import shutil
import sqlite3
import tempfile
from pathlib import Path
from datetime import date, datetime

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

        income_mode TEXT NOT NULL DEFAULT 'simple',

        income_period_duration REAL NOT NULL DEFAULT 1,

        income_period_unit TEXT NOT NULL DEFAULT 'month',

        manual_tax_rate REAL NOT NULL DEFAULT 0,

        gross_annual_income REAL,

        tax_country TEXT,

        tax_region_code TEXT,

        tax_year INTEGER,

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
        recurrence_interval INTEGER NOT NULL DEFAULT 1,
        recurrence_unit TEXT NOT NULL DEFAULT 'month',
        expense_date TEXT NOT NULL,

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
        income REAL NOT NULL DEFAULT 0,
        income_period_duration REAL NOT NULL DEFAULT 1,
        income_period_unit TEXT NOT NULL DEFAULT 'month',
        income_snapshot_present INTEGER NOT NULL DEFAULT 1,
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
        recurrence_interval INTEGER NOT NULL DEFAULT 1,
        recurrence_unit TEXT NOT NULL DEFAULT 'month',
        expense_date TEXT NOT NULL,
        FOREIGN KEY(scorecard_id)
            REFERENCES scorecards(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tax_rulesets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        country TEXT NOT NULL,
        region_name TEXT NOT NULL,
        region_code TEXT NOT NULL,
        tax_year INTEGER NOT NULL,
        source_url TEXT,
        basic_personal_credit_enabled INTEGER NOT NULL DEFAULT 0,
        basic_personal_credit_amount REAL NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(country, region_code, tax_year)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tax_brackets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ruleset_id INTEGER NOT NULL,
        lower_bound REAL NOT NULL,
        upper_bound REAL,
        rate REAL NOT NULL,
        FOREIGN KEY(ruleset_id) REFERENCES tax_rulesets(id) ON DELETE CASCADE
    )
    """)

    _ensure_column(cursor, "months", "income_mode", "TEXT NOT NULL DEFAULT 'simple'")
    _ensure_column(cursor, "months", "income_period_duration", "REAL NOT NULL DEFAULT 1")
    _ensure_column(cursor, "months", "income_period_unit", "TEXT NOT NULL DEFAULT 'month'")
    _ensure_column(cursor, "months", "manual_tax_rate", "REAL NOT NULL DEFAULT 0")
    _ensure_column(cursor, "months", "gross_annual_income", "REAL")
    _ensure_column(cursor, "months", "tax_country", "TEXT")
    _ensure_column(cursor, "months", "tax_region_code", "TEXT")
    _ensure_column(cursor, "months", "tax_year", "INTEGER")
    _ensure_column(cursor, "tax_rulesets", "basic_personal_credit_enabled", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(cursor, "tax_rulesets", "basic_personal_credit_amount", "REAL NOT NULL DEFAULT 0")
    _ensure_column(cursor, "expenses", "expense_date", "TEXT")
    _ensure_column(cursor, "scorecard_expenses", "expense_date", "TEXT")
    _ensure_column(cursor, "expenses", "recurrence_interval", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(cursor, "expenses", "recurrence_unit", "TEXT NOT NULL DEFAULT 'month'")
    _ensure_column(cursor, "expenses", "global_type", "TEXT")
    _ensure_column(cursor, "scorecard_expenses", "recurrence_interval", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(cursor, "scorecard_expenses", "recurrence_unit", "TEXT NOT NULL DEFAULT 'month'")
    _ensure_column(cursor, "scorecard_expenses", "global_type", "TEXT")
    _ensure_column(cursor, "scorecards", "income", "REAL NOT NULL DEFAULT 0")
    _ensure_column(cursor, "scorecards", "income_period_duration", "REAL NOT NULL DEFAULT 1")
    _ensure_column(cursor, "scorecards", "income_period_unit", "TEXT NOT NULL DEFAULT 'month'")
    _ensure_column(cursor, "scorecards", "income_snapshot_present", "INTEGER NOT NULL DEFAULT 0")
    cursor.execute(
        "UPDATE expenses SET expense_date = ? WHERE expense_date IS NULL OR expense_date = ''",
        (date.today().isoformat(),),
    )
    cursor.execute(
        "UPDATE scorecard_expenses SET expense_date = ? WHERE expense_date IS NULL OR expense_date = ''",
        (date.today().isoformat(),),
    )

    conn.commit()
    conn.close()
    migrate_categories()
    from services.income import seed_default_tax_rules
    seed_default_tax_rules()


def _ensure_column(cursor, table, column, definition):
    columns = [row[1] for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in columns:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


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
