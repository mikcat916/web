from fastapi.testclient import TestClient

import main as app_module


def fake_user():
    return {
        "id": 1,
        "username": "admin",
        "password_hash": "hash",
        "display_name": "Admin User",
        "created_at": "2026-03-10T12:00",
    }


def login(client: TestClient):
    response = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200


def mock_auth(monkeypatch):
    monkeypatch.setattr(app_module, "mysql_configured", lambda: True)
    monkeypatch.setattr(app_module, "ensure_database", lambda: None)
    monkeypatch.setattr(app_module, "execute_schema", lambda: None)
    monkeypatch.setattr(app_module, "ensure_admin_user", lambda: None)
    monkeypatch.setattr(app_module, "get_user_by_username", lambda username: fake_user())
    monkeypatch.setattr(app_module, "verify_password", lambda password, password_hash: True)


def test_login_page_available_without_mysql():
    with TestClient(app_module.app) as client:
        response = client.get("/login")
    assert response.status_code == 200
    assert "机器人巡检平台" in response.text


def test_page_requires_login_redirect():
    with TestClient(app_module.app) as client:
        response = client.get("/overview", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_login_success_and_page_access(monkeypatch):
    mock_auth(monkeypatch)

    with TestClient(app_module.app) as client:
        login(client)
        response = client.get("/overview")

    assert response.status_code == 200
    assert "退出登录" in response.text


def test_api_requires_login():
    with TestClient(app_module.app) as client:
        response = client.get("/api/dashboard")
    assert response.status_code == 401


def test_authenticated_dashboard_and_logout(monkeypatch):
    mock_auth(monkeypatch)
    monkeypatch.setattr(
        app_module,
        "build_dashboard_payload",
        lambda: {
            "site": app_module.DEFAULT_SITE,
            "counts": {"robots": 1, "tasks": 2, "alerts": 3, "reports": 4, "zones": 5},
            "robots": [],
            "tasks": [],
            "alerts": [],
            "reports": [],
            "zones": [],
            "maintenance": [],
            "generatedAt": "2026-03-10T12:00",
        },
    )

    with TestClient(app_module.app) as client:
        login(client)
        dashboard_response = client.get("/api/dashboard")
        logout_response = client.post("/auth/logout")
        after_logout = client.get("/api/dashboard")

    assert dashboard_response.status_code == 200
    assert dashboard_response.json()["data"]["counts"]["robots"] == 1
    assert logout_response.status_code == 200
    assert after_logout.status_code == 401


def test_health_endpoint(monkeypatch):
    monkeypatch.setattr(app_module, "mysql_configured", lambda: True)
    monkeypatch.setattr(app_module, "mysql_ready", lambda: True)
    app_module.APP_STATE["db_error"] = ""
    with TestClient(app_module.app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["mysqlConfigured"] is True
    assert payload["mysqlReady"] is True


def test_websocket_dashboard_connected(monkeypatch):
    mock_auth(monkeypatch)

    with TestClient(app_module.app) as client:
        login(client)
        with client.websocket_connect("/ws/dashboard") as websocket:
            message = websocket.receive_json()
            assert message["type"] == "dashboard_update"
            assert message["event"] == "connected"


def test_delete_invalid_task_id_returns_422(monkeypatch):
    mock_auth(monkeypatch)
    with TestClient(app_module.app) as client:
        login(client)
        response = client.delete("/api/tasks/0")
    assert response.status_code == 422


def test_delete_missing_task_returns_404(monkeypatch):
    mock_auth(monkeypatch)
    monkeypatch.setattr(app_module, "clear_table", lambda table_name, record_id: 0)
    with TestClient(app_module.app) as client:
        login(client)
        response = client.delete("/api/tasks/999999999")
    assert response.status_code == 404


def test_create_task_rejects_invalid_foreign_key_boundary(monkeypatch):
    mock_auth(monkeypatch)
    payload = {
        "name": "测试任务",
        "priority": "medium",
        "robotId": 0,
        "zoneId": 1,
        "startAt": "2026-03-14T09:00:00",
        "endAt": "2026-03-14T10:00:00",
    }
    with TestClient(app_module.app) as client:
        login(client)
        response = client.post("/api/tasks", json=payload)
    assert response.status_code == 422


def test_create_task_rejects_missing_foreign_record(monkeypatch):
    mock_auth(monkeypatch)
    monkeypatch.setattr(app_module, "robot_exists", lambda record_id: False)
    monkeypatch.setattr(app_module, "zone_exists", lambda record_id: True)
    payload = {
        "name": "测试任务",
        "priority": "medium",
        "robotId": 1,
        "zoneId": 1,
        "startAt": "2026-03-14T09:00:00",
        "endAt": "2026-03-14T10:00:00",
    }
    with TestClient(app_module.app) as client:
        login(client)
        response = client.post("/api/tasks", json=payload)
    assert response.status_code == 404
