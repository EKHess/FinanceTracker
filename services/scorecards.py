from config import CATEGORY_CONFIG
from database import get_connection
from services.expenses import normalize_category
from services.finance import dashboard_summary


def _scorecard_expenses(scorecard_id):
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id, description, amount, category, recurring
        FROM scorecard_expenses
        WHERE scorecard_id = ?
        ORDER BY category, description
        """,
        (scorecard_id,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def _categories_from_expenses(expenses):
    categories = {
        category_id: {
            "id": category_id,
            "label": config["label"],
            "color": config["color"],
            "icon": config["icon"],
            "total": 0.0,
            "count": 0,
            "expenses": [],
        }
        for category_id, config in CATEGORY_CONFIG.items()
    }

    for expense in expenses:
        category = categories.get(expense["category"])
        if category is None:
            continue
        category["total"] += float(expense["amount"])
        category["count"] += 1
        category["expenses"].append(expense)

    return list(categories.values())


def _serialize_scorecard(row, include_expenses=False):
    scorecard = dict(row)
    scorecard["total_spending"] = float(scorecard["total_spending"])
    if include_expenses:
        expenses = _scorecard_expenses(scorecard["id"])
        scorecard["expenses"] = expenses
        scorecard["categories"] = _categories_from_expenses(expenses)
    return scorecard


def _scorecard_exists(conn, scorecard_id):
    return conn.execute("SELECT 1 FROM scorecards WHERE id = ?", (scorecard_id,)).fetchone() is not None


def _refresh_scorecard_total(conn, scorecard_id):
    conn.execute(
        """
        UPDATE scorecards
        SET total_spending = (
            SELECT COALESCE(SUM(amount), 0)
            FROM scorecard_expenses
            WHERE scorecard_id = ?
        )
        WHERE id = ?
        """,
        (scorecard_id, scorecard_id),
    )


def _validate_expense(description, amount, category):
    description = (description or "").strip()
    if not description:
        raise ValueError("Charge description is required")
    try:
        amount = float(amount)
    except (TypeError, ValueError) as exc:
        raise ValueError("Charge amount must be a number") from exc
    if amount < 0:
        raise ValueError("Charge amount cannot be negative")
    return description, amount, normalize_category(category)


def list_scorecards():
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id, name, start_date, end_date, total_spending, created_at
        FROM scorecards
        ORDER BY created_at DESC, id DESC
        """
    ).fetchall()
    conn.close()
    return [_serialize_scorecard(row) for row in rows]


def get_scorecard(scorecard_id):
    conn = get_connection()
    row = conn.execute(
        """
        SELECT id, name, start_date, end_date, total_spending, created_at
        FROM scorecards
        WHERE id = ?
        """,
        (scorecard_id,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return _serialize_scorecard(row, include_expenses=True)


def create_scorecard(month_id, name, start_date, end_date):
    name = (name or "").strip()
    if not name:
        raise ValueError("Scorecard name is required")
    if not start_date or not end_date:
        raise ValueError("Start and end dates are required")
    if start_date > end_date:
        raise ValueError("Start date must be before end date")

    snapshot = dashboard_summary(month_id)
    expenses = snapshot["expenses"]

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO scorecards (name, start_date, end_date, total_spending)
        VALUES (?, ?, ?, ?)
        """,
        (name, start_date, end_date, snapshot["summary"]["spending"]),
    )
    scorecard_id = cursor.lastrowid

    cursor.executemany(
        """
        INSERT INTO scorecard_expenses (scorecard_id, description, amount, category, recurring)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                scorecard_id,
                expense["description"],
                float(expense["amount"]),
                expense["category"],
                1 if expense["recurring"] else 0,
            )
            for expense in expenses
        ],
    )

    cursor.execute(
        """
        DELETE FROM expenses
        WHERE month_id = ? AND recurring = 0
        """,
        (month_id,),
    )
    conn.commit()
    conn.close()

    return get_scorecard(scorecard_id)


def delete_scorecard(scorecard_id):
    conn = get_connection()
    if not _scorecard_exists(conn, scorecard_id):
        conn.close()
        return False
    conn.execute("DELETE FROM scorecard_expenses WHERE scorecard_id = ?", (scorecard_id,))
    conn.execute("DELETE FROM scorecards WHERE id = ?", (scorecard_id,))
    conn.commit()
    conn.close()
    return True


def add_scorecard_expense(scorecard_id, description, amount, category, recurring):
    description, amount, category = _validate_expense(description, amount, category)
    conn = get_connection()
    if not _scorecard_exists(conn, scorecard_id):
        conn.close()
        return None
    conn.execute(
        """
        INSERT INTO scorecard_expenses (scorecard_id, description, amount, category, recurring)
        VALUES (?, ?, ?, ?, ?)
        """,
        (scorecard_id, description, amount, category, 1 if recurring else 0),
    )
    _refresh_scorecard_total(conn, scorecard_id)
    conn.commit()
    conn.close()
    return get_scorecard(scorecard_id)


def update_scorecard_expense(scorecard_id, expense_id, description, amount, category, recurring):
    description, amount, category = _validate_expense(description, amount, category)
    conn = get_connection()
    cursor = conn.execute(
        """
        UPDATE scorecard_expenses
        SET description = ?, amount = ?, category = ?, recurring = ?
        WHERE id = ? AND scorecard_id = ?
        """,
        (description, amount, category, 1 if recurring else 0, expense_id, scorecard_id),
    )
    if cursor.rowcount == 0:
        conn.close()
        return None
    _refresh_scorecard_total(conn, scorecard_id)
    conn.commit()
    conn.close()
    return get_scorecard(scorecard_id)


def delete_scorecard_expense(scorecard_id, expense_id):
    conn = get_connection()
    cursor = conn.execute(
        "DELETE FROM scorecard_expenses WHERE id = ? AND scorecard_id = ?",
        (expense_id, scorecard_id),
    )
    if cursor.rowcount == 0:
        conn.close()
        return None
    _refresh_scorecard_total(conn, scorecard_id)
    conn.commit()
    conn.close()
    return get_scorecard(scorecard_id)
