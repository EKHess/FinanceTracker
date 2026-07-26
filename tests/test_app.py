import importlib
from datetime import datetime


def test_dashboard_payload_uses_category_ids(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    import database
    import app as app_module

    importlib.reload(database)
    importlib.reload(app_module)

    client = app_module.app.test_client()
    response = client.get("/api/dashboard")

    assert response.status_code == 200
    payload = response.get_json()
    assert {category["id"] for category in payload["categories"]} == {
        "fixed",
        "savings",
        "investments",
        "guilt_free",
    }
    assert payload["summary"]["income"] == 0


def test_workspace_schedule_can_be_customized_and_creates_due_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import database
    import app as app_module
    import services.workspace_schedule as schedule_service
    importlib.reload(database)
    importlib.reload(schedule_service)
    importlib.reload(app_module)
    client = app_module.app.test_client()

    response = client.put("/api/workspace-schedule", json={
        "mode": "interval", "interval_value": 2, "interval_unit": "week",
        "monthly_day": 25, "time_of_day": "24:00",
    })
    assert response.status_code == 200
    assert response.get_json()["time_of_day"] == "24:00"

    conn = database.get_connection()
    conn.execute("UPDATE workspace_schedule SET period_start='2026-07-01', next_run='2026-07-15T12:00'")
    conn.commit(); conn.close()
    report = schedule_service.process_due_workspace(datetime(2026, 7, 15, 12, 1))
    assert report["name"] == "Financial Report · 2026-07-01 to 2026-07-15"
    assert report["start_date"] == "2026-07-01"
    assert report["end_date"] == "2026-07-15"


def test_expense_crud_updates_dashboard(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    import database
    import app as app_module

    importlib.reload(database)
    importlib.reload(app_module)

    client = app_module.app.test_client()
    assert client.post("/api/income", json={"income": 1000}).status_code == 200
    assert client.post(
        "/api/expenses",
        json={
            "description": "Rent",
            "amount": 400,
            "category": "fixed",
            "recurring": True,
            "recurrence_interval": 2,
            "recurrence_unit": "week",
        },
    ).status_code == 200

    dashboard = client.get("/api/dashboard").get_json()
    assert dashboard["summary"]["spending"] == 400
    assert dashboard["summary"]["surplus"] == 600
    assert dashboard["summary"]["recurring_total"] == 400
    assert dashboard["expenses"][0]["recurrence_interval"] == 2
    assert dashboard["expenses"][0]["recurrence_unit"] == "week"

    expense_id = dashboard["expenses"][0]["id"]
    assert client.put(
        f"/api/expenses/{expense_id}",
        json={
            "description": "Rent",
            "amount": 450,
            "category": "fixed",
            "recurring": True,
            "recurrence_interval": 3,
            "recurrence_unit": "month",
        },
    ).status_code == 200
    assert client.delete(f"/api/expenses/{expense_id}").status_code == 200
    assert client.get("/api/dashboard").get_json()["summary"]["spending"] == 0


def test_global_deficit_pledge_is_editable_highlighted_savings(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import database
    import app as app_module
    importlib.reload(database)
    importlib.reload(app_module)
    client = app_module.app.test_client()

    client.post("/api/income", json={"income": 100})
    client.post("/api/expenses", json={"description": "Emergency", "amount": 250, "category": "fixed"})
    client.post("/api/scorecards", json={"name": "Past term", "start_date": "2026-01-01", "end_date": "2026-01-31"})
    assert client.get("/api/global-balance").get_json()["balance"] == -50

    assert client.post("/api/global-balance/pledge", json={"amount": 30}).status_code == 200
    updated = client.post("/api/global-balance/pledge", json={"amount": 50})
    assert updated.status_code == 200
    assert updated.get_json()["balance"] == -100
    expenses = client.get("/api/expenses").get_json()
    pledge = next(expense for expense in expenses if expense["global_type"] == "pledge")
    assert pledge["category"] == "savings"
    assert pledge["amount"] == 50


def test_global_surplus_draw_is_capped_and_allocated_to_category(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import database
    import app as app_module
    importlib.reload(database)
    importlib.reload(app_module)
    client = app_module.app.test_client()
    client.post("/api/income", json={"income": 500})

    response = client.post("/api/global-balance/draw", json={"amount": 125, "category": "guilt_free", "description": "Weekend away"})
    assert response.status_code == 200
    assert response.get_json()["balance"] == 375
    draw = client.get("/api/expenses").get_json()[0]
    assert draw["global_type"] == "draw"
    assert draw["category"] == "guilt_free"
    assert client.post("/api/global-balance/draw", json={"amount": 376, "category": "fixed"}).status_code == 400


def test_global_balance_is_exact_sum_of_saved_and_current_results(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import database
    import app as app_module
    importlib.reload(database)
    importlib.reload(app_module)
    client = app_module.app.test_client()

    # Saved surplus: 1,000 - 600 = +400.
    client.post("/api/income", json={"income": 1000})
    client.post("/api/expenses", json={"description": "First term", "amount": 600, "category": "fixed"})
    client.post("/api/scorecards", json={"name": "Saved surplus", "start_date": "2026-01-01", "end_date": "2026-01-31"})

    # Saved deficit: 1,000 - 1,250 = -250.
    client.post("/api/expenses", json={"description": "Second term", "amount": 1250, "category": "fixed"})
    client.post("/api/scorecards", json={"name": "Saved deficit", "start_date": "2026-02-01", "end_date": "2026-02-28"})

    # Current surplus: 1,000 - 900 = +100. Global: 400 - 250 + 100 = 250.
    client.post("/api/expenses", json={"description": "Current term", "amount": 900, "category": "fixed"})
    state = client.get("/api/global-balance").get_json()
    assert state["historical_balance"] == 150
    assert state["current_contribution"] == 100
    assert state["balance"] == 250
    assert client.get("/api/dashboard").get_json()["global_balance"] == state


def test_expenses_store_default_and_explicit_dates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    import database
    import app as app_module
    from datetime import date

    importlib.reload(database)
    importlib.reload(app_module)
    client = app_module.app.test_client()

    assert client.post("/api/expenses", json={
        "description": "Coffee", "amount": 4.5, "category": "guilt_free"
    }).status_code == 200
    coffee = client.get("/api/expenses").get_json()[0]
    assert coffee["expense_date"] == date.today().isoformat()

    assert client.put(f"/api/expenses/{coffee['id']}", json={
        "description": "Coffee", "amount": 4.5, "category": "guilt_free",
        "expense_date": "2026-06-02",
    }).status_code == 200
    assert client.get("/api/expenses").get_json()[0]["expense_date"] == "2026-06-02"

    invalid = client.post("/api/expenses", json={
        "description": "Invalid subscription", "amount": 5, "category": "fixed",
        "recurring": True, "recurrence_interval": 0, "recurrence_unit": "month",
    })
    assert invalid.status_code == 400
    assert "at least 1" in invalid.get_json()["error"]


def test_recurring_expenses_only_apply_to_periods_containing_an_occurrence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import database
    import app as app_module
    importlib.reload(database)
    importlib.reload(app_module)
    client = app_module.app.test_client()

    assert client.post("/api/expenses", json={
        "description": "Home Insurance", "amount": 172, "category": "fixed",
        "recurring": True, "expense_date": "2030-01-05",
        "recurrence_interval": 1, "recurrence_unit": "month",
    }).status_code == 200
    assert client.post("/api/expenses", json={
        "description": "LingQ Subscription", "amount": 175, "category": "guilt_free",
        "recurring": True, "expense_date": "2030-01-21",
        "recurrence_interval": 1, "recurrence_unit": "year",
    }).status_code == 200

    def set_period(start, end):
        conn = database.get_connection()
        conn.execute(
            "UPDATE workspace_schedule SET period_start = ?, next_run = ? WHERE id = 1",
            (start, f"{end}T00:00"),
        )
        conn.commit()
        conn.close()

    set_period("2030-02-01", "2030-03-01")
    february = client.get("/api/dashboard").get_json()
    assert february["workspace_period"] == {"start": "2030-02-01", "end": "2030-03-01"}
    assert [expense["description"] for expense in february["expenses"]] == ["Home Insurance"]
    assert february["summary"]["spending"] == 172
    assert {expense["description"] for expense in february["recurring_expenses"]} == {
        "Home Insurance", "LingQ Subscription",
    }

    set_period("2030-12-20", "2031-01-20")
    before_annual_due_date = client.get("/api/dashboard").get_json()
    assert [expense["description"] for expense in before_annual_due_date["expenses"]] == ["Home Insurance"]
    assert before_annual_due_date["summary"]["spending"] == 172

    set_period("2031-01-20", "2031-02-20")
    annual_due_period = client.get("/api/dashboard").get_json()
    assert annual_due_period["workspace_period"] == {"start": "2031-01-20", "end": "2031-02-20"}
    assert {expense["description"] for expense in annual_due_period["expenses"]} == {
        "Home Insurance", "LingQ Subscription",
    }
    assert annual_due_period["summary"]["spending"] == 347


def test_scorecard_save_snapshots_expenses_and_resets_non_recurring(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    import database
    import app as app_module

    importlib.reload(database)
    importlib.reload(app_module)

    client = app_module.app.test_client()
    assert client.post("/api/income", json={"income": 2000}).status_code == 200
    assert client.post(
        "/api/expenses",
        json={
            "description": "Rent",
            "amount": 1000,
            "category": "fixed",
            "recurring": True,
            "recurrence_interval": 3,
            "recurrence_unit": "month",
        },
    ).status_code == 200
    assert client.post(
        "/api/expenses",
        json={
            "description": "Concert",
            "amount": 150,
            "category": "guilt_free",
            "recurring": False,
        },
    ).status_code == 200

    response = client.post(
        "/api/scorecards",
        json={"name": "July 2026", "start_date": "2026-07-01", "end_date": "2026-07-31"},
    )

    assert response.status_code == 201
    scorecard = response.get_json()
    assert scorecard["name"] == "July 2026"
    assert scorecard["total_spending"] == 1150
    assert scorecard["income"] == 2000
    assert scorecard["surplus"] == 850
    assert scorecard["income_period_duration"] == 1
    assert scorecard["income_period_unit"] == "month"
    assert scorecard["income_snapshot_present"] == 1
    assert {expense["description"] for expense in scorecard["expenses"]} == {"Rent", "Concert"}

    dashboard = client.get("/api/dashboard").get_json()
    assert dashboard["summary"]["spending"] == 1000
    assert [expense["description"] for expense in dashboard["expenses"]] == ["Rent"]

    saved = client.get(f"/api/scorecards/{scorecard['id']}").get_json()
    guilt_free = next(category for category in saved["categories"] if category["id"] == "guilt_free")
    assert guilt_free["total"] == 150
    assert guilt_free["expenses"][0]["description"] == "Concert"
    rent = next(expense for expense in saved["expenses"] if expense["description"] == "Rent")
    assert rent["recurrence_interval"] == 3
    assert rent["recurrence_unit"] == "month"
    assert saved["global_balance"] == 850
    assert saved["summary"]["expense_count"] == 2
    assert saved["summary"]["recurring_count"] == 1
    assert saved["summary"]["recurring_percent"] == 1000 / 1150 * 100
    assert saved["summary"]["largest_expense"]["description"] == "Rent"
    assert saved["summary"]["largest_expense"]["category_label"] == "Fixed Costs"
    assert saved["summary"]["largest_category"]["label"] == "Fixed Costs"
    assert saved["summary"]["category_spending"]["guilt_free"] == 150


def test_scorecard_requires_name_and_valid_date_range(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    import database
    import app as app_module

    importlib.reload(database)
    importlib.reload(app_module)

    client = app_module.app.test_client()
    response = client.post(
        "/api/scorecards",
        json={"name": "", "start_date": "2026-07-31", "end_date": "2026-07-01"},
    )

    assert response.status_code == 400
    assert "Scorecard name is required" in response.get_json()["error"]


def _create_scorecard_with_one_charge(client):
    assert client.post(
        "/api/expenses",
        json={
            "description": "Rent",
            "amount": 1000,
            "category": "fixed",
            "recurring": True,
        },
    ).status_code == 200
    response = client.post(
        "/api/scorecards",
        json={"name": "July 2026", "start_date": "2026-07-01", "end_date": "2026-07-31"},
    )
    assert response.status_code == 201
    return response.get_json()


def test_scorecard_charge_crud_recalculates_saved_totals(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    import database
    import app as app_module

    importlib.reload(database)
    importlib.reload(app_module)

    client = app_module.app.test_client()
    scorecard = _create_scorecard_with_one_charge(client)

    response = client.post(
        f"/api/scorecards/{scorecard['id']}/expenses",
        json={
            "description": "Brokerage",
            "amount": 250,
            "category": "investments",
            "recurring": False,
        },
    )
    assert response.status_code == 201
    scorecard = response.get_json()
    assert scorecard["total_spending"] == 1250
    added = next(expense for expense in scorecard["expenses"] if expense["description"] == "Brokerage")

    response = client.put(
        f"/api/scorecards/{scorecard['id']}/expenses/{added['id']}",
        json={
            "description": "Emergency fund",
            "amount": 300,
            "category": "savings",
            "recurring": True,
        },
    )
    assert response.status_code == 200
    scorecard = response.get_json()
    assert scorecard["total_spending"] == 1300
    savings = next(category for category in scorecard["categories"] if category["id"] == "savings")
    assert savings["total"] == 300
    assert savings["expenses"][0]["recurring"] == 1

    response = client.delete(f"/api/scorecards/{scorecard['id']}/expenses/{added['id']}")
    assert response.status_code == 200
    scorecard = response.get_json()
    assert scorecard["total_spending"] == 1000
    assert {expense["description"] for expense in scorecard["expenses"]} == {"Rent"}


def test_delete_scorecard_removes_it_and_its_saved_charges(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    import database
    import app as app_module

    importlib.reload(database)
    importlib.reload(app_module)

    client = app_module.app.test_client()
    scorecard = _create_scorecard_with_one_charge(client)

    assert client.delete(f"/api/scorecards/{scorecard['id']}").status_code == 200
    assert client.get(f"/api/scorecards/{scorecard['id']}").status_code == 404
    assert client.get("/api/scorecards").get_json() == []


def test_scorecard_csv_export_downloads_saved_charge_details(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    import database
    import app as app_module

    importlib.reload(database)
    importlib.reload(app_module)

    client = app_module.app.test_client()
    scorecard = _create_scorecard_with_one_charge(client)

    response = client.get(f"/api/scorecards/{scorecard['id']}/export.csv")

    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert "attachment" in response.headers["Content-Disposition"]
    csv_text = response.data.decode()
    assert "Scorecard,July 2026" in csv_text
    assert "Global Surplus / Deficit at Save,-1000.0" in csv_text
    assert "Largest Expense,Rent,1000.0,Fixed Costs" in csv_text
    assert "Total Expense Count,1" in csv_text
    assert "Total Recurring Count,1" in csv_text
    assert "Percent of Spending Recurring,100.00%" in csv_text
    assert "Fixed Costs,Rent,1000.0,Yes" in csv_text


def test_year_to_date_summary_aggregates_reports_and_saved_invested_spending(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import database
    import app as app_module
    importlib.reload(database)
    importlib.reload(app_module)
    client = app_module.app.test_client()

    conn = database.get_connection()
    first = conn.execute(
        "INSERT INTO scorecards (name, start_date, end_date, total_spending, income) VALUES ('January', '2026-01-01', '2026-01-31', 600, 1000)"
    ).lastrowid
    second = conn.execute(
        "INSERT INTO scorecards (name, start_date, end_date, total_spending, income) VALUES ('February', '2026-02-01', '2026-02-28', 400, 800)"
    ).lastrowid
    conn.executemany(
        "INSERT INTO scorecard_expenses (scorecard_id, description, amount, category, recurring, expense_date) VALUES (?, ?, ?, ?, 0, '2026-01-01')",
        [(first, "Emergency fund", 200, "savings"), (first, "Rent", 400, "fixed"), (second, "Brokerage", 100, "investments"), (second, "Fun", 300, "guilt_free")],
    )
    conn.execute(
        "INSERT INTO scorecards (name, start_date, end_date, total_spending, income) VALUES ('Old report', '2025-12-01', '2025-12-31', 999, 999)"
    )
    conn.commit()
    conn.close()

    response = client.get("/api/scorecards/year-to-date?year=2026")
    assert response.status_code == 200
    assert response.get_json() == {
        "year": 2026,
        "total_income": 1800.0,
        "total_spending": 1000.0,
        "saved_and_invested": 300.0,
        "percent_saved_invested": 30.0,
    }


def test_database_export_can_be_imported_to_restore_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    import io
    import database
    import app as app_module

    importlib.reload(database)
    importlib.reload(app_module)

    client = app_module.app.test_client()
    scorecard = _create_scorecard_with_one_charge(client)
    exported = client.get("/api/database/export")
    assert exported.status_code == 200
    assert "attachment" in exported.headers["Content-Disposition"]

    assert client.delete(f"/api/scorecards/{scorecard['id']}").status_code == 200
    assert client.get("/api/scorecards").get_json() == []

    imported = client.post(
        "/api/database/import",
        data={"database": (io.BytesIO(exported.data), "finance-tracker.db")},
        content_type="multipart/form-data",
    )

    assert imported.status_code == 200
    restored = client.get("/api/scorecards").get_json()
    assert len(restored) == 1
    assert restored[0]["name"] == "July 2026"


def test_income_profile_calculates_canadian_after_tax_pay(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    import database
    import app as app_module

    importlib.reload(database)
    importlib.reload(app_module)

    client = app_module.app.test_client()
    response = client.post(
        "/api/income",
        json={
            "mode": "gross_tax",
            "country": "Canada",
            "region_code": "ON",
            "tax_year": 2026,
            "gross_annual_income": 120000,
            "period_duration": 2,
            "period_unit": "week",
        },
    )

    assert response.status_code == 200
    profile = response.get_json()
    assert profile["income_mode"] == "gross_tax"
    assert profile["income_period_duration"] == 2
    assert profile["income_period_unit"] == "week"
    assert profile["income"] == 3462.52

    dashboard = client.get("/api/dashboard").get_json()
    assert dashboard["summary"]["income"] == 3462.52


def test_tax_ruleset_crud_allows_future_updates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    import database
    import app as app_module

    importlib.reload(database)
    importlib.reload(app_module)

    client = app_module.app.test_client()
    created = client.post(
        "/api/tax-rulesets",
        json={
            "country": "Canada",
            "region_name": "Test Province",
            "region_code": "TP",
            "tax_year": 2027,
            "brackets": [{"lower_bound": 0, "upper_bound": None, "rate": 10}],
        },
    )
    assert created.status_code == 201
    ruleset = next(item for item in client.get("/api/tax-rulesets").get_json() if item["region_code"] == "TP")

    overwritten = client.post(
        "/api/tax-rulesets",
        json={
            "country": "Canada",
            "region_name": "Renamed Test Province",
            "region_code": "TP",
            "tax_year": 2027,
            "brackets": [{"lower_bound": 0, "upper_bound": None, "rate": 8}],
        },
    )
    assert overwritten.status_code == 200
    assert overwritten.get_json() == {"success": True, "id": ruleset["id"], "overwritten": True}
    matching = [item for item in client.get("/api/tax-rulesets").get_json() if item["region_code"] == "TP"]
    assert len(matching) == 1
    assert matching[0]["region_name"] == "Renamed Test Province"
    assert matching[0]["brackets"][0]["rate"] == 8

    updated = client.put(
        f"/api/tax-rulesets/{ruleset['id']}",
        json={
            "country": "Canada",
            "region_name": "Test Province",
            "region_code": "TP",
            "tax_year": 2027,
            "brackets": [{"lower_bound": 0, "upper_bound": 50000, "rate": 9}, {"lower_bound": 50000, "upper_bound": None, "rate": 11}],
        },
    )
    assert updated.status_code == 200
    assert client.delete(f"/api/tax-rulesets/{ruleset['id']}").status_code == 200
    assert not any(item["region_code"] == "TP" for item in client.get("/api/tax-rulesets").get_json())


def test_new_ruleset_brackets_use_shared_editor_target(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    import database
    import app as app_module

    importlib.reload(database)
    importlib.reload(app_module)

    page = app_module.app.test_client().get("/").get_data(as_text=True)
    assert 'id="ruleset-new"' in page
    assert "addTaxBracketRow('new')" in page


def test_federal_only_income_does_not_apply_federal_rules_twice(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    import database
    import app as app_module

    importlib.reload(database)
    importlib.reload(app_module)

    client = app_module.app.test_client()
    created = client.post(
        "/api/tax-rulesets",
        json={
            "country": "Testland",
            "region_name": "Testland Federal",
            "region_code": "FED",
            "tax_year": 2028,
            "brackets": [{"lower_bound": 0, "upper_bound": None, "rate": 10}],
        },
    )
    assert created.status_code == 201

    profile = client.post(
        "/api/income",
        json={
            "mode": "gross_tax",
            "country": "Testland",
            "region_code": "FED",
            "tax_year": 2028,
            "gross_annual_income": 120000,
            "period_duration": 1,
            "period_unit": "month",
        },
    ).get_json()
    assert profile["income"] == 9000


def test_basic_personal_amount_reduces_income_before_ruleset_tax(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    import database
    import app as app_module

    importlib.reload(database)
    importlib.reload(app_module)

    client = app_module.app.test_client()
    created = client.post(
        "/api/tax-rulesets",
        json={
            "country": "Creditland",
            "region_name": "Federal",
            "region_code": "FED",
            "tax_year": 2028,
            "basic_personal_credit_enabled": True,
            "basic_personal_credit_amount": 1000,
            "brackets": [{"lower_bound": 0, "upper_bound": None, "rate": 10}],
        },
    )
    assert created.status_code == 201
    ruleset = next(item for item in client.get("/api/tax-rulesets").get_json() if item["country"] == "Creditland")
    assert ruleset["basic_personal_credit_enabled"] == 1
    assert ruleset["basic_personal_credit_amount"] == 1000

    profile = client.post(
        "/api/income",
        json={
            "mode": "gross_tax",
            "country": "Creditland",
            "region_code": "FED",
            "tax_year": 2028,
            "gross_annual_income": 120000,
            "period_duration": 1,
            "period_unit": "month",
        },
    ).get_json()
    assert profile["income"] == 9008.33
