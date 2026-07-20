from database import get_connection


def update_income(month_id, income):

    conn = get_connection()

    conn.execute(
        """
        UPDATE months
        SET income=?
        WHERE id=?
        """,
        (income, month_id),
    )

    conn.commit()
    conn.close()


def get_month_summary(month_id):

    conn = get_connection()

    month = conn.execute(
        """
        SELECT *
        FROM months
        WHERE id=?
        """,
        (month_id,),
    ).fetchone()

    spending = conn.execute(
        """
        SELECT COALESCE(SUM(amount),0)
        FROM expenses
        WHERE month_id=?
        """,
        (month_id,),
    ).fetchone()[0]

    conn.close()

    surplus = month["income"] - spending

    return {
        "income": month["income"],
        "spending": spending,
        "surplus": surplus,
    }

def get_category_totals(month_id):

    conn = get_connection()

    rows = conn.execute("""
        SELECT
            category,
            COALESCE(SUM(amount),0) AS total,
            COUNT(*) AS count
        FROM expenses
        WHERE month_id=?
        GROUP BY category
    """, (month_id,)).fetchall()

    conn.close()

    categories = {
        "Fixed Costs": {
            "total": 0,
            "count": 0
        },
        "Savings": {
            "total": 0,
            "count": 0
        },
        "Investments": {
            "total": 0,
            "count": 0
        },
        "Guilt Free Spending": {
            "total": 0,
            "count": 0
        }
    }

    for row in rows:
        categories[row["category"]] = {
            "total": row["total"],
            "count": row["count"]
        }

    return categories