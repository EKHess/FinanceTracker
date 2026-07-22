import calendar
import csv
from io import StringIO

from flask import Flask, Response, jsonify, render_template, request, send_file

from config import CATEGORY_CONFIG
import database
from database import get_current_month, import_database_file, initialize_database
from services.expenses import add_expense, delete_expense, get_expenses, update_expense
from services.finance import dashboard_summary
from services.months import get_category_totals, get_month_summary, update_income
from services.income import get_income_profile, get_tax_rulesets, save_income_profile
from services.scorecards import (
    add_scorecard_expense,
    create_scorecard,
    delete_scorecard,
    delete_scorecard_expense,
    get_scorecard,
    list_scorecards,
    update_scorecard_expense,
)


app = Flask(__name__)

initialize_database()


def _current_month_context():
    month = get_current_month()
    return month, calendar.month_name[month["month"]]


@app.route("/")
def dashboard():
    month, month_name = _current_month_context()
    return render_template(
        "dashboard.html",
        month=month,
        month_name=month_name,
        categories=CATEGORY_CONFIG,
    )


@app.route("/api/dashboard")
def api_dashboard():
    month = get_current_month()
    return jsonify(dashboard_summary(month["id"]))


@app.route("/api/summary")
def api_summary():
    month = get_current_month()
    return jsonify(get_month_summary(month["id"]))


@app.route("/api/income")
def api_income_profile():
    return jsonify(get_income_profile(get_current_month()["id"]))


@app.route("/api/income", methods=["POST"])
def api_income():
    data = request.get_json() or {}
    if set(data.keys()) <= {"income"}:
        update_income(get_current_month()["id"], float(data.get("income", 0)))
        return jsonify({"success": True})
    return jsonify(save_income_profile(get_current_month()["id"], data))


@app.route("/api/tax-rulesets")
def api_tax_rulesets():
    return jsonify(get_tax_rulesets())


@app.route("/api/tax-rulesets", methods=["POST"])
def api_create_tax_ruleset():
    data = request.get_json() or {}
    conn = database.get_connection()
    country = data.get("country", "Canada").strip()
    region_code = data.get("region_code", "").strip().upper()
    tax_year = int(data.get("tax_year", 2026))
    existing = conn.execute(
        "SELECT id FROM tax_rulesets WHERE country=? AND region_code=? AND tax_year=?",
        (country, region_code, tax_year),
    ).fetchone()
    if existing:
        ruleset_id = existing["id"]
        conn.execute(
            "UPDATE tax_rulesets SET region_name=?, source_url=? WHERE id=?",
            (data.get("region_name", "").strip(), data.get("source_url", ""), ruleset_id),
        )
        conn.execute("DELETE FROM tax_brackets WHERE ruleset_id=?", (ruleset_id,))
    else:
        cursor = conn.execute(
            "INSERT INTO tax_rulesets(country, region_name, region_code, tax_year, source_url) VALUES(?,?,?,?,?)",
            (country, data.get("region_name", "").strip(), region_code, tax_year, data.get("source_url", "")),
        )
        ruleset_id = cursor.lastrowid
    for bracket in data.get("brackets", []):
        conn.execute("INSERT INTO tax_brackets(ruleset_id, lower_bound, upper_bound, rate) VALUES(?,?,?,?)", (ruleset_id, bracket.get("lower_bound", 0), bracket.get("upper_bound"), bracket.get("rate", 0)))
    conn.commit(); conn.close()
    return jsonify({"success": True, "id": ruleset_id, "overwritten": bool(existing)}), 200 if existing else 201


@app.route("/api/tax-rulesets/<int:id>", methods=["PUT"])
def api_update_tax_ruleset(id):
    data = request.get_json() or {}
    conn = database.get_connection()
    conn.execute("UPDATE tax_rulesets SET country=?, region_name=?, region_code=?, tax_year=?, source_url=? WHERE id=?", (data.get("country", "Canada"), data.get("region_name", ""), data.get("region_code", ""), int(data.get("tax_year", 2026)), data.get("source_url", ""), id))
    conn.execute("DELETE FROM tax_brackets WHERE ruleset_id=?", (id,))
    for bracket in data.get("brackets", []):
        conn.execute("INSERT INTO tax_brackets(ruleset_id, lower_bound, upper_bound, rate) VALUES(?,?,?,?)", (id, bracket.get("lower_bound", 0), bracket.get("upper_bound"), bracket.get("rate", 0)))
    conn.commit(); conn.close()
    return jsonify({"success": True})


@app.route("/api/tax-rulesets/<int:id>", methods=["DELETE"])
def api_delete_tax_ruleset(id):
    conn = database.get_connection()
    conn.execute("DELETE FROM tax_brackets WHERE ruleset_id=?", (id,))
    conn.execute("DELETE FROM tax_rulesets WHERE id=?", (id,))
    conn.commit(); conn.close()
    return jsonify({"success": True})


@app.route("/api/categories")
def api_categories():
    month = get_current_month()
    return jsonify(get_category_totals(month["id"]))


@app.route("/api/expenses")
def api_expenses():
    month = get_current_month()
    return jsonify(get_expenses(month["id"], request.args.get("category")))


@app.route("/api/expenses", methods=["POST"])
def api_add_expense():
    data = request.get_json() or {}
    add_expense(
        get_current_month()["id"],
        data["description"],
        float(data["amount"]),
        data["category"],
        bool(data.get("recurring", False)),
    )
    return jsonify({"success": True})


@app.route("/api/expenses/<int:id>", methods=["PUT"])
def api_update_expense(id):
    data = request.get_json() or {}
    update_expense(
        id,
        data["description"],
        float(data["amount"]),
        data["category"],
        bool(data.get("recurring", False)),
    )
    return jsonify({"success": True})


@app.route("/api/expenses/<int:id>", methods=["DELETE"])
def api_delete_expense(id):
    delete_expense(id)
    return jsonify({"success": True})


@app.route("/api/scorecards")
def api_scorecards():
    return jsonify(list_scorecards())


@app.route("/api/scorecards/<int:id>")
def api_scorecard(id):
    scorecard = get_scorecard(id)
    if scorecard is None:
        return jsonify({"error": "Scorecard not found"}), 404
    return jsonify(scorecard)


@app.route("/api/scorecards", methods=["POST"])
def api_create_scorecard():
    data = request.get_json() or {}
    try:
        scorecard = create_scorecard(
            get_current_month()["id"],
            data.get("name", ""),
            data.get("start_date", ""),
            data.get("end_date", ""),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(scorecard), 201

@app.route("/api/scorecards/<int:id>", methods=["DELETE"])
def api_delete_scorecard(id):
    if not delete_scorecard(id):
        return jsonify({"error": "Scorecard not found"}), 404
    return jsonify({"success": True})


@app.route("/api/scorecards/<int:id>/expenses", methods=["POST"])
def api_add_scorecard_expense(id):
    data = request.get_json() or {}
    try:
        scorecard = add_scorecard_expense(
            id,
            data.get("description", ""),
            data.get("amount", 0),
            data.get("category", ""),
            bool(data.get("recurring", False)),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if scorecard is None:
        return jsonify({"error": "Scorecard not found"}), 404
    return jsonify(scorecard), 201


@app.route("/api/scorecards/<int:id>/expenses/<int:expense_id>", methods=["PUT"])
def api_update_scorecard_expense(id, expense_id):
    data = request.get_json() or {}
    try:
        scorecard = update_scorecard_expense(
            id,
            expense_id,
            data.get("description", ""),
            data.get("amount", 0),
            data.get("category", ""),
            bool(data.get("recurring", False)),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if scorecard is None:
        return jsonify({"error": "Scorecard charge not found"}), 404
    return jsonify(scorecard)


@app.route("/api/scorecards/<int:id>/expenses/<int:expense_id>", methods=["DELETE"])
def api_delete_scorecard_expense(id, expense_id):
    scorecard = delete_scorecard_expense(id, expense_id)
    if scorecard is None:
        return jsonify({"error": "Scorecard charge not found"}), 404
    return jsonify(scorecard)


@app.route("/api/scorecards/<int:id>/export.csv")
def api_export_scorecard_csv(id):
    scorecard = get_scorecard(id)
    if scorecard is None:
        return jsonify({"error": "Scorecard not found"}), 404

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Scorecard", scorecard["name"]])
    writer.writerow(["Start Date", scorecard["start_date"]])
    writer.writerow(["End Date", scorecard["end_date"]])
    writer.writerow(["Total Spending", scorecard["total_spending"]])
    writer.writerow([])
    writer.writerow(["Category", "Description", "Amount", "Recurring"])

    category_labels = {category["id"]: category["label"] for category in scorecard["categories"]}
    for expense in scorecard["expenses"]:
        writer.writerow([
            category_labels.get(expense["category"], expense["category"]),
            expense["description"],
            expense["amount"],
            "Yes" if expense["recurring"] else "No",
        ])

    filename = f"scorecard-{id}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/api/database/export")
def api_export_database():
    initialize_database()
    return send_file(database.DATABASE.resolve(), as_attachment=True, download_name="finance-tracker.db")


@app.route("/api/database/import", methods=["POST"])
def api_import_database():
    uploaded_file = request.files.get("database")
    if uploaded_file is None or uploaded_file.filename == "":
        return jsonify({"error": "Database file is required"}), 400
    try:
        import_database_file(uploaded_file)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"success": True})

if __name__ == "__main__":
    app.run(debug=True)
