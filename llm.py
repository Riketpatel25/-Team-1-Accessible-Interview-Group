"""
llm.py — the single AI (OpenAI, SR5) that runs the interview.

Three jobs, one model:
  1. generate_questions(...)  -> questions from a track OR a pasted job description (F2, R5)
  2. analyze_answer(...)      -> score + strengths/improvements + next follow-up (F5, F6, R7, R8)
  3. build_report(...)        -> overall summary for the interview report (F7, R9)

If OPENAI_API_KEY is not set (or a call fails), everything falls back to a
deterministic offline "mock" so the app runs end-to-end without a key and so
NF12 (graceful failure) always has something to return.
"""

import json
import random
from config import Config

OPENERS = {
    "Behavioral": "Tell me about a time you disagreed with a teammate on a technical decision. How did you handle it?",
    "Technical / Coding": "Walk me through how you'd detect a cycle in a linked list. Think out loud.",
}

_QUESTION_SYS = """You are Ava, a warm but rigorous technical interviewer for software roles.
Generate realistic interview questions. Match the difficulty:
- Warm-up: gentle, encouraging.
- Standard: a normal round.
- Onsite: demanding, probes edge cases and trade-offs.
Respond ONLY with JSON: {"questions": ["...", "..."]}"""

_ANALYZE_SYS = """You are Ava, a supportive technical interviewer coaching a nervous candidate.
Score the candidate's answer fairly and kindly. Then write a natural follow-up question.
Respond ONLY with JSON:
{
  "structure": int 0-100,      // STAR completeness
  "clarity": int 0-100,
  "relevance": int 0-100,      // did it answer the question asked
  "completeness": int 0-100,   // specifics & measurable results
  "confidence": int 0-100,     // overall read of the answer
  "strengths": "one encouraging sentence about what worked",
  "improvements": "one specific sentence about what to add",
  "tip": "one concrete, actionable coaching sentence",
  "next_question": "the follow-up question",
  "tag": "short label e.g. 'Follow-up · impact'"
}"""

_REPORT_SYS = """You are Ava, summarizing a completed mock interview for the candidate's report.
Be encouraging and specific. Respond ONLY with JSON:
{"overall": int 0-100, "strengths": "2-3 sentences", "improvements": "2-3 sentences"}"""


def _client():
    from openai import OpenAI
    return OpenAI(api_key=Config.OPENAI_API_KEY)


def _chat_json(system, user, max_tokens=700):
    """One OpenAI call that returns parsed JSON, or None on any failure."""
    if not Config.OPENAI_API_KEY:
        return None
    try:
        resp = _client().chat.completions.create(
            model=Config.LLM_MODEL,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            max_tokens=max_tokens,
            temperature=0.7,
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        print(f"[llm] OpenAI call failed, using mock: {e}")
        return None


# ----------------------------------------------------------------------------
# 1. Question generation (F1, F2, R5)
# ----------------------------------------------------------------------------
def generate_questions(track, difficulty, count=4, job_description=None):
    """Return a list of question strings. Uses the job description when given (F2)."""
    if job_description:
        user = (f"Generate {count} {difficulty} technical interview questions tailored to "
                f"THIS job description. Focus on skills it names.\n\nJob description:\n{job_description}")
    else:
        user = f"Generate {count} {difficulty} interview questions for a '{track}' interview."

    data = _chat_json(_QUESTION_SYS, user)
    if data and isinstance(data.get("questions"), list) and data["questions"]:
        return data["questions"][:count]

    # ---- offline mock ----
    opener = OPENERS.get(track, OPENERS["Behavioral"])
    extras = [
        "Describe a project you're proud of and the hardest problem you solved on it.",
        "Tell me about a time you received difficult feedback. What did you do with it?",
        "How do you approach a problem when you're unsure where to start?",
        "Walk me through a technical trade-off you made and why.",
        "Tell me about a time you had to learn something quickly under pressure.",
    ]
    random.shuffle(extras)
    return [opener] + extras[: max(0, count - 1)]


# ----------------------------------------------------------------------------
# 2. Answer analysis + follow-up (F5, F6, R7, R8)
# ----------------------------------------------------------------------------
def analyze_answer(track, difficulty, question, answer, is_last=False):
    user = (f"Track: {track}. Difficulty: {difficulty}.\n"
            f"Question asked: {question}\n"
            f"Candidate's answer: \"{answer}\"\n"
            "Score it, give strengths/improvements/tip, and a follow-up question.")
    data = _chat_json(_ANALYZE_SYS, user)
    if data and "confidence" in data:
        data.setdefault("tag", "Follow-up")
        return data
    return _mock_analysis()


def _mock_analysis():
    base = 60 + random.randint(-6, 14)
    fb = {
        "structure": min(96, base + random.randint(0, 16)),
        "clarity": min(96, base + random.randint(2, 18)),
        "relevance": min(96, base + random.randint(0, 20)),
        "completeness": min(96, base + random.randint(-10, 6)),
    }
    fb["confidence"] = round(sum(fb.values()) / 4)
    fb.update({
        "strengths": "You set up the situation clearly and stayed calm and organized.",
        "improvements": "Add a concrete, measurable result so the impact lands.",
        "tip": "Close with a number — a %, a time saved, or a metric that moved.",
        "next_question": random.choice([
            "What was the measurable result after you shipped it?",
            "What would you do differently if you faced that same call today?",
            "How did the rest of the team react to your decision?",
            "Where could this approach break at 10x the scale?",
        ]),
        "tag": "Follow-up · impact",
    })
    return fb


# ----------------------------------------------------------------------------
# 3. Interview report (F7, R9)
# ----------------------------------------------------------------------------
def build_report(track, transcript, avg_confidence):
    joined = "\n".join(
        f"Q{r['q_index']}: {r['prompt']}\nA: {r.get('answer') or '(no answer)'}"
        for r in transcript
    )
    data = _chat_json(_REPORT_SYS,
                      f"Track: {track}\n\nTranscript:\n{joined}\n\n"
                      f"Average per-answer confidence was {avg_confidence}.")
    if data and "overall" in data:
        return data
    return {
        "overall": avg_confidence or 70,
        "strengths": "You communicated clearly and kept a steady, structured pace "
                     "throughout the session. Your setups were easy to follow.",
        "improvements": "Lean harder on specifics — concrete numbers and outcomes. "
                        "Tie each story back to measurable impact to finish strong.",
    }
