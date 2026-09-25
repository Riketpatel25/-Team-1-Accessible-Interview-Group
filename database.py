"""
database.py — all MySQL access for Interview Studio (SR4).

Every SQL statement lives here so routes never touch the database directly.
Uses mysql-connector-python. NF2 (user isolation) is enforced by always
scoping reads/writes to a user_id that the route takes from the login session.
"""

import mysql.connector
from mysql.connector import errorcode
from config import Config


# ----------------------------------------------------------------------------
# Connection helpers
# ----------------------------------------------------------------------------
def get_conn(with_db=True):
    """Open a MySQL connection. with_db=False connects to the server only
    (used once to CREATE DATABASE during setup)."""
    params = dict(Config.DB)
    if not with_db:
        params.pop("database", None)
    return mysql.connector.connect(**params)


def query(sql, params=None, one=False):
    """Run a SELECT and return dict rows (or a single dict with one=True)."""
    conn = get_conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params or ())
        rows = cur.fetchall()
        return (rows[0] if rows else None) if one else rows
    finally:
        conn.close()


def execute(sql, params=None):
    """Run an INSERT/UPDATE/DELETE. Returns lastrowid for inserts."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


# ----------------------------------------------------------------------------
# Schema setup
# ----------------------------------------------------------------------------
def init_db(schema_path="schema.sql"):
    """Create the database + tables from schema.sql. Safe to run repeatedly."""
    with open(schema_path, "r", encoding="utf-8") as f:
        script = f.read()
    # Connect without selecting the DB first (schema.sql creates it)
    conn = get_conn(with_db=False)
    try:
        cur = conn.cursor()
        for statement in _split_statements(script):
            if statement.strip():
                cur.execute(statement)
        conn.commit()
    finally:
        conn.close()


def _split_statements(script):
    """Naive splitter on ';' — fine for this schema (no stored procedures)."""
    return [s for s in script.split(";") if s.strip() and not s.strip().startswith("--")]


# ----------------------------------------------------------------------------
# Users (F15, R1, R2)
# ----------------------------------------------------------------------------
def create_user(name, email, password_hash):
    return execute(
        "INSERT INTO users (name, email, password_hash) VALUES (%s, %s, %s)",
        (name, email, password_hash),
    )


def get_user_by_email(email):
    return query("SELECT * FROM users WHERE email = %s", (email,), one=True)


def get_user(user_id):
    return query("SELECT * FROM users WHERE id = %s", (user_id,), one=True)


def update_user_prefs(user_id, text_scale, read_aloud):
    """Persist accessibility prefs (F10, F12, R12, R13)."""
    execute(
        "UPDATE users SET text_scale = %s, read_aloud = %s WHERE id = %s",
        (int(text_scale), 1 if read_aloud else 0, user_id),
    )


def delete_user_data(user_id):
    """NF4 — confirmed deletion. Cascades remove interviews/answers/feedback."""
    execute("DELETE FROM users WHERE id = %s", (user_id,))


# ----------------------------------------------------------------------------
# Question library (F1)
# ----------------------------------------------------------------------------
def library_questions(category=None, difficulty=None, limit=20):
    sql = "SELECT * FROM question_library WHERE 1=1"
    params = []
    if category:
        sql += " AND category = %s"; params.append(category)
    if difficulty:
        sql += " AND difficulty = %s"; params.append(difficulty)
    sql += " ORDER BY RAND() LIMIT %s"; params.append(limit)
    return query(sql, tuple(params))


# ----------------------------------------------------------------------------
# Interviews (R3, R4, F8, F9)
# ----------------------------------------------------------------------------
def create_interview(user_id, track, difficulty, mode, length_min,
                     job_title=None, job_description=None):
    return execute(
        """INSERT INTO interviews
           (user_id, track, difficulty, mode, length_min, job_title, job_description)
           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        (user_id, track, difficulty, mode, int(length_min), job_title, job_description),
    )


def get_interview(interview_id, user_id):
    """Scoped to user_id -> enforces NF2 (no cross-user access)."""
    return query(
        "SELECT * FROM interviews WHERE id = %s AND user_id = %s",
        (interview_id, user_id), one=True,
    )


def list_interviews(user_id, limit=50):
    return query(
        "SELECT * FROM interviews WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
        (user_id, limit),
    )


def set_status(interview_id, user_id, status):
    """Pause / resume / in_progress (F9, R11)."""
    execute(
        "UPDATE interviews SET status = %s WHERE id = %s AND user_id = %s",
        (status, interview_id, user_id),
    )


def complete_interview(interview_id, user_id, overall, strengths, improvements):
    execute(
        """UPDATE interviews
           SET status='completed', overall_score=%s, strengths=%s, improvements=%s,
               completed_at=NOW()
           WHERE id=%s AND user_id=%s""",
        (int(overall), strengths, improvements, interview_id, user_id),
    )


# ----------------------------------------------------------------------------
# Questions / Answers / Feedback
# ----------------------------------------------------------------------------
def add_question(interview_id, q_index, prompt, source="ai", tag=None):
    return execute(
        "INSERT INTO questions (interview_id, q_index, prompt, source, tag) VALUES (%s,%s,%s,%s,%s)",
        (interview_id, q_index, prompt, source, tag),
    )


def get_questions(interview_id):
    return query("SELECT * FROM questions WHERE interview_id = %s ORDER BY q_index", (interview_id,))


def add_answer(question_id, interview_id, user_id, content):
    return execute(
        "INSERT INTO answers (question_id, interview_id, user_id, content) VALUES (%s,%s,%s,%s)",
        (question_id, interview_id, user_id, content),
    )


def add_feedback(answer_id, interview_id, fb):
    """fb = dict with structure/clarity/relevance/completeness/confidence/strengths/improvements/tip."""
    return execute(
        """INSERT INTO feedback
           (answer_id, interview_id, structure, clarity, relevance, completeness,
            confidence, strengths, improvements, tip)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (answer_id, interview_id, fb.get("structure"), fb.get("clarity"),
         fb.get("relevance"), fb.get("completeness"), fb.get("confidence"),
         fb.get("strengths"), fb.get("improvements"), fb.get("tip")),
    )


def get_transcript(interview_id, user_id):
    """Full ordered transcript with each answer's feedback (F7, R9)."""
    if not get_interview(interview_id, user_id):
        return None
    return query(
        """SELECT q.q_index, q.prompt, q.tag, q.source,
                  a.content AS answer, a.id AS answer_id,
                  f.structure, f.clarity, f.relevance, f.completeness,
                  f.confidence, f.strengths, f.improvements, f.tip
           FROM questions q
           LEFT JOIN answers  a ON a.question_id = q.id
           LEFT JOIN feedback f ON f.answer_id   = a.id
           WHERE q.interview_id = %s
           ORDER BY q.q_index""",
        (interview_id,),
    )


# ----------------------------------------------------------------------------
# Statistics & progress (F13, F14, R14, R15, R16)
# ----------------------------------------------------------------------------
def user_stats(user_id):
    total = query(
        "SELECT COUNT(*) AS n FROM interviews WHERE user_id=%s AND status='completed'",
        (user_id,), one=True)["n"]
    avg = query(
        "SELECT AVG(overall_score) AS a FROM interviews WHERE user_id=%s AND overall_score IS NOT NULL",
        (user_id,), one=True)["a"]
    # weakest skill dimension across all feedback (where to practice next)
    dims = query(
        """SELECT AVG(structure) s, AVG(clarity) c, AVG(relevance) r, AVG(completeness) k
           FROM feedback f JOIN interviews i ON i.id=f.interview_id
           WHERE i.user_id=%s""", (user_id,), one=True)
    trend = query(
        """SELECT id, track, overall_score, created_at
           FROM interviews WHERE user_id=%s AND overall_score IS NOT NULL
           ORDER BY created_at ASC""", (user_id,))
    labels = {"s": "Structure", "c": "Clarity", "r": "Relevance", "k": "Completeness"}
    weakest = None
    if dims and any(dims.values()):
        weakest_key = min((k for k in labels if dims[k] is not None), key=lambda k: dims[k])
        weakest = labels[weakest_key]
    return {
        "completed": total,
        "avg_score": round(avg) if avg is not None else None,
        "dimensions": {labels[k]: (round(dims[k]) if dims[k] is not None else None)
                       for k in labels} if dims else {},
        "weakest_area": weakest,
        "trend": [{"score": t["overall_score"], "track": t["track"],
                   "date": str(t["created_at"])} for t in trend],
    }
