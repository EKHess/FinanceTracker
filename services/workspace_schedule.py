import calendar
from datetime import datetime, timedelta

from database import get_connection, get_current_month
from services.scorecards import create_scorecard


VALID_UNITS = {"day", "week", "month"}


def _add_months(value, count, preferred_day=None):
    month_index = value.year * 12 + value.month - 1 + count
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    day = min(preferred_day or value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _advance(value, amount, unit, monthly_day=None):
    if unit == "day":
        return value + timedelta(days=amount)
    if unit == "week":
        return value + timedelta(weeks=amount)
    return _add_months(value, amount, monthly_day)


def _next_monthly(now, day, hour, minute):
    candidate = now.replace(day=min(day, calendar.monthrange(now.year, now.month)[1]), hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate = _add_months(candidate, 1, day)
    return candidate


def _serialize(row):
    result = dict(row)
    result["next_run"] = datetime.fromisoformat(result["next_run"]).isoformat(timespec="minutes")
    return result


def get_workspace_schedule(now=None):
    now = now or datetime.now()
    conn = get_connection()
    row = conn.execute("SELECT * FROM workspace_schedule WHERE id = 1").fetchone()
    if row is None:
        next_run = _next_monthly(now, 1, 0, 0)
        conn.execute(
            "INSERT INTO workspace_schedule (id, period_start, next_run) VALUES (1, ?, ?)",
            (now.date().isoformat(), next_run.isoformat(timespec="minutes")),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM workspace_schedule WHERE id = 1").fetchone()
    conn.close()
    return _serialize(row)


def save_workspace_schedule(data, now=None):
    now = now or datetime.now()
    mode = data.get("mode")
    if mode not in {"monthly", "interval"}:
        raise ValueError("Choose a monthly or interval schedule")
    try:
        day = int(data.get("monthly_day", 1))
        amount = int(data.get("interval_value", 1))
    except (TypeError, ValueError):
        raise ValueError("Schedule values must be whole numbers")
    unit = data.get("interval_unit", "day")
    if not 1 <= day <= 31 or amount < 1 or unit not in VALID_UNITS:
        raise ValueError("Enter a valid workspace period")
    try:
        hour, minute = (int(part) for part in data.get("time_of_day", "00:00").split(":"))
    except (AttributeError, TypeError, ValueError):
        raise ValueError("Enter a valid time")
    if not 0 <= hour <= 24 or not 0 <= minute <= 59 or (hour == 24 and minute != 0):
        raise ValueError("Time must be between 00:00 and 24:00")
    calculation_hour = 0 if hour == 24 else hour
    base = now + timedelta(days=1) if hour == 24 else now
    if mode == "monthly":
        next_run = _next_monthly(base, day, calculation_hour, minute)
    else:
        anchor = now.replace(hour=calculation_hour, minute=minute, second=0, microsecond=0)
        if hour == 24:
            anchor += timedelta(days=1)
        next_run = _advance(anchor, amount, unit)
    conn = get_connection()
    conn.execute("""
        INSERT INTO workspace_schedule (id, mode, monthly_day, interval_value, interval_unit, time_of_day, period_start, next_run)
        VALUES (1, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET mode=excluded.mode, monthly_day=excluded.monthly_day,
          interval_value=excluded.interval_value, interval_unit=excluded.interval_unit,
          time_of_day=excluded.time_of_day, period_start=excluded.period_start,
          next_run=excluded.next_run, updated_at=CURRENT_TIMESTAMP
    """, (mode, day, amount, unit, f"{hour:02d}:{minute:02d}", now.date().isoformat(), next_run.isoformat(timespec="minutes")))
    conn.commit(); conn.close()
    return get_workspace_schedule(now)


def process_due_workspace(now=None):
    now = now or datetime.now()
    schedule = get_workspace_schedule(now)
    next_run = datetime.fromisoformat(schedule["next_run"])
    if next_run > now:
        return None
    start = schedule["period_start"]
    end = next_run.date().isoformat()
    name = f"Financial Report · {start} to {end}"
    # Report creation and schedule advancement are intentionally recoverable.
    # If power was lost after the report committed but before the schedule was
    # advanced, do not create a second report on the next launch.
    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM scorecards WHERE start_date = ? AND end_date = ? AND name = ? ORDER BY id LIMIT 1",
        (start, end, name),
    ).fetchone()
    conn.close()
    if existing:
        from services.scorecards import get_scorecard
        report = get_scorecard(existing["id"])
    else:
        report = create_scorecard(get_current_month()["id"], name, start, end)
    if schedule["mode"] == "monthly":
        following = _add_months(next_run, 1, schedule["monthly_day"])
    else:
        following = _advance(next_run, schedule["interval_value"], schedule["interval_unit"])
    while following <= now:
        following = _add_months(following, 1, schedule["monthly_day"]) if schedule["mode"] == "monthly" else _advance(following, schedule["interval_value"], schedule["interval_unit"])
    conn = get_connection()
    conn.execute("UPDATE workspace_schedule SET period_start=?, next_run=? WHERE id=1", (end, following.isoformat(timespec="minutes")))
    conn.commit(); conn.close()
    return report
