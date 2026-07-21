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


@app.route("/api/income", methods=["POST"])
def api_income():
    data = request.get_json() or {}
    update_income(get_current_month()["id"], float(data.get("income", 0)))
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
