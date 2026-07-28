from database import get_connection
from services.categories import get_category_config
from services.expenses import normalize_category, normalize_expense_date, normalize_recurrence
from services.finance import dashboard_summary
from services.global_balance import get_global_balance
from services.net_worth import get_net_worth


def _scorecard_expenses(scorecard_id):
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id, description, amount, category, recurring, expense_date, recurrence_interval, recurrence_unit, global_type
        FROM scorecard_expenses
        WHERE scorecard_id = ?
        ORDER BY category, description
        """,
        (scorecard_id,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def _scorecard_category_config(scorecard_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT category_id, label, color, icon FROM scorecard_categories WHERE scorecard_id = ? ORDER BY display_order, category_id",
        (scorecard_id,),
    ).fetchall()
    conn.close()
    return {row["category_id"]: {"label": row["label"], "color": row["color"], "icon": row["icon"]} for row in rows}


def _categories_from_expenses(scorecard_id, expenses):
    category_config = _scorecard_category_config(scorecard_id)
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
        for category_id, config in category_config.items()
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
    scorecard["income"] = float(scorecard.get("income") or 0)
    scorecard["surplus"] = scorecard["income"] - scorecard["total_spending"]
    scorecard["global_balance"] = float(scorecard.get("global_balance") or 0)
    scorecard["net_worth"] = float(scorecard["net_worth"]) if scorecard.get("net_worth") is not None else None
    if include_expenses:
        expenses = _scorecard_expenses(scorecard["id"])
        scorecard["expenses"] = expenses
        category_config = _scorecard_category_config(scorecard["id"])
        scorecard["categories"] = _categories_from_expenses(scorecard["id"], expenses)
        category_with_most = max(scorecard["categories"], key=lambda category: category["total"], default=None)
        largest_expense = max(expenses, key=lambda expense: float(expense["amount"]), default=None)
        recurring = [expense for expense in expenses if expense["recurring"]]
        recurring_spending = sum(float(expense["amount"]) for expense in recurring)
        scorecard["summary"] = {
            "category_spending": {category["id"]: category["total"] for category in scorecard["categories"]},
            "largest_expense": ({**largest_expense, "category_label": category_config[largest_expense["category"]]["label"]} if largest_expense else None),
            "largest_category": ({"id": category_with_most["id"], "label": category_with_most["label"], "total": category_with_most["total"]} if category_with_most else None),
            "expense_count": len(expenses),
            "recurring_count": len(recurring),
            "recurring_percent": (recurring_spending / scorecard["total_spending"] * 100 if scorecard["total_spending"] else 0),
        }
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
        SELECT id, name, start_date, end_date, total_spending, income,
               income_period_duration, income_period_unit, income_snapshot_present, global_balance, net_worth, created_at
        FROM scorecards
        ORDER BY created_at DESC, id DESC
        """
    ).fetchall()
    conn.close()
    return [_serialize_scorecard(row) for row in rows]


def get_year_to_date_summary(year):
    """Aggregate saved report income and spending for a calendar year."""
    try:
        year = int(year)
    except (TypeError, ValueError) as exc:
        raise ValueError("Year must be a number") from exc
    if year < 1 or year > 9999:
        raise ValueError("Year is out of range")

    start_date = f"{year:04d}-01-01"
    end_date = f"{year:04d}-12-31"
    conn = get_connection()
    totals = conn.execute(
        """
        SELECT COALESCE(SUM(income), 0) AS income,
               COALESCE(SUM(total_spending), 0) AS spending
        FROM scorecards
        WHERE start_date BETWEEN ? AND ?
        """,
        (start_date, end_date),
    ).fetchone()
    saved_and_invested = conn.execute(
        """
        SELECT COALESCE(SUM(expense.amount), 0)
        FROM scorecard_expenses AS expense
        JOIN scorecards AS scorecard ON scorecard.id = expense.scorecard_id
        WHERE scorecard.start_date BETWEEN ? AND ?
          AND expense.category IN ('savings', 'investments')
        """,
        (start_date, end_date),
    ).fetchone()[0]
    conn.close()
    spending = float(totals["spending"])
    return {
        "year": year,
        "total_income": float(totals["income"]),
        "total_spending": spending,
        "saved_and_invested": float(saved_and_invested),
        "percent_saved_invested": float(saved_and_invested) / spending * 100 if spending else 0,
    }


def get_scorecard(scorecard_id):
    conn = get_connection()
    row = conn.execute(
        """
        SELECT id, name, start_date, end_date, total_spending, income,
               income_period_duration, income_period_unit, income_snapshot_present, global_balance, net_worth, created_at
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
    # Saving closes the active period, so its income-funded result becomes part
    # of the carried balance at the moment represented by this report.
    global_balance = get_global_balance(month_id)["balance"] + snapshot["summary"]["surplus"]
    net_worth = get_net_worth()["net_worth"]
    expenses = snapshot["expenses"]

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO scorecards (name, start_date, end_date, total_spending, income, income_period_duration, income_period_unit, income_snapshot_present, global_balance, net_worth)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        """,
        (name, start_date, end_date, snapshot["summary"]["spending"], snapshot["summary"]["income"],
         snapshot["month"]["income_period_duration"], snapshot["month"]["income_period_unit"], global_balance, net_worth),
    )
    scorecard_id = cursor.lastrowid

    cursor.executemany(
        "INSERT INTO scorecard_categories(scorecard_id, category_id, label, color, icon, display_order) VALUES(?,?,?,?,?,?)",
        [(scorecard_id, category["id"], category["label"], category["color"], category["icon"], index)
         for index, category in enumerate(snapshot["categories"])],
    )

    cursor.executemany(
        """
        INSERT INTO scorecard_expenses (scorecard_id, description, amount, category, recurring, expense_date, recurrence_interval, recurrence_unit, global_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                scorecard_id,
                expense["description"],
                float(expense["amount"]),
                expense["category"],
                1 if expense["recurring"] else 0,
                expense["expense_date"],
                expense["recurrence_interval"],
                expense["recurrence_unit"],
                expense.get("global_type"),
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
    conn.execute("DELETE FROM scorecard_categories WHERE scorecard_id = ?", (scorecard_id,))
    conn.execute("DELETE FROM scorecards WHERE id = ?", (scorecard_id,))
    conn.commit()
    conn.close()
    return True


def delete_all_scorecards():
    """Delete every saved report and its snapshot expenses atomically."""
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM scorecards").fetchone()[0]
    conn.execute("DELETE FROM scorecard_expenses")
    conn.execute("DELETE FROM scorecard_categories")
    conn.execute("DELETE FROM scorecards")
    conn.commit()
    conn.close()
    return int(count)


def add_scorecard_expense(scorecard_id, description, amount, category, recurring, expense_date=None, recurrence_interval=1, recurrence_unit="month"):
    description, amount, category = _validate_expense(description, amount, category)
    recurrence_interval, recurrence_unit = normalize_recurrence(recurring, recurrence_interval, recurrence_unit)
    conn = get_connection()
    if not _scorecard_exists(conn, scorecard_id):
        conn.close()
        return None
    conn.execute(
        """
        INSERT INTO scorecard_expenses (scorecard_id, description, amount, category, recurring, expense_date, recurrence_interval, recurrence_unit)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (scorecard_id, description, amount, category, 1 if recurring else 0, normalize_expense_date(expense_date), recurrence_interval, recurrence_unit),
    )
    _refresh_scorecard_total(conn, scorecard_id)
    conn.commit()
    conn.close()
    return get_scorecard(scorecard_id)


def update_scorecard_expense(scorecard_id, expense_id, description, amount, category, recurring, expense_date=None, recurrence_interval=1, recurrence_unit="month"):
    description, amount, category = _validate_expense(description, amount, category)
    recurrence_interval, recurrence_unit = normalize_recurrence(recurring, recurrence_interval, recurrence_unit)
    conn = get_connection()
    cursor = conn.execute(
        """
        UPDATE scorecard_expenses
        SET description = ?, amount = ?, category = ?, recurring = ?, expense_date = COALESCE(?, expense_date), recurrence_interval = ?, recurrence_unit = ?
        WHERE id = ? AND scorecard_id = ?
        """,
        (description, amount, category, 1 if recurring else 0, normalize_expense_date(expense_date) if expense_date else None, recurrence_interval, recurrence_unit, expense_id, scorecard_id),
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
