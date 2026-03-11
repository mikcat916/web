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
    monkeypatch.setattr(app_module, "mysql_configured", lambda: True)
    monkeypatch.setattr(app_module, "ensure_database", lambda: None)
    monkeypatch.setattr(app_module, "execute_schema", lambda: None)
    monkeypatch.setattr(app_module, "ensure_admin_user", lambda: None)
    monkeypatch.setattr(app_module, "get_user_by_username", lambda username: fake_user())
    monkeypatch.setattr(app_module, "verify_password", lambda password, password_hash: True)

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
    monkeypatch.setattr(app_module, "mysql_configured", lambda: True)
    monkeypatch.setattr(app_module, "ensure_database", lambda: None)
    monkeypatch.setattr(app_module, "execute_schema", lambda: None)
    monkeypatch.setattr(app_module, "ensure_admin_user", lambda: None)
    monkeypatch.setattr(app_module, "get_user_by_username", lambda username: fake_user())
    monkeypatch.setattr(app_module, "verify_password", lambda password, password_hash: True)
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
