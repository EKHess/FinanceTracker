import sqlite3
from pathlib import Path
from datetime import datetime

DATABASE_FOLDER = Path("data")
DATABASE_FOLDER.mkdir(exist_ok=True)

DATABASE = DATABASE_FOLDER / "finance.db"


def get_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS months (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        month INTEGER NOT NULL,
        year INTEGER NOT NULL,
        income REAL DEFAULT 0,
        finalized INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        month_id INTEGER NOT NULL,
        description TEXT NOT NULL,
        amount REAL NOT NULL,
        category TEXT NOT NULL,
        recurring INTEGER DEFAULT 0,

        FOREIGN KEY(month_id)
            REFERENCES months(id)
    )
    """)

    conn.commit()
    conn.close()

def get_current_month():

    today = datetime.today()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM months
        WHERE month = ?
        AND year = ?
    """, (today.month, today.year))

    month = cursor.fetchone()

    if month is None:

        cursor.execute("""
            INSERT INTO months(month, year)
            VALUES(?, ?)
        """, (today.month, today.year))

        conn.commit()

        cursor.execute("""
            SELECT *
            FROM months
            WHERE month=?
            AND year=?
        """, (today.month, today.year))

        month = cursor.fetchone()

    conn.close()

    return month
