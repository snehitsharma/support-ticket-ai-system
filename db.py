import os
import sqlite3

DB_PATH = "tickets.db"


def get_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    abs_path = os.path.abspath(db_path)
    return sqlite3.connect(f"file:{abs_path}?mode=ro", uri=True)
