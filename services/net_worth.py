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
    payment_rows = conn.execute(
        """
        SELECT id, liability_item_id, expense_date, liability_payment_amount
        FROM expenses
        WHERE liability_item_id IS NOT NULL AND liability_payment_amount IS NOT NULL
        ORDER BY expense_date DESC, id DESC
        """
    ).fetchall()
    conn.close()
    payments_by_liability = {}
    for payment in payment_rows:
        payments_by_liability.setdefault(payment["liability_item_id"], []).append({
            "id": payment["id"],
            "date": payment["expense_date"],
            "amount": payment["liability_payment_amount"],
        })
    for row in rows:
        if row["item_type"] == "liability":
            row["payment_history"] = payments_by_liability.get(row["id"], [])
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


def apply_liability_payment(conn, description, amount):
    """Deduct a payment from an exactly named liability and return its id."""
    liability = conn.execute(
        "SELECT id, amount FROM net_worth_items WHERE item_type='liability' AND name = ? COLLATE NOCASE ORDER BY id LIMIT 1",
        (str(description or "").strip(),),
    ).fetchone()
    if liability is None:
        return None
    payment_amount = float(amount)
    balance = float(liability["amount"])
    if payment_amount > balance:
        raise ValueError(
            f"This expense exceeds the current value of {description.strip()}. "
            f"The current liability balance is ${balance:,.2f}."
        )
    conn.execute(
        "UPDATE net_worth_items SET amount = amount - ? WHERE id = ?",
        (payment_amount, liability["id"]),
    )
    return liability["id"], payment_amount


def restore_liability_payment(conn, liability_item_id, amount):
    if liability_item_id is not None:
        conn.execute(
            "UPDATE net_worth_items SET amount = amount + ? WHERE id = ? AND item_type='liability'",
            (float(amount), liability_item_id),
        )
