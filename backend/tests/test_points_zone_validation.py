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


def square_zone():
    return {
        "id": 1,
        "name": "测试巡检区",
        "path": [
            [121.0, 31.0],
            [121.1, 31.0],
            [121.1, 31.1],
            [121.0, 31.1],
        ],
    }


def test_create_point_rejects_outside_zone(monkeypatch):
    mock_auth(monkeypatch)
    monkeypatch.setattr(app_module, "load_zones", lambda: [square_zone()])

    payload = {
        "name": "点位 A",
        "lat": 32.0,
        "lng": 122.0,
    }

    with TestClient(app_module.app) as client:
        login(client)
        response = client.post("/api/points", json=payload)

    assert response.status_code == 422
    assert "巡检区域" in response.json()["detail"]


def test_create_point_accepts_inside_zone(monkeypatch):
    mock_auth(monkeypatch)
    captured = {}
    monkeypatch.setattr(app_module, "load_zones", lambda: [square_zone()])

    def fake_execute_write(sql, params=None):
        captured["params"] = params
        return 1

    monkeypatch.setattr(app_module, "execute_write", fake_execute_write)

    payload = {
        "name": "点位 A",
        "lat": 31.05,
        "lng": 121.05,
    }

    with TestClient(app_module.app) as client:
        login(client)
        response = client.post("/api/points", json=payload)

    assert response.status_code == 200
    assert captured["params"][3] == 31.05
    assert captured["params"][4] == 121.05
