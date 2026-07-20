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


if __name__ == "__main__":
    app.run(debug=True)