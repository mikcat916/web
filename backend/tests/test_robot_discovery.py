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
    monkeypatch.setattr(app_module, "ensure_robot_ip_column", lambda: None)
    monkeypatch.setattr(app_module, "ensure_admin_user", lambda: None)
    monkeypatch.setattr(app_module, "get_user_by_username", lambda username: fake_user())
    monkeypatch.setattr(app_module, "verify_password", lambda password, password_hash: True)


async def fake_ws_broadcast(event: str):
    return None


def test_robot_discovery_endpoint_returns_candidates(monkeypatch):
    mock_auth(monkeypatch)
    monkeypatch.setattr(
        app_module,
        "discover_robot_candidates",
        lambda force=False: {
            "items": [
                {
                    "ipAddress": "192.168.31.101",
                    "hostName": "raspberrypi",
                    "macAddress": "2C:CF:67:06:98:4C",
                    "openPorts": [22],
                    "confirmed": True,
                    "summary": "hostname=raspberrypi, mac=2C:CF:67:06:98:4C, ssh",
                }
            ],
            "scannedAt": "2026-03-30T10:00:00",
            "expiresAt": "2026-03-30T10:05:00",
            "subnets": ["192.168.31.0/24"],
        },
    )

    with TestClient(app_module.app) as client:
        login(client)
        response = client.get("/api/robots/discovery?refresh=1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["ipAddress"] == "192.168.31.101"
    assert payload["items"][0]["confirmed"] is True


def test_create_robot_rejects_undiscovered_ip(monkeypatch):
    mock_auth(monkeypatch)
    monkeypatch.setattr(app_module, "get_discovered_robot", lambda ip_address: None)

    payload = {
        "model": "巡检机器人01",
        "ipAddress": "192.168.31.101",
        "status": "idle",
        "health": 92,
        "battery": 78,
        "speed": 1.2,
        "signal": 88,
        "latency": 28,
        "lng": 121.81742,
        "lat": 31.09161,
        "heading": 0,
    }

    with TestClient(app_module.app) as client:
        login(client)
        response = client.post("/api/robots", json=payload)

    assert response.status_code == 422
    assert "扫描" in response.json()["detail"]


def test_create_robot_accepts_confirmed_discovered_ip(monkeypatch):
    mock_auth(monkeypatch)
    captured = {}

    def fake_execute_write(sql, params=None):
        captured["sql"] = sql
        captured["params"] = params
        return 1

    monkeypatch.setattr(
        app_module,
        "get_discovered_robot",
        lambda ip_address: {"ipAddress": ip_address, "confirmed": True, "hostName": "raspberrypi"},
    )
    monkeypatch.setattr(app_module, "execute_write", fake_execute_write)
    monkeypatch.setattr(app_module, "ws_broadcast", fake_ws_broadcast)

    payload = {
        "model": "巡检机器人01",
        "ipAddress": "192.168.31.101",
        "status": "idle",
        "health": 92,
        "battery": 78,
        "speed": 1.2,
        "signal": 88,
        "latency": 28,
        "lng": 121.81742,
        "lat": 31.09161,
        "heading": 0,
    }

    with TestClient(app_module.app) as client:
        login(client)
        response = client.post("/api/robots", json=payload)

    assert response.status_code == 200
    assert captured["params"][1] == "192.168.31.101"


def test_iot_telemetry_persists_source_ip(monkeypatch):
    captured = {}

    def fake_execute_insert(sql, params=None):
        captured["sql"] = sql
        captured["params"] = params
        return 1

    monkeypatch.setattr(app_module, "require_device_token", lambda request: 2)
    monkeypatch.setattr(app_module, "execute_insert", fake_execute_insert)
    monkeypatch.setattr(app_module, "execute_write", lambda *args, **kwargs: 1)
    monkeypatch.setattr(app_module, "ws_broadcast", fake_ws_broadcast)

    payload = {
        "battery": 85,
        "signal": 72,
        "status": "online",
        "lat": 31.09161,
        "lng": 121.81742,
        "reportedAt": "2026-03-30T10:00:00",
    }

    with TestClient(app_module.app) as client:
        response = client.post("/api/iot/telemetry", json=payload)

    assert response.status_code == 200
    assert captured["params"][6] == "testclient"


def test_recent_iot_log_identity_map_falls_back_from_journal(monkeypatch):
    monkeypatch.setattr(app_module, "mysql_ready", lambda: True)
    monkeypatch.setattr(
        app_module,
        "query_all",
        lambda sql, params=None: [
            {
                "device_id": 2,
                "device_name": "Raspberry Car",
                "device_model": "Pi Robot",
                "reported_at": "2026-03-31T10:51:53",
            }
        ],
    )
    monkeypatch.setattr(
        app_module.subprocess,
        "check_output",
        lambda *args, **kwargs: 'Mar 31 10:51:53 host python[1]: INFO:     192.168.31.200:0 - "POST /api/iot/telemetry HTTP/1.1" 200 OK',
    )

    result = app_module.load_recent_iot_log_identity_map()

    assert result["192.168.31.200"]["deviceId"] == 2
    assert result["192.168.31.200"]["deviceName"] == "Raspberry Car"
