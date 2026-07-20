from config import CATEGORY_CONFIG
from database import get_connection
from services.finance import category_totals, dashboard_summary


def update_income(month_id, income):
    conn = get_connection()
    conn.execute("UPDATE months SET income = ? WHERE id = ?", (income, month_id))
    conn.commit()
    conn.close()


def get_month_summary(month_id):
    return dashboard_summary(month_id)["summary"]


def get_category_totals(month_id):
    return category_totals(month_id)


def finalize_month(month_id):
    conn = get_connection()
    conn.execute("UPDATE months SET finalized = 1 WHERE id = ?", (month_id,))
    conn.commit()
    conn.close()


def category_options():
    return [
        {"id": category_id, **config}
        for category_id, config in CATEGORY_CONFIG.items()
    ]
