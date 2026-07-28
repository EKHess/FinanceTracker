import re

from database import get_connection


HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def get_category_config():
    conn = get_connection()
    rows = conn.execute("SELECT id, label, color, icon FROM categories ORDER BY display_order, id").fetchall()
    conn.close()
    return {row["id"]: {"label": row["label"], "color": row["color"], "icon": row["icon"]} for row in rows}


def update_category(category_id, label, color):
    label = (label or "").strip()
    color = (color or "").strip().upper()
    if not label:
        raise ValueError("Category title is required")
    if len(label) > 60:
        raise ValueError("Category title must be 60 characters or fewer")
    if not HEX_COLOR.fullmatch(color):
        raise ValueError("Color must be a six-digit hexadecimal code such as #15975D")

    conn = get_connection()
    cursor = conn.execute("UPDATE categories SET label = ?, color = ? WHERE id = ?", (label, color, category_id))
    if cursor.rowcount == 0:
        conn.close()
        raise ValueError("Unknown category")
    conn.commit()
    row = conn.execute("SELECT id, label, color, icon FROM categories WHERE id = ?", (category_id,)).fetchone()
    conn.close()
    return dict(row)
