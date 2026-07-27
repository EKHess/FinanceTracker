import calendar
from datetime import date, timedelta

from config import CATEGORY_CONFIG
from database import get_connection
from services.net_worth import apply_liability_payment, restore_liability_payment


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


def _add_months(value, count, preferred_day):
    month_index = value.year * 12 + value.month - 1 + count
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    return date(year, month, min(preferred_day, calendar.monthrange(year, month)[1]))


def _next_occurrence(value, interval, unit, preferred_day):
    if unit == "day":
        return value + timedelta(days=interval)
    if unit == "week":
        return value + timedelta(weeks=interval)
    if unit == "month":
        return _add_months(value, interval, preferred_day)
    return _add_months(value, interval * 12, preferred_day)


def occurrences_in_period(expense, period_start, period_end):
    """Return one expense entry for every occurrence in ``[start, end)``."""
    if not expense["recurring"]:
        return [expense]
    occurrence = date.fromisoformat(expense["expense_date"])
    start = date.fromisoformat(period_start) if isinstance(period_start, str) else period_start
    end = date.fromisoformat(period_end) if isinstance(period_end, str) else period_end
    interval = int(expense["recurrence_interval"])
    preferred_day = occurrence.day
    while occurrence < start:
        occurrence = _next_occurrence(occurrence, interval, expense["recurrence_unit"], preferred_day)

    occurrences = []
    while occurrence < end:
        item = expense.copy()
        item["expense_date"] = occurrence.isoformat()
        occurrences.append(item)
        occurrence = _next_occurrence(occurrence, interval, expense["recurrence_unit"], preferred_day)
    return occurrences


def occurs_in_period(expense, period_start, period_end):
    """Return whether an expense has at least one occurrence in ``[start, end)``."""
    return bool(occurrences_in_period(expense, period_start, period_end))


def get_workspace_expenses(month_id, category=None):
    """Return only charges that apply to the active configured workspace period."""
    expenses = get_expenses(month_id, category)
    conn = get_connection()
    schedule = conn.execute("SELECT period_start, next_run FROM workspace_schedule WHERE id = 1").fetchone()
    conn.close()
    if schedule is None:
        return expenses
    period_end = schedule["next_run"].split("T", 1)[0]
    return [
        occurrence
        for expense in expenses
        for occurrence in occurrences_in_period(expense, schedule["period_start"], period_end)
    ]


def normalize_expense_date(expense_date=None):
    value = expense_date or date.today().isoformat()
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError) as exc:
        raise ValueError("Expense date must be a valid ISO date") from exc


def normalize_recurrence(recurring, interval=1, unit="month"):
    if not recurring:
        return 1, "month"
    try:
        interval = int(interval)
    except (TypeError, ValueError) as exc:
        raise ValueError("Recurrence interval must be a whole number") from exc
    if interval < 1:
        raise ValueError("Recurrence interval must be at least 1")
    if unit not in {"day", "week", "month", "year"}:
        raise ValueError("Unknown recurrence unit")
    return interval, unit


def add_expense(month_id, description, amount, category, recurring, expense_date=None, recurrence_interval=1, recurrence_unit="month"):
    recurrence_interval, recurrence_unit = normalize_recurrence(recurring, recurrence_interval, recurrence_unit)
    conn = get_connection()
    try:
        payment = apply_liability_payment(conn, description, amount)
    except ValueError:
        conn.close()
        raise
    liability_item_id, liability_payment_amount = payment or (None, None)
    conn.execute(
        """
        INSERT INTO expenses (month_id, description, amount, category, recurring, expense_date, recurrence_interval, recurrence_unit, liability_item_id, liability_payment_amount)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            month_id,
            description.strip(),
            amount,
            normalize_category(category),
            1 if recurring else 0,
            normalize_expense_date(expense_date),
            recurrence_interval,
            recurrence_unit,
            liability_item_id,
            liability_payment_amount,
        ),
    )
    conn.commit()
    conn.close()


def update_expense(expense_id, description, amount, category, recurring, expense_date=None, recurrence_interval=1, recurrence_unit="month"):
    recurrence_interval, recurrence_unit = normalize_recurrence(recurring, recurrence_interval, recurrence_unit)
    conn = get_connection()
    previous = conn.execute("SELECT amount, liability_item_id, liability_payment_amount FROM expenses WHERE id = ?", (expense_id,)).fetchone()
    if previous is None:
        conn.close()
        raise ValueError("Expense not found")
    restore_liability_payment(conn, previous["liability_item_id"], previous["liability_payment_amount"] or previous["amount"])
    try:
        payment = apply_liability_payment(conn, description, amount)
    except ValueError:
        conn.close()
        raise
    liability_item_id, liability_payment_amount = payment or (None, None)
    conn.execute(
        """
        UPDATE expenses
        SET description = ?, amount = ?, category = ?, recurring = ?, expense_date = COALESCE(?, expense_date), recurrence_interval = ?, recurrence_unit = ?, liability_item_id = ?, liability_payment_amount = ?
        WHERE id = ?
        """,
        (description.strip(), amount, normalize_category(category), 1 if recurring else 0, normalize_expense_date(expense_date) if expense_date else None, recurrence_interval, recurrence_unit, liability_item_id, liability_payment_amount, expense_id),
    )
    conn.commit()
    conn.close()


def delete_expense(expense_id):
    conn = get_connection()
    expense = conn.execute("SELECT amount, liability_item_id, liability_payment_amount FROM expenses WHERE id = ?", (expense_id,)).fetchone()
    if expense:
        restore_liability_payment(conn, expense["liability_item_id"], expense["liability_payment_amount"] or expense["amount"])
    conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    conn.commit()
    conn.close()
