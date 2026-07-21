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
