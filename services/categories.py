import re
import uuid

from database import get_connection
from services.net_worth import restore_liability_payment


HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def get_category_config():
    conn = get_connection()
    rows = conn.execute("SELECT id, label, color, icon FROM categories ORDER BY display_order, id").fetchall()
    conn.close()
    return {row["id"]: {"label": row["label"], "color": row["color"], "icon": row["icon"]} for row in rows}


def _validate_category_details(label, color):
    label = (label or "").strip()
    color = (color or "").strip().upper()
    if not label:
        raise ValueError("Category title is required")
    if len(label) > 60:
        raise ValueError("Category title must be 60 characters or fewer")
    if not HEX_COLOR.fullmatch(color):
        raise ValueError("Color must be a six-digit hexadecimal code such as #15975D")
    return label, color


def create_category(label, color):
    label, color = _validate_category_details(label, color)
    category_id = f"custom_{uuid.uuid4().hex}"
    conn = get_connection()
    display_order = conn.execute("SELECT COALESCE(MAX(display_order), -1) + 1 FROM categories").fetchone()[0]
    conn.execute(
        "INSERT INTO categories(id, label, color, icon, display_order) VALUES(?,?,?,?,?)",
        (category_id, label, color, "tag-fill", display_order),
    )
    conn.commit()
    row = conn.execute("SELECT id, label, color, icon FROM categories WHERE id = ?", (category_id,)).fetchone()
    conn.close()
    return dict(row)


def update_category(category_id, label, color):
    label, color = _validate_category_details(label, color)

    conn = get_connection()
    cursor = conn.execute("UPDATE categories SET label = ?, color = ? WHERE id = ?", (label, color, category_id))
    if cursor.rowcount == 0:
        conn.close()
        raise ValueError("Unknown category")
    conn.execute("UPDATE scorecard_categories SET label = ?, color = ? WHERE category_id = ?", (label, color, category_id))
    conn.commit()
    row = conn.execute("SELECT id, label, color, icon FROM categories WHERE id = ?", (category_id,)).fetchone()
    conn.close()
    return dict(row)


def delete_category(category_id, month_id):
    conn = get_connection()
    category = conn.execute("SELECT label FROM categories WHERE id = ?", (category_id,)).fetchone()
    if category is None:
        conn.close()
        raise ValueError("Unknown category")
    expenses = conn.execute(
        "SELECT amount, liability_item_id, liability_payment_amount FROM expenses WHERE month_id = ? AND category = ?",
        (month_id, category_id),
    ).fetchall()
    for expense in expenses:
        restore_liability_payment(conn, expense["liability_item_id"], expense["liability_payment_amount"] or expense["amount"])
    returned = sum(float(expense["amount"]) for expense in expenses)
    conn.execute("DELETE FROM expenses WHERE month_id = ? AND category = ?", (month_id, category_id))
    conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    conn.commit()
    conn.close()
    return {"id": category_id, "label": category["label"], "deleted_expenses": len(expenses), "returned": returned}
