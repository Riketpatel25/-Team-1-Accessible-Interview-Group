"""
seed.py — one-time setup.
Creates the database + tables (schema.sql), seeds the question library (F1),
and adds a demo account so you can log in immediately.

Run:  python seed.py
"""

from werkzeug.security import generate_password_hash
import database as db

LIBRARY = [
    ("Behavioral", "Warm-up", "Tell me about a project you enjoyed working on."),
    ("Behavioral", "Standard", "Tell me about a time you disagreed with a teammate on a technical decision."),
    ("Behavioral", "Standard", "Describe a time you missed a deadline. What happened and what did you learn?"),
    ("Behavioral", "Onsite", "Tell me about the most difficult technical problem you've solved end to end."),
    ("Coding", "Warm-up", "How would you reverse a string, and what's the time complexity?"),
    ("Coding", "Standard", "Walk me through detecting a cycle in a linked list. Think out loud."),
    ("Coding", "Onsite", "Design an LRU cache. Explain your data structures and their complexity."),
]


def main():
    print("Creating database and tables from schema.sql ...")
    db.init_db("schema.sql")

    # seed question library only if empty
    existing = db.query("SELECT COUNT(*) AS n FROM question_library", one=True)["n"]
    if existing == 0:
        for cat, diff, prompt in LIBRARY:
            db.execute(
                "INSERT INTO question_library (category, difficulty, prompt) VALUES (%s,%s,%s)",
                (cat, diff, prompt),
            )
        print(f"Seeded {len(LIBRARY)} library questions.")
    else:
        print(f"Question library already has {existing} rows — skipping.")

    # demo account
    if not db.get_user_by_email("demo@interview.studio"):
        db.create_user("Demo User", "demo@interview.studio",
                       generate_password_hash("demo123"))
        print("Created demo account -> email: demo@interview.studio  password: demo123")
    else:
        print("Demo account already exists.")

    print("\nDone. Start the app with:  flask --app app run --debug")


if __name__ == "__main__":
    main()
