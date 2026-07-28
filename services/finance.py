from database import get_connection
from services.categories import get_category_config
from services.expenses import get_expenses, get_workspace_expenses
from services.global_balance import get_global_balance


def _empty_categories():
    category_config = get_category_config()
    return {
        category_id: {
            "id": category_id,
            "label": config["label"],
            "color": config["color"],
            "icon": config["icon"],
            "total": 0.0,
            "count": 0,
        }
        for category_id, config in category_config.items()
    }


def category_totals(month_id):
    categories = _empty_categories()
    for expense in get_workspace_expenses(month_id):
        category_id = expense["category"]
        if category_id in categories:
            categories[category_id]["total"] += float(expense["amount"])
            categories[category_id]["count"] += 1

    return categories


def _workspace_period():
    conn = get_connection()
    schedule = conn.execute("SELECT period_start, next_run FROM workspace_schedule WHERE id = 1").fetchone()
    conn.close()
    if schedule is None:
        return None
    return {
        "start": schedule["period_start"],
        "end": schedule["next_run"].split("T", 1)[0],
    }


def dashboard_summary(month_id):
    conn = get_connection()
    month = conn.execute("SELECT * FROM months WHERE id = ?", (month_id,)).fetchone()
    conn.close()

    expenses = get_workspace_expenses(month_id)
    spending = sum(float(expense["amount"]) for expense in expenses)
    global_draws = sum(
        float(expense["amount"])
        for expense in expenses
        if expense.get("global_type") == "draw"
    )
    recurring = sum(float(expense["amount"]) for expense in expenses if expense["recurring"])
    largest = min(expenses, key=lambda expense: (-float(expense["amount"]), expense["description"]), default=None)

    income = float(month["income"])
    spending = float(spending)
    # Global draws are funded by past reports, not this workspace's income.
    surplus = income - (spending - global_draws)
    categories = category_totals(month_id)

    return {
        "month": dict(month),
        "workspace_period": _workspace_period(),
        "summary": {
            "income": income,
            "spending": spending,
            "surplus": surplus,
            "recurring_total": float(recurring),
            "largest_expense": largest,
            "savings_rate": _rate(categories["savings"]["total"], income),
            "investment_rate": _rate(categories["investments"]["total"], income),
        },
        "categories": list(categories.values()),
        "expenses": expenses,
        "recurring_expenses": [expense for expense in get_expenses(month_id) if expense["recurring"]],
        "global_balance": get_global_balance(month_id),
    }


def _rate(amount, income):
    if income <= 0:
        return 0.0
    return round((amount / income) * 100, 1)
