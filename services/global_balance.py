from datetime import date

from database import get_connection
from services.expenses import get_workspace_expenses, normalize_category
from services.net_worth import apply_liability_payment


def get_global_balance(month_id):
    """Return saved report balances adjusted by active global allocations.

    Ordinary income and spending in the active workspace do not become part of
    the global balance until the workspace is saved as a financial report.
    """
    conn = get_connection()
    historical = conn.execute(
        "SELECT COALESCE(SUM(income - total_spending), 0) FROM scorecards"
    ).fetchone()[0]
    pledge = conn.execute(
        "SELECT id, amount, category FROM expenses WHERE month_id = ? AND global_type = 'pledge' LIMIT 1",
        (month_id,),
    ).fetchone()
    draws = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE month_id = ? AND global_type = 'draw'",
        (month_id,),
    ).fetchone()[0]
    conn.close()
    pledge_amount = float(pledge["amount"]) if pledge else 0.0
    # A pledge transfers active income into a saved deficit, while a draw
    # spends previously saved surplus. Neither operation changes the active
    # workspace's otherwise-unspent income.
    current_contribution = pledge_amount - float(draws)
    balance = float(historical) + current_contribution
    return {
        "balance": round(balance, 2),
        "status": "surplus" if balance >= 0 else "deficit",
        "historical_balance": round(float(historical), 2),
        "current_contribution": round(current_contribution, 2),
        "pledge": round(pledge_amount, 2),
        "pledge_expense_id": pledge["id"] if pledge else None,
        "pledge_category": pledge["category"] if pledge else "savings",
        "drawn_this_period": round(float(draws), 2),
    }


def save_deficit_pledge(month_id, amount, category="savings"):
    amount = float(amount)
    category = normalize_category(category)
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
        conn.execute(
            "UPDATE expenses SET amount = ?, category = ?, expense_date = ? WHERE id = ?",
            (amount, category, date.today().isoformat(), existing["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO expenses (month_id, description, amount, category, recurring, expense_date, recurrence_interval, recurrence_unit, global_type) VALUES (?, ?, ?, ?, 0, ?, 1, 'month', 'pledge')",
            (month_id, "Global deficit payoff", amount, category, date.today().isoformat()),
        )
    conn.commit()
    conn.close()
    return get_global_balance(month_id)


def draw_from_surplus(month_id, amount, category, description="Global surplus allocation"):
    amount = float(amount)
    category = normalize_category(category)
    state = get_global_balance(month_id)
    if amount <= 0:
        raise ValueError("Draw amount must be greater than zero")
    if state["balance"] <= 0 or amount > state["balance"]:
        raise ValueError("Draw cannot exceed the available global surplus")
    conn = get_connection()
    clean_description = (description or "Global surplus allocation").strip()
    try:
        payment = apply_liability_payment(conn, clean_description, amount)
    except ValueError:
        conn.close()
        raise
    liability_item_id, liability_payment_amount = payment or (None, None)
    conn.execute(
        "INSERT INTO expenses (month_id, description, amount, category, recurring, expense_date, recurrence_interval, recurrence_unit, global_type, liability_item_id, liability_payment_amount) VALUES (?, ?, ?, ?, 0, ?, 1, 'month', 'draw', ?, ?)",
        (month_id, clean_description, amount, category, date.today().isoformat(), liability_item_id, liability_payment_amount),
    )
    conn.commit()
    conn.close()
    return get_global_balance(month_id)
