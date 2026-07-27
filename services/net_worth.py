import database


VALID_TYPES = {"asset", "liability"}


def _validate(item_type, name, amount):
    if item_type not in VALID_TYPES:
        raise ValueError("Item type must be asset or liability")
    name = str(name or "").strip()
    if not name:
        raise ValueError("Name is required")
    amount = float(amount)
    if amount < 0:
        raise ValueError("Amount cannot be negative")
    return name, amount


def get_net_worth():
    conn = database.get_connection()
    rows = [dict(row) for row in conn.execute("SELECT id, item_type, name, category, amount FROM net_worth_items ORDER BY id")]
    conn.close()
    assets = [row for row in rows if row["item_type"] == "asset"]
    liabilities = [row for row in rows if row["item_type"] == "liability"]
    total_assets = sum(row["amount"] for row in assets)
    total_liabilities = sum(row["amount"] for row in liabilities)
    return {"assets": assets, "liabilities": liabilities, "total_assets": total_assets,
            "total_liabilities": total_liabilities, "net_worth": total_assets - total_liabilities}


def add_item(item_type, name, category, amount):
    name, amount = _validate(item_type, name, amount)
    conn = database.get_connection()
    cursor = conn.execute("INSERT INTO net_worth_items(item_type, name, category, amount) VALUES(?,?,?,?)",
                          (item_type, name, str(category or "").strip(), amount))
    conn.commit()
    item_id = cursor.lastrowid
    conn.close()
    return item_id


def update_item(item_id, item_type, name, category, amount):
    name, amount = _validate(item_type, name, amount)
    conn = database.get_connection()
    cursor = conn.execute("UPDATE net_worth_items SET item_type=?, name=?, category=?, amount=? WHERE id=?",
                          (item_type, name, str(category or "").strip(), amount, item_id))
    conn.commit()
    conn.close()
    if not cursor.rowcount:
        raise ValueError("Item not found")


def delete_item(item_id):
    conn = database.get_connection()
    conn.execute("DELETE FROM net_worth_items WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
