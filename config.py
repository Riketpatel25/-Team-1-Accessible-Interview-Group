"""
config.py — loads settings from the environment (.env file).
Central place for every tunable value so nothing is hard-coded elsewhere.
"""

import os
from dotenv import load_dotenv

load_dotenv()  # read .env if present


class Config:
    # Flask
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    DEBUG = os.environ.get("FLASK_DEBUG", "1") == "1"

    # OpenAI (SR5)
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
    LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")

    # MySQL (SR4)
    DB = {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", "3306")),
        "user": os.environ.get("DB_USER", "root"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "database": os.environ.get("DB_NAME", "interview_studio"),
    }
    DB_NAME = os.environ.get("DB_NAME", "interview_studio")

    # How many questions a mock interview asks, by session length
    QUESTIONS_BY_LENGTH = {15: 4, 30: 6, 45: 8}
