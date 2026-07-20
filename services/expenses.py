from database import get_connection


def get_expenses(month_id, category=None):

    conn = get_connection()

    if category:

        rows = conn.execute(
            """
            SELECT *
            FROM expenses
            WHERE month_id=?
            AND category=?
            ORDER BY description
            """,
            (month_id, category)
        ).fetchall()

    else:

        rows = conn.execute(
            """
            SELECT *
            FROM expenses
            WHERE month_id=?
            ORDER BY category, description
            """,
            (month_id,)
        ).fetchall()

    conn.close()

    return [dict(row) for row in rows]

def add_expense(
    month_id,
    description,
    amount,
    category,
    recurring
):

    conn = get_connection()

    conn.execute(
        """
        INSERT INTO expenses
        (
            month_id,
            description,
            amount,
            category,
            recurring
        )
        VALUES
        (?,?,?,?,?)
        """,
        (
            month_id,
            description,
            amount,
            category,
            recurring
        )
    )

    conn.commit()
    conn.close()