-- ===========================================================================
-- Interview Studio — MySQL schema  (SR4)
-- Accessible Interview System Project — CSSE 4901 Capstone, Savage 17
-- Run automatically by seed.py, or:  mysql -u root -p < schema.sql
-- ===========================================================================

CREATE DATABASE IF NOT EXISTS interview_studio
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE interview_studio;

-- --- Users (F15, R1, R2, NF1, NF2) -----------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    name           VARCHAR(120) NOT NULL,
    email          VARCHAR(190) NOT NULL UNIQUE,
    password_hash  VARCHAR(255) NOT NULL,          -- Werkzeug PBKDF2 hash, never plaintext
    text_scale     TINYINT      NOT NULL DEFAULT 100, -- saved visual preference (F10, R12)
    read_aloud     TINYINT(1)   NOT NULL DEFAULT 0,   -- saved TTS preference (F12, R13)
    created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- --- Reusable technical question bank (F1) ----------------------------------
CREATE TABLE IF NOT EXISTS question_library (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    category    VARCHAR(60)  NOT NULL,   -- Behavioral | Coding | System Design | Recruiter Screen
    difficulty  VARCHAR(20)  NOT NULL,   -- Warm-up | Standard | Onsite
    prompt      TEXT         NOT NULL
) ENGINE=InnoDB;

-- --- Interview sessions (R3, R4, F3, F4, F8, F9) ----------------------------
-- One row per session. mode='mock' is a full interview; mode='practice' is a
-- single one-off question (F8, R10). status supports pause/resume (F9, R11).
CREATE TABLE IF NOT EXISTS interviews (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    user_id        INT NOT NULL,
    track          VARCHAR(60)  NOT NULL,
    difficulty     VARCHAR(20)  NOT NULL DEFAULT 'Standard',
    mode           VARCHAR(20)  NOT NULL DEFAULT 'mock',      -- mock | practice
    job_title      VARCHAR(190),                              -- F2, R5 (optional)
    job_description TEXT,                                     -- F2, R5 (optional)
    length_min     INT          NOT NULL DEFAULT 15,
    status         VARCHAR(20)  NOT NULL DEFAULT 'in_progress', -- in_progress | paused | completed
    overall_score  INT,                                       -- 0-100 (F7, R9)
    strengths      TEXT,                                      -- report summary (F5, F7)
    improvements   TEXT,                                      -- report summary (F5, F7)
    created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at   DATETIME,
    CONSTRAINT fk_interview_user FOREIGN KEY (user_id)
        REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- --- Questions asked in a session ------------------------------------------
CREATE TABLE IF NOT EXISTS questions (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    interview_id   INT NOT NULL,
    q_index        INT NOT NULL,             -- 1,2,3... order in the session
    prompt         TEXT NOT NULL,
    source         VARCHAR(20) NOT NULL DEFAULT 'ai',  -- ai | library | job_desc
    tag            VARCHAR(60),              -- e.g. "Follow-up · impact"
    created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_question_interview FOREIGN KEY (interview_id)
        REFERENCES interviews(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- --- Candidate answers (R6) -------------------------------------------------
CREATE TABLE IF NOT EXISTS answers (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    question_id   INT NOT NULL,
    interview_id  INT NOT NULL,
    user_id       INT NOT NULL,
    content       TEXT NOT NULL,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_answer_question FOREIGN KEY (question_id)
        REFERENCES questions(id) ON DELETE CASCADE,
    CONSTRAINT fk_answer_interview FOREIGN KEY (interview_id)
        REFERENCES interviews(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- --- Per-answer AI analysis + feedback (F5, F6, R7, R8) ---------------------
CREATE TABLE IF NOT EXISTS feedback (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    answer_id      INT NOT NULL,
    interview_id   INT NOT NULL,
    structure      INT,         -- STAR completeness  0-100
    clarity        INT,         -- 0-100
    relevance      INT,         -- does it answer the question  0-100
    completeness   INT,         -- specifics & measurable result 0-100
    confidence     INT,         -- overall read of the answer 0-100
    strengths      TEXT,
    improvements   TEXT,
    tip            TEXT,        -- one concrete coaching tip
    created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_feedback_answer FOREIGN KEY (answer_id)
        REFERENCES answers(id) ON DELETE CASCADE,
    CONSTRAINT fk_feedback_interview FOREIGN KEY (interview_id)
        REFERENCES interviews(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE INDEX idx_interviews_user  ON interviews(user_id);
CREATE INDEX idx_questions_intv   ON questions(interview_id);
CREATE INDEX idx_answers_intv     ON answers(interview_id);
CREATE INDEX idx_feedback_intv    ON feedback(interview_id);
