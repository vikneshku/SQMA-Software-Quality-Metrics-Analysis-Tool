"""
reset_db.py - delete the SQLite database and create a fresh empty one.
Usage:  python reset_db.py          (asks for confirmation)
        python reset_db.py --yes    (no question)
WARNING: all projects, bugs, users and analysis data are lost. Uploaded files in uploads/ are kept.
"""
import os
import sys

from config import DB_PATH


def main():
    if "--yes" not in sys.argv:
        if input(f"Delete {DB_PATH} and ALL its data? Type yes to continue: ").strip().lower() != "yes":
            print("Cancelled.")
            return
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print("Old database deleted.")
    from app import app, db       # importing app creates the new schema
    with app.app_context():
        db.create_all()
    print("New empty database created. Start the app with:  python app.py")
    print("The first account you register becomes the Admin.")


if __name__ == "__main__":
    main()
