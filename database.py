import shutil
import sqlite3
import tempfile
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

        label TEXT NOT NULL UNIQUE,

        month INTEGER NOT NULL,

        year INTEGER NOT NULL,

        income REAL NOT NULL DEFAULT 0,

        finalized INTEGER NOT NULL DEFAULT 0,

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


    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scorecards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        total_spending REAL NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scorecard_expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scorecard_id INTEGER NOT NULL,
        description TEXT NOT NULL,
        amount REAL NOT NULL,
        category TEXT NOT NULL,
        recurring INTEGER DEFAULT 0,
        FOREIGN KEY(scorecard_id)
            REFERENCES scorecards(id)
    )
    """)

    conn.commit()
    conn.close()
    migrate_categories()


def migrate_categories():
    legacy_categories = {
        "Fixed Costs": "fixed",
        "Savings": "savings",
        "Investments": "investments",
        "Guilt Free Spending": "guilt_free",
        "Guilt Free": "guilt_free",
    }

    conn = get_connection()
    for legacy, category_id in legacy_categories.items():
        conn.execute(
            "UPDATE expenses SET category = ? WHERE category = ?",
            (category_id, legacy),
        )
    conn.commit()
    conn.close()


def validate_database_file(path):
    required_tables = {"months", "expenses", "scorecards", "scorecard_expenses"}
    try:
        conn = sqlite3.connect(path)
        quick_check = conn.execute("PRAGMA quick_check").fetchone()[0]
        if quick_check != "ok":
            return False
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        tables = {row[0] for row in rows}
        conn.close()
    except sqlite3.DatabaseError:
        return False

    return required_tables.issubset(tables)


def import_database_file(uploaded_file):
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_file:
        temp_path = Path(temp_file.name)
        uploaded_file.save(temp_file)

    try:
        if not validate_database_file(temp_path):
            raise ValueError("Uploaded file is not a valid FinanceTracker database")
        DATABASE_FOLDER.mkdir(exist_ok=True)
        shutil.copyfile(temp_path, DATABASE)
    finally:
        temp_path.unlink(missing_ok=True)

    initialize_database()


def get_current_month():

    today = datetime.today()

    label = f"{today.year}-{today.month:02d}"

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM months
        WHERE label = ?
    """, (label,))

    month = cursor.fetchone()

    if month is None:

        cursor.execute("""
            INSERT INTO months(label, month, year)
            VALUES(?,?,?)
        """, (
            label,
            today.month,
            today.year
        ))

        conn.commit()

        cursor.execute("""
            SELECT *
            FROM months
            WHERE label=?
        """, (label,))

        month = cursor.fetchone()

    conn.close()

    return month
