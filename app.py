from flask import Flask, render_template
import calendar

from database import (
    initialize_database,
    get_current_month
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


if __name__ == "__main__":
    app.run(debug=True)