from fastapi.testclient import TestClient

import main as app_module


def fake_user():
    return {
        "id": 1,
        "username": "admin",
        "password_hash": "hash",
        "display_name": "Admin User",
        "status": "active",
        "created_at": "2026-03-10T12:00",
    }


def login(client: TestClient):
    response = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200


def mock_auth(monkeypatch):
    monkeypatch.setattr(app_module, "mysql_configured", lambda: True)
    monkeypatch.setattr(app_module, "ensure_database", lambda: None)
    monkeypatch.setattr(app_module, "execute_schema", lambda: None)
    monkeypatch.setattr(app_module, "ensure_iot_tables", lambda: None)
    monkeypatch.setattr(app_module, "ensure_robot_ip_column", lambda: None)
    monkeypatch.setattr(app_module, "ensure_admin_user", lambda: None)
    monkeypatch.setattr(app_module, "get_user_by_username", lambda username: fake_user())
    monkeypatch.setattr(app_module, "verify_password", lambda password, password_hash: True)


def test_login_page_available_without_mysql():
    with TestClient(app_module.app) as client:
        response = client.get("/login")
    assert response.status_code == 200
    assert "机器人巡检平台" in response.text
    assert "注册" in response.text


def test_login_page_enables_registration_by_default(monkeypatch):
    monkeypatch.delenv("ALLOW_SELF_REGISTER", raising=False)
    with TestClient(app_module.app) as client:
        response = client.get("/login")
    assert response.status_code == 200
    assert "allowSelfRegister: true" in response.text


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


def test_register_rejected_when_disabled(monkeypatch):
    mock_auth(monkeypatch)
    monkeypatch.setattr(app_module, "mysql_ready", lambda: True)
    monkeypatch.setenv("ALLOW_SELF_REGISTER", "0")

    with TestClient(app_module.app) as client:
        response = client.post(
            "/auth/register",
            json={"username": "newuser", "password": "secret123", "displayName": "New User"},
        )

    assert response.status_code == 403


def test_register_success_and_dashboard_access(monkeypatch):
    mock_auth(monkeypatch)
    monkeypatch.setattr(app_module, "mysql_ready", lambda: True)
    monkeypatch.setattr(app_module, "hash_password", lambda password: f"hashed:{password}")
    monkeypatch.setenv("ALLOW_SELF_REGISTER", "1")

    users = {}

    def fake_get_user(username):
        return users.get(username)

    def fake_execute_write(sql, params=None):
        username, password_hash, display_name, created_at = params
        users[username] = {
            "id": len(users) + 1,
            "username": username,
            "password_hash": password_hash,
            "display_name": display_name,
            "status": "active",
            "created_at": created_at,
        }
        return 1

    monkeypatch.setattr(app_module, "get_user_by_username", fake_get_user)
    monkeypatch.setattr(app_module, "execute_write", fake_execute_write)
    monkeypatch.setattr(
        app_module,
        "build_dashboard_payload",
        lambda: {
            "site": app_module.DEFAULT_SITE,
            "counts": {"robots": 0, "tasks": 0, "alerts": 0, "reports": 0, "zones": 0},
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
        response = client.post(
            "/auth/register",
            json={"username": "newuser", "password": "secret123", "displayName": "New User"},
        )
        dashboard_response = client.get("/api/dashboard")

    assert response.status_code == 200
    assert response.json()["user"]["username"] == "newuser"
    assert dashboard_response.status_code == 200


def test_register_rejects_duplicate_username(monkeypatch):
    mock_auth(monkeypatch)
    monkeypatch.setattr(app_module, "mysql_ready", lambda: True)
    monkeypatch.setenv("ALLOW_SELF_REGISTER", "1")
    monkeypatch.setattr(app_module, "get_user_by_username", lambda username: fake_user())

    with TestClient(app_module.app) as client:
        response = client.post(
            "/auth/register",
            json={"username": "admin", "password": "secret123", "displayName": "Admin User"},
        )

    assert response.status_code == 409


def test_zone_update_and_delete(monkeypatch):
    mock_auth(monkeypatch)

    events = []

    async def fake_ws_broadcast(event):
        events.append(event)

    monkeypatch.setattr(
        app_module,
        "load_zone",
        lambda zone_id: {
            "id": zone_id,
            "name": "旧区域",
            "type": "inspection",
            "risk": "medium",
            "status": "active",
            "frequency": "30分钟/次",
            "strokeColor": "#0db9f2",
            "fillColor": "rgba(13, 185, 242, 0.18)",
            "path": [[121.81, 31.09], [121.82, 31.09], [121.815, 31.08]],
            "notes": "旧备注",
            "createdAt": "2026-03-10T12:00",
            "center": [121.815, 31.086],
        },
    )
    monkeypatch.setattr(app_module, "execute_write", lambda sql, params=None: 1)
    monkeypatch.setattr(app_module, "clear_table", lambda table_name, record_id: 1)
    monkeypatch.setattr(app_module, "ws_broadcast", fake_ws_broadcast)

    with TestClient(app_module.app) as client:
        login(client)
        update_response = client.put(
            "/api/zones/1",
            json={"name": "新区域", "notes": "新备注", "risk": "high"},
        )
        delete_response = client.delete("/api/zones/1")

    assert update_response.status_code == 200
    assert delete_response.status_code == 200
    assert events == ["zone_updated", "zone_deleted"]


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
