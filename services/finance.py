from config import CATEGORY_CONFIG
from database import get_connection
from services.expenses import get_expenses
from services.global_balance import get_global_balance


def _empty_categories():
    return {
        category_id: {
            "id": category_id,
            "label": config["label"],
            "color": config["color"],
            "icon": config["icon"],
            "total": 0.0,
            "count": 0,
        }
        for category_id, config in CATEGORY_CONFIG.items()
    }


def category_totals(month_id):
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT category, COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count
        FROM expenses
        WHERE month_id = ?
        GROUP BY category
        """,
        (month_id,),
    ).fetchall()
    conn.close()

    categories = _empty_categories()
    for row in rows:
        category_id = row["category"]
        if category_id in categories:
            categories[category_id]["total"] = float(row["total"])
            categories[category_id]["count"] = int(row["count"])

    return categories


def dashboard_summary(month_id):
    conn = get_connection()
    month = conn.execute("SELECT * FROM months WHERE id = ?", (month_id,)).fetchone()
    spending = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE month_id = ?",
        (month_id,),
    ).fetchone()[0]
    recurring = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE month_id = ? AND recurring = 1",
        (month_id,),
    ).fetchone()[0]
    largest = conn.execute(
        """
        SELECT id, description, amount, category, recurring
        FROM expenses
        WHERE month_id = ?
        ORDER BY amount DESC, description ASC
        LIMIT 1
        """,
        (month_id,),
    ).fetchone()
    conn.close()

    income = float(month["income"])
    spending = float(spending)
    surplus = income - spending
    categories = category_totals(month_id)

    return {
        "month": dict(month),
        "summary": {
            "income": income,
            "spending": spending,
            "surplus": surplus,
            "recurring_total": float(recurring),
            "largest_expense": dict(largest) if largest else None,
            "savings_rate": _rate(categories["savings"]["total"], income),
            "investment_rate": _rate(categories["investments"]["total"], income),
        },
        "categories": list(categories.values()),
        "expenses": get_expenses(month_id),
        "global_balance": get_global_balance(month_id),
    }


def _rate(amount, income):
    if income <= 0:
        return 0.0
    return round((amount / income) * 100, 1)
