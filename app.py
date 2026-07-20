from flask import Flask, jsonify, render_template, request
import calendar

from database import (
    initialize_database,
    get_current_month
)

from services.months import (
    get_month_summary,
    update_income,
)

from services.months import (
    get_month_summary,
    update_income,
    get_category_totals
)

from services.expenses import (
    get_expenses,
    add_expense
)

app = Flask(__name__)

initialize_database()


@app.route("/")
def dashboard():

    month = get_current_month()

    month_name = calendar.month_name[month["month"]]

    return render_template(
        "dashboard.html",
        month=month,
        month_name=month_name
    )

@app.route("/api/summary")
def api_summary():

    month = get_current_month()

    summary = get_month_summary(month["id"])

    return jsonify(summary)

@app.route("/api/income", methods=["POST"])
def api_income():

    data = request.get_json()

    income = float(data["income"])

    month = get_current_month()

    update_income(month["id"], income)

    return jsonify({"success": True})

@app.route("/api/categories")
def api_categories():

    month = get_current_month()

    return jsonify(
        get_category_totals(month["id"])
    )

@app.route("/api/expenses")
def api_expenses():

    month = get_current_month()

    category = request.args.get("category")

    return jsonify(
        get_expenses(
            month["id"],
            category
        )
    )

@app.route("/api/expenses", methods=["POST"])
def api_add_expense():

    data = request.get_json()

    month = get_current_month()

    add_expense(
        month["id"],
        data["description"],
        float(data["amount"]),
        data["category"],
        int(data["recurring"])
    )

    return jsonify({
        "success": True
    })


if __name__ == "__main__":
    app.run(debug=True)