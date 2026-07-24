from datetime import date

from config import CATEGORY_CONFIG
from database import get_connection
from services.expenses import get_workspace_expenses


def get_global_balance(month_id):
    """Return the sum of every saved and active workspace surplus or deficit."""
    conn = get_connection()
    historical = conn.execute(
        "SELECT COALESCE(SUM(income - total_spending), 0) FROM scorecards"
    ).fetchone()[0]
    month = conn.execute("SELECT income FROM months WHERE id = ?", (month_id,)).fetchone()
    current_spending = sum(float(expense["amount"]) for expense in get_workspace_expenses(month_id))
    pledge = conn.execute(
        "SELECT id, amount FROM expenses WHERE month_id = ? AND global_type = 'pledge' LIMIT 1",
        (month_id,),
    ).fetchone()
    draws = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE month_id = ? AND global_type = 'draw'",
        (month_id,),
    ).fetchone()[0]
    conn.close()
    income = float(month["income"]) if month else 0.0
    pledge_amount = float(pledge["amount"]) if pledge else 0.0
    current_contribution = income - float(current_spending)
    balance = float(historical) + current_contribution
    return {
        "balance": round(balance, 2),
        "status": "surplus" if balance >= 0 else "deficit",
        "historical_balance": round(float(historical), 2),
        "current_contribution": round(current_contribution, 2),
        "pledge": round(pledge_amount, 2),
        "pledge_expense_id": pledge["id"] if pledge else None,
        "drawn_this_period": round(float(draws), 2),
    }


def save_deficit_pledge(month_id, amount):
    amount = float(amount)
    state = get_global_balance(month_id)
    if amount <= 0:
        raise ValueError("Pledge must be greater than zero")
    conn = get_connection()
    month = conn.execute("SELECT income FROM months WHERE id = ?", (month_id,)).fetchone()
    non_pledge = sum(
        float(expense["amount"])
        for expense in get_workspace_expenses(month_id)
        if expense.get("global_type") != "pledge"
    )
    available = max(float(month["income"]) - float(non_pledge), 0)
    balance_before_pledge = state["balance"] + state["pledge"]
    if balance_before_pledge >= 0:
        conn.close()
        raise ValueError("A pledge can only be made while the global balance is in deficit")
    if amount > available:
        conn.close()
        raise ValueError("Pledge cannot exceed this period's unallocated income")
    if amount > abs(balance_before_pledge):
        conn.close()
        raise ValueError("Pledge cannot exceed the remaining global deficit")
    existing = conn.execute(
        "SELECT id FROM expenses WHERE month_id = ? AND global_type = 'pledge' LIMIT 1", (month_id,)
    ).fetchone()
    if existing:
        conn.execute("UPDATE expenses SET amount = ?, expense_date = ? WHERE id = ?", (amount, date.today().isoformat(), existing["id"]))
    else:
        conn.execute(
            "INSERT INTO expenses (month_id, description, amount, category, recurring, expense_date, recurrence_interval, recurrence_unit, global_type) VALUES (?, ?, ?, 'savings', 0, ?, 1, 'month', 'pledge')",
            (month_id, "Global deficit payoff", amount, date.today().isoformat()),
        )
    conn.commit()
    conn.close()
    return get_global_balance(month_id)


def draw_from_surplus(month_id, amount, category, description="Global surplus allocation"):
    amount = float(amount)
    state = get_global_balance(month_id)
    if amount <= 0:
        raise ValueError("Draw amount must be greater than zero")
    if state["balance"] <= 0 or amount > state["balance"]:
        raise ValueError("Draw cannot exceed the available global surplus")
    if category not in CATEGORY_CONFIG:
        raise ValueError("Unknown expense category")
    conn = get_connection()
    conn.execute(
        "INSERT INTO expenses (month_id, description, amount, category, recurring, expense_date, recurrence_interval, recurrence_unit, global_type) VALUES (?, ?, ?, ?, 0, ?, 1, 'month', 'draw')",
        (month_id, (description or "Global surplus allocation").strip(), amount, category, date.today().isoformat()),
    )
    conn.commit()
    conn.close()
    return get_global_balance(month_id)
