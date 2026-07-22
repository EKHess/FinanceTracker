import importlib


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
        },
    ).status_code == 200

    dashboard = client.get("/api/dashboard").get_json()
    assert dashboard["summary"]["spending"] == 400
    assert dashboard["summary"]["surplus"] == 600
    assert dashboard["summary"]["recurring_total"] == 400

    expense_id = dashboard["expenses"][0]["id"]
    assert client.put(
        f"/api/expenses/{expense_id}",
        json={
            "description": "Rent",
            "amount": 450,
            "category": "fixed",
            "recurring": True,
        },
    ).status_code == 200
    assert client.delete(f"/api/expenses/{expense_id}").status_code == 200
    assert client.get("/api/dashboard").get_json()["summary"]["spending"] == 0


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
    assert {expense["description"] for expense in scorecard["expenses"]} == {"Rent", "Concert"}

    dashboard = client.get("/api/dashboard").get_json()
    assert dashboard["summary"]["spending"] == 1000
    assert [expense["description"] for expense in dashboard["expenses"]] == ["Rent"]

    saved = client.get(f"/api/scorecards/{scorecard['id']}").get_json()
    guilt_free = next(category for category in saved["categories"] if category["id"] == "guilt_free")
    assert guilt_free["total"] == 150
    assert guilt_free["expenses"][0]["description"] == "Concert"


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
    assert "Fixed Costs,Rent,1000.0,Yes" in csv_text


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


def test_basic_personal_credit_reduces_ruleset_tax(tmp_path, monkeypatch):
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
    assert profile["income"] == 9083.33
