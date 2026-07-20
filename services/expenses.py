from config import CATEGORY_CONFIG
from database import get_connection


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


def add_expense(month_id, description, amount, category, recurring):
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO expenses (month_id, description, amount, category, recurring)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            month_id,
            description.strip(),
            amount,
            normalize_category(category),
            1 if recurring else 0,
        ),
    )
    conn.commit()
    conn.close()


def update_expense(expense_id, description, amount, category, recurring):
    conn = get_connection()
    conn.execute(
        """
        UPDATE expenses
        SET description = ?, amount = ?, category = ?, recurring = ?
        WHERE id = ?
        """,
        (description.strip(), amount, normalize_category(category), 1 if recurring else 0, expense_id),
    )
    conn.commit()
    conn.close()


def delete_expense(expense_id):
    conn = get_connection()
    conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    conn.commit()
    conn.close()
