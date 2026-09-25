"""
app.py — Flask application + all API routes for Interview Studio.

Route  ->  requirement it satisfies
  auth (register/login/logout)          F15, R1, R2, NF1, NF2
  /api/interviews  (start)              R3, R4, F2, F3, F4, F8 (mode='practice'), R5, R10
  /api/interviews/<id>/answer           R6, R7, R8, F5, F6
  /api/interviews/<id>/pause|resume     F9, R11
  /api/interviews/<id>/complete|report  F7, R9
  /api/history                          F14, R16
  /api/stats                            F13, R14, R15
  /api/prefs                            F10, R12, F12, R13 (saved server-side)
  /api/account (DELETE)                 NF4
Every data route requires login and is scoped to the session user -> NF1/NF2.
"""

from functools import wraps
from flask import Flask, request, jsonify, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash

import database as db
import llm
from config import Config

app = Flask(__name__, static_folder="static", static_url_path="")
app.config["SECRET_KEY"] = Config.SECRET_KEY


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return jsonify(error="Please log in to continue."), 401
        return fn(*args, **kwargs)
    return wrapper


def current_user_id():
    return session.get("user_id")


# ---------------------------------------------------------------------------
# Static / SPA
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory("static", "index.html")


# ---------------------------------------------------------------------------
# Account: register / login / logout / me  (F15, R1, R2)
# ---------------------------------------------------------------------------
@app.post("/api/register")
def register():
    d = request.get_json(force=True)
    name = (d.get("name") or "").strip()
    email = (d.get("email") or "").strip().lower()
    password = d.get("password") or ""
    if not name or not email or len(password) < 6:
        return jsonify(error="Name, email, and a 6+ character password are required."), 400
    if db.get_user_by_email(email):
        return jsonify(error="An account with that email already exists."), 409
    uid = db.create_user(name, email, generate_password_hash(password))
    session["user_id"] = uid
    return jsonify(user=_public_user(db.get_user(uid)))


@app.post("/api/login")
def login():
    d = request.get_json(force=True)
    email = (d.get("email") or "").strip().lower()
    user = db.get_user_by_email(email)
    if not user or not check_password_hash(user["password_hash"], d.get("password") or ""):
        return jsonify(error="Incorrect email or password."), 401
    session["user_id"] = user["id"]
    return jsonify(user=_public_user(user))


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/api/me")
def me():
    if "user_id" not in session:
        return jsonify(user=None)
    return jsonify(user=_public_user(db.get_user(session["user_id"])))


def _public_user(u):
    return {"id": u["id"], "name": u["name"], "email": u["email"],
            "text_scale": u["text_scale"], "read_aloud": bool(u["read_aloud"])}


# ---------------------------------------------------------------------------
# Accessibility preferences (F10, F12, R12, R13)
# ---------------------------------------------------------------------------
@app.post("/api/prefs")
@login_required
def save_prefs():
    d = request.get_json(force=True)
    scale = max(80, min(150, int(d.get("text_scale", 100))))
    db.update_user_prefs(current_user_id(), scale, bool(d.get("read_aloud")))
    return jsonify(ok=True)


# ---------------------------------------------------------------------------
# Start an interview (R3, R4) or a one-off practice question (F8, R10)
# ---------------------------------------------------------------------------
@app.post("/api/interviews")
@login_required
def start_interview():
    d = request.get_json(force=True)
    uid = current_user_id()
    track = d.get("track", "Behavioral")
    difficulty = d.get("difficulty", "Standard")
    mode = d.get("mode", "mock")               # 'mock' | 'practice'
    length = int(d.get("length", 15))
    job_title = (d.get("job_title") or "").strip() or None
    job_desc = (d.get("job_description") or "").strip() or None

    iv_id = db.create_interview(uid, track, difficulty, mode, length, job_title, job_desc)

    # how many questions to ask
    count = 1 if mode == "practice" else Config.QUESTIONS_BY_LENGTH.get(length, 4)
    try:
        questions = llm.generate_questions(track, difficulty, count, job_desc)
    except Exception:
        return jsonify(error="Could not reach the AI service. Please retry."), 502  # NF12

    # store only the first question now; follow-ups come from analysis
    source = "job_desc" if job_desc else "ai"
    first = questions[0]
    db.add_question(iv_id, 1, first, source=source, tag="Opening question")

    return jsonify(interview_id=iv_id, mode=mode, question=first,
                   q_index=1, total=count, tag="Opening question")


# ---------------------------------------------------------------------------
# Submit an answer -> analyze + next question (R6, R7, R8, F5, F6)
# ---------------------------------------------------------------------------
@app.post("/api/interviews/<int:iv_id>/answer")
@login_required
def submit_answer(iv_id):
    uid = current_user_id()
    iv = db.get_interview(iv_id, uid)                 # NF2 ownership check
    if not iv:
        return jsonify(error="Interview not found."), 404

    d = request.get_json(force=True)
    answer_text = (d.get("answer") or "").strip()
    if not answer_text:
        return jsonify(error="Answer cannot be empty."), 400

    questions = db.get_questions(iv_id)
    current_q = questions[-1]
    total = 1 if iv["mode"] == "practice" else Config.QUESTIONS_BY_LENGTH.get(iv["length_min"], 4)
    q_index = current_q["q_index"]
    is_last = q_index >= total

    # store answer
    ans_id = db.add_answer(current_q["id"], iv_id, uid, answer_text)

    # analyze (F6) + feedback (F5)
    try:
        fb = llm.analyze_answer(iv["track"], iv["difficulty"],
                                current_q["prompt"], answer_text, is_last)
    except Exception:
        return jsonify(error="The AI could not analyze that answer. Please retry."), 502  # NF12
    db.add_feedback(ans_id, iv_id, fb)

    payload = {
        "score": {k: fb.get(k) for k in
                  ("structure", "clarity", "relevance", "completeness", "confidence")},
        "strengths": fb.get("strengths"),
        "improvements": fb.get("improvements"),
        "tip": fb.get("tip"),
        "is_last": is_last,
    }

    # next question (mock interview only)
    if not is_last and iv["mode"] == "mock":
        next_q = fb.get("next_question") or "Tell me more about the impact of that."
        db.add_question(iv_id, q_index + 1, next_q, source="ai", tag=fb.get("tag"))
        payload.update(next_question=next_q, q_index=q_index + 1,
                       total=total, tag=fb.get("tag"))
    return jsonify(payload)


# ---------------------------------------------------------------------------
# Pause / resume (F9, R11)
# ---------------------------------------------------------------------------
@app.post("/api/interviews/<int:iv_id>/pause")
@login_required
def pause(iv_id):
    db.set_status(iv_id, current_user_id(), "paused")
    return jsonify(ok=True, status="paused")


@app.post("/api/interviews/<int:iv_id>/resume")
@login_required
def resume(iv_id):
    iv = db.get_interview(iv_id, current_user_id())
    if not iv:
        return jsonify(error="Interview not found."), 404
    db.set_status(iv_id, current_user_id(), "in_progress")
    return jsonify(ok=True, status="in_progress",
                   transcript=db.get_transcript(iv_id, current_user_id()))


# ---------------------------------------------------------------------------
# Complete + report (F5, F7, R8, R9)
# ---------------------------------------------------------------------------
@app.post("/api/interviews/<int:iv_id>/complete")
@login_required
def complete(iv_id):
    uid = current_user_id()
    iv = db.get_interview(iv_id, uid)
    if not iv:
        return jsonify(error="Interview not found."), 404
    transcript = db.get_transcript(iv_id, uid)
    confs = [r["confidence"] for r in transcript if r.get("confidence") is not None]
    avg = round(sum(confs) / len(confs)) if confs else 70
    try:
        report = llm.build_report(iv["track"], transcript, avg)
    except Exception:
        report = {"overall": avg, "strengths": "Nice, steady session.",
                  "improvements": "Add more measurable detail next time."}
    db.complete_interview(iv_id, uid, report["overall"],
                          report["strengths"], report["improvements"])
    return jsonify(report=report, transcript=transcript)


@app.get("/api/interviews/<int:iv_id>")
@login_required
def get_report(iv_id):
    uid = current_user_id()
    iv = db.get_interview(iv_id, uid)
    if not iv:
        return jsonify(error="Interview not found."), 404
    return jsonify(interview=iv, transcript=db.get_transcript(iv_id, uid))


# ---------------------------------------------------------------------------
# History + statistics (F13, F14, R14, R15, R16)
# ---------------------------------------------------------------------------
@app.get("/api/history")
@login_required
def history():
    return jsonify(interviews=db.list_interviews(current_user_id()))


@app.get("/api/stats")
@login_required
def stats():
    return jsonify(stats=db.user_stats(current_user_id()))


# ---------------------------------------------------------------------------
# Delete account + all data (NF4)
# ---------------------------------------------------------------------------
@app.delete("/api/account")
@login_required
def delete_account():
    db.delete_user_data(current_user_id())
    session.clear()
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(debug=Config.DEBUG, port=5000)
