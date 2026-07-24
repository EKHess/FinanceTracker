import calendar
from datetime import date, timedelta

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


def occurs_in_period(expense, period_start, period_end):
    """Return whether an expense has an occurrence in [start, end)."""
    if not expense["recurring"]:
        return True
    occurrence = date.fromisoformat(expense["expense_date"])
    start = date.fromisoformat(period_start) if isinstance(period_start, str) else period_start
    end = date.fromisoformat(period_end) if isinstance(period_end, str) else period_end
    interval = int(expense["recurrence_interval"])
    preferred_day = occurrence.day
    while occurrence < start:
        occurrence = _next_occurrence(occurrence, interval, expense["recurrence_unit"], preferred_day)
    return occurrence < end


def get_workspace_expenses(month_id, category=None):
    """Return only charges that apply to the active configured workspace period."""
    expenses = get_expenses(month_id, category)
    conn = get_connection()
    schedule = conn.execute("SELECT period_start, next_run FROM workspace_schedule WHERE id = 1").fetchone()
    conn.close()
    if schedule is None:
        return expenses
    period_end = schedule["next_run"].split("T", 1)[0]
    return [expense for expense in expenses if occurs_in_period(expense, schedule["period_start"], period_end)]


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
    conn.execute(
        """
        INSERT INTO expenses (month_id, description, amount, category, recurring, expense_date, recurrence_interval, recurrence_unit)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
        ),
    )
    conn.commit()
    conn.close()


def update_expense(expense_id, description, amount, category, recurring, expense_date=None, recurrence_interval=1, recurrence_unit="month"):
    recurrence_interval, recurrence_unit = normalize_recurrence(recurring, recurrence_interval, recurrence_unit)
    conn = get_connection()
    conn.execute(
        """
        UPDATE expenses
        SET description = ?, amount = ?, category = ?, recurring = ?, expense_date = COALESCE(?, expense_date), recurrence_interval = ?, recurrence_unit = ?
        WHERE id = ?
        """,
        (description.strip(), amount, normalize_category(category), 1 if recurring else 0, normalize_expense_date(expense_date) if expense_date else None, recurrence_interval, recurrence_unit, expense_id),
    )
    conn.commit()
    conn.close()


def delete_expense(expense_id):
    conn = get_connection()
    conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    conn.commit()
    conn.close()
