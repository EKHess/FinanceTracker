import calendar

from flask import Flask, jsonify, render_template, request

from config import CATEGORY_CONFIG
from database import get_current_month, initialize_database
from services.expenses import add_expense, delete_expense, get_expenses, update_expense
from services.finance import dashboard_summary
from services.months import get_category_totals, get_month_summary, update_income
from services.scorecards import create_scorecard, get_scorecard, list_scorecards

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


if __name__ == "__main__":
    app.run(debug=True)
