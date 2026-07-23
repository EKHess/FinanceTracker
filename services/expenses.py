from config import CATEGORY_CONFIG
from database import get_connection
from datetime import date


def normalize_category(category):
    if category in CATEGORY_CONFIG:
        return category

    for category_id, config in CATEGORY_CONFIG.items():
        if category == config["label"]:
            return category_id

    raise ValueError("Unknown expense category")


def get_expenses(month_id, category=None):
    conn = get_connection()
    params = [month_id]
    where = "WHERE month_id = ?"

    if category:
        where += " AND category = ?"
        params.append(normalize_category(category))

    rows = conn.execute(
        f"""
        SELECT *
        FROM expenses
        {where}
        ORDER BY category, description
        """,
        params,
    ).fetchall()
    conn.close()

    return [dict(row) for row in rows]


def normalize_expense_date(expense_date=None):
    value = expense_date or date.today().isoformat()
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError) as exc:
        raise ValueError("Expense date must be a valid ISO date") from exc


def add_expense(month_id, description, amount, category, recurring, expense_date=None):
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO expenses (month_id, description, amount, category, recurring, expense_date)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            month_id,
            description.strip(),
            amount,
            normalize_category(category),
            1 if recurring else 0,
            normalize_expense_date(expense_date),
        ),
    )
    conn.commit()
    conn.close()


def update_expense(expense_id, description, amount, category, recurring, expense_date=None):
    conn = get_connection()
    conn.execute(
        """
        UPDATE expenses
        SET description = ?, amount = ?, category = ?, recurring = ?, expense_date = COALESCE(?, expense_date)
        WHERE id = ?
        """,
        (description.strip(), amount, normalize_category(category), 1 if recurring else 0, normalize_expense_date(expense_date) if expense_date else None, expense_id),
    )
    conn.commit()
    conn.close()


def delete_expense(expense_id):
    conn = get_connection()
    conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    conn.commit()
    conn.close()
