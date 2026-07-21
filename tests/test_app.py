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
