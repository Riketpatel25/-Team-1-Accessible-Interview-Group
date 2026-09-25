# Interview Studio — Accessible Interview System

An AI-powered mock-interview web app that lets job seekers practice technical
interviews in a low-pressure, self-paced environment, with feedback, progress
tracking, and accessibility (keyboard, screen reader, adjustable text, and
text-to-speech) built in.

*CSSE 4901 Capstone — Savage 17.* This codebase implements the Product
Requirements (SR1–SR7, F1–F15, R1–R16, NF1–NF12).

---

## Tech stack (matches the SRS)

| Layer     | Choice                              | Requirement |
|-----------|-------------------------------------|-------------|
| Frontend  | HTML + CSS + vanilla JavaScript     | SR1, SR6, NF10, NF11 |
| Backend   | Python 3 + Flask                    | SR3 |
| Database  | **MySQL** (`mysql-connector-python`)| SR4 |
| AI        | **OpenAI API** (one model)          | SR5, F2, F4, F6 |
| Speech    | Web Speech API (TTS + voice input)  | SR7, F11, F12 |

The one model does three jobs: generate questions (from a track *or* a pasted
job description), analyze each answer, and write the final report.

---

## Project layout

```
interview-studio/
├── app.py            # Flask app + every API route
├── config.py         # Loads settings from .env
├── database.py       # All MySQL access (data-access layer)
├── llm.py            # The single AI: OpenAI calls + offline mock fallback
├── schema.sql        # MySQL schema (tables, keys, indexes)
├── seed.py           # Creates DB + tables, seeds question library + demo user
├── requirements.txt
├── .env.example
├── static/
│   ├── index.html    # Single-page app (auth, setup, interview, report, history)
│   ├── css/styles.css
│   └── js/app.js
└── README.md
```

---

## Setup

**Prerequisites:** Python 3.10+, a running MySQL server, and (optionally) an
OpenAI API key.

```bash
cd interview-studio

python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
#   edit .env -> set DB_USER / DB_PASSWORD for your MySQL
#   optionally set OPENAI_API_KEY (leave blank to run in offline mock mode)

python seed.py                       # creates the DB, tables, library, demo user
flask --app app run --debug          # open http://127.0.0.1:5000
```

**Demo login:** `demo@interview.studio` / `demo123`

> **No OpenAI key?** The app still runs end-to-end. `llm.py` falls back to a
> deterministic mock for questions, scoring, and reports — perfect for demos and
> grading. This also backs **NF12** (graceful failure with retry).

---

## How a session flows

1. **Log in / create account** (`F15, R1, R2`). Every data route requires the
   session and is scoped to the logged-in user, enforcing **NF1/NF2**.
2. **Set up** the session: pick a track, difficulty, length, and mode
   (*full mock* or *one-off practice question*, `F8/R10`). Optionally paste a
   **job description** so questions are generated for that role (`F2/R5`).
3. **Interview**: Ava asks one question at a time (`F3/F4`). Answer by typing or
   by **voice** (Web Speech). Turn on **Read aloud** for **text-to-speech**
   (`F11/F12/R13`). Each answer is analyzed and scored live (`F5/F6/R6–R8`).
   You can **pause and resume** at any time (`F9/R11`).
4. **Report**: an overall score, strengths, areas to improve, and a
   question-by-question breakdown (`F7/R9`).
5. **History & progress**: past sessions, average score, and your weakest skill
   area to focus on next (`F13/F14/R14–R16`).

Accessibility controls (theme, **text size A−/A/A+**, reduced-motion) live in
the top bar (`F10/R12/NF7–NF9`), and preferences are saved to the account.

---

## API reference

| Method | Route                              | Purpose | Req |
|--------|------------------------------------|---------|-----|
| POST   | `/api/register`, `/api/login`      | account + session | R1, R2 |
| POST   | `/api/logout`                      | end session | F15 |
| GET    | `/api/me`                          | current user | NF1 |
| POST   | `/api/prefs`                       | save text size / read-aloud | F10, R12 |
| POST   | `/api/interviews`                  | start mock or practice; job-desc questions | R4, R5, F8 |
| POST   | `/api/interviews/<id>/answer`      | submit answer → score + next question | R6, R7, R8 |
| POST   | `/api/interviews/<id>/pause`       | pause & save | F9, R11 |
| POST   | `/api/interviews/<id>/resume`      | resume with transcript | F9, R11 |
| POST   | `/api/interviews/<id>/complete`    | build report | F7, R9 |
| GET    | `/api/interviews/<id>`             | past report + transcript | R9, R16 |
| GET    | `/api/history`                     | list past sessions | F14, R16 |
| GET    | `/api/stats`                       | progress statistics | F13, R14, R15 |
| DELETE | `/api/account`                     | remove all user data | NF4 |

---

## Requirements traceability (where each is implemented)

- **F1 Question library** → `question_library` table + `database.library_questions` + seeded in `seed.py`
- **F2 / R5 Job-description questions** → `llm.generate_questions(job_description=…)`, setup form fields
- **F3 / F4 Text + AI interview** → `/api/interviews/*`, chat UI in `app.js`
- **F5 / R8 Feedback**, **F6 / R7 Answer analysis** → `llm.analyze_answer`, `feedback` table, live rail
- **F7 / R9 Report** → `/api/interviews/<id>/complete`, report view
- **F8 / R10 One-off practice** → `mode='practice'`
- **F9 / R11 Pause & resume** → `interviews.status`, pause/resume routes
- **F10 / R12 Visual adjustments** → text-size control, themes, saved prefs
- **F11 Screen reader** → semantic HTML, ARIA roles/labels, `aria-live` log
- **F12 / R13 Text-to-speech** → `speechSynthesis` (Read aloud)
- **F13 / R14 Statistics**, **F14 / R15–R16 History & progress** → `database.user_stats`, history view
- **F15 / R1 / R2 Accounts** → `users` table, register/login/logout, hashed passwords
- **NF1 / NF2 Auth + isolation** → `login_required`, all queries scoped to `user_id`
- **NF3 Save confirmation** → each API returns immediately after commit
- **NF4 Deletion** → `DELETE /api/account` cascades all user rows
- **NF7 Keyboard**, **NF8 / NF9 TTS + adjustable text (WCAG)** → focus styles, controls
- **NF12 Retry on AI failure** → mock fallback + 502 with retry-friendly messages

---

## Security notes

- Passwords are stored only as Werkzeug PBKDF2 hashes — never plaintext.
- `MySQL` access uses parameterized queries throughout (no string-built SQL).
- Sessions are signed with `SECRET_KEY`; set a long random value in production.
- For deployment, run behind gunicorn: `gunicorn -w 4 app:app`.
