from datetime import date, datetime

from fastapi.testclient import TestClient

import main as app_module


def fake_user(status: str = "active"):
    return {
        "id": 1,
        "username": "admin",
        "password_hash": "hash",
        "display_name": "Admin User",
        "status": status,
        "created_at": "2026-03-10T12:00",
    }


def login(client: TestClient):
    response = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200


def mock_auth(monkeypatch, *, user_status: str = "active"):
    monkeypatch.setattr(app_module, "mysql_configured", lambda: True)
    monkeypatch.setattr(app_module, "ensure_database", lambda: None)
    monkeypatch.setattr(app_module, "execute_schema", lambda: None)
    monkeypatch.setattr(app_module, "ensure_iot_tables", lambda: None)
    monkeypatch.setattr(app_module, "ensure_robot_ip_column", lambda: None)
    monkeypatch.setattr(app_module, "ensure_admin_user", lambda: None)
    monkeypatch.setattr(app_module, "get_user_by_username", lambda username: fake_user(user_status))
    monkeypatch.setattr(app_module, "verify_password", lambda password, password_hash: True)


def test_areas_list_supports_pagination_and_keyword(monkeypatch):
    mock_auth(monkeypatch)
    captured = {}

    def fake_query_one(sql, params=None):
        if "COUNT(*)" in sql and "FROM areas" in sql:
            return {"cnt": 3}
        return None

    def fake_query_all(sql, params=None):
        captured["sql"] = sql
        captured["params"] = params
        return [
            {
                "id": 101,
                "name": "东区",
                "description": "东门区域",
                "manager": "张三",
                "created_at": datetime(2026, 4, 1, 10, 0, 0),
            },
            {
                "id": 102,
                "name": "东区二期",
                "description": "东门扩展区",
                "manager": "李四",
                "created_at": datetime(2026, 4, 1, 9, 0, 0),
            },
        ]

    monkeypatch.setattr(app_module, "query_one", fake_query_one)
    monkeypatch.setattr(app_module, "query_all", fake_query_all)

    with TestClient(app_module.app) as client:
        login(client)
        response = client.get("/api/areas?page=2&size=2&keyword=东区")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["page"] == 2
    assert payload["size"] == 2
    assert len(payload["items"]) == 2
    assert "东区" in str(captured.get("params"))


def test_zones_list_supports_pagination(monkeypatch):
    mock_auth(monkeypatch)
    captured = {}

    def fake_query_one(sql, params=None):
        if "COUNT(*)" in sql and "FROM zones" in sql:
            return {"cnt": 7}
        return None

    def fake_query_all(sql, params=None):
        captured["params"] = params
        return [
            {
                "id": 1,
                "name": "Z-1",
                "type": "inspection",
                "risk": "medium",
                "status": "active",
                "frequency": "30分钟/次",
                "stroke_color": "#0db9f2",
                "fill_color": "rgba(13, 185, 242, 0.18)",
                "path_json": "[[121.81,31.09],[121.82,31.09],[121.815,31.08]]",
                "notes": "",
                "created_at": datetime(2026, 4, 1, 12, 0, 0),
            },
            {
                "id": 2,
                "name": "Z-2",
                "type": "inspection",
                "risk": "high",
                "status": "active",
                "frequency": "60分钟/次",
                "stroke_color": "#0db9f2",
                "fill_color": "rgba(13, 185, 242, 0.18)",
                "path_json": "[[121.71,31.19],[121.72,31.19],[121.715,31.18]]",
                "notes": "",
                "created_at": datetime(2026, 4, 1, 11, 0, 0),
            },
        ]

    monkeypatch.setattr(app_module, "query_one", fake_query_one)
    monkeypatch.setattr(app_module, "query_all", fake_query_all)

    with TestClient(app_module.app) as client:
        login(client)
        response = client.get("/api/zones?page=2&size=2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 7
    assert payload["page"] == 2
    assert payload["size"] == 2
    assert len(payload["items"]) == 2
    assert captured["params"] == (2, 2)


def test_reports_list_supports_pagination(monkeypatch):
    mock_auth(monkeypatch)
    captured = {}

    def fake_query_one(sql, params=None):
        if "COUNT(*)" in sql and "FROM reports" in sql:
            return {"cnt": 5}
        return None

    def fake_query_all(sql, params=None):
        captured["params"] = params
        return [
            {
                "id": 1,
                "title": "日报 A",
                "value": "95%",
                "trend": "+2%",
                "tone": "positive",
                "detail": "ok",
                "report_date": date(2026, 4, 1),
                "created_at": datetime(2026, 4, 1, 10, 0, 0),
            },
            {
                "id": 2,
                "title": "日报 B",
                "value": "93%",
                "trend": "-1%",
                "tone": "neutral",
                "detail": "ok",
                "report_date": date(2026, 3, 31),
                "created_at": datetime(2026, 3, 31, 10, 0, 0),
            },
        ]

    monkeypatch.setattr(app_module, "query_one", fake_query_one)
    monkeypatch.setattr(app_module, "query_all", fake_query_all)

    with TestClient(app_module.app) as client:
        login(client)
        response = client.get("/api/reports?page=2&size=2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 5
    assert payload["page"] == 2
    assert payload["size"] == 2
    assert len(payload["items"]) == 2
    assert captured["params"] == (2, 2)


def test_create_area_rejects_duplicate_name_case_insensitive(monkeypatch):
    mock_auth(monkeypatch)

    def fake_query_one(sql, params=None):
        if "FROM areas" in sql:
            return {"id": 9}
        return None

    monkeypatch.setattr(app_module, "query_one", fake_query_one)
    monkeypatch.setattr(app_module, "execute_write", lambda sql, params=None: 1)

    with TestClient(app_module.app) as client:
        login(client)
        response = client.post("/api/areas", json={"name": "  东区  ", "description": "", "manager": ""})

    assert response.status_code == 409


def test_update_area_rejects_duplicate_name_case_insensitive(monkeypatch):
    mock_auth(monkeypatch)

    def fake_query_one(sql, params=None):
        lowered = sql.lower()
        if "from areas" not in lowered:
            return None
        if "where id" in lowered:
            return {"id": 1, "name": "原区域"}
        return {"id": 2, "name": "冲突区域"}

    monkeypatch.setattr(app_module, "query_one", fake_query_one)
    monkeypatch.setattr(app_module, "execute_write", lambda sql, params=None: 1)

    with TestClient(app_module.app) as client:
        login(client)
        response = client.put("/api/areas/1", json={"name": "  东区  ", "description": "", "manager": ""})

    assert response.status_code == 409


def test_create_zone_rejects_duplicate_name_case_insensitive(monkeypatch):
    mock_auth(monkeypatch)

    def fake_query_one(sql, params=None):
        if "FROM zones" in sql:
            return {"id": 9}
        return None

    monkeypatch.setattr(app_module, "query_one", fake_query_one)
    monkeypatch.setattr(app_module, "execute_write", lambda sql, params=None: 1)

    with TestClient(app_module.app) as client:
        login(client)
        response = client.post(
            "/api/zones",
            json={"name": "  东区  ", "path": [[121.0, 31.0], [121.1, 31.0], [121.05, 31.1]]},
        )

    assert response.status_code == 409


def test_update_zone_rejects_duplicate_name_case_insensitive(monkeypatch):
    mock_auth(monkeypatch)

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

    def fake_query_one(sql, params=None):
        if "FROM zones" in sql:
            return {"id": 2}
        return None

    monkeypatch.setattr(app_module, "query_one", fake_query_one)
    monkeypatch.setattr(app_module, "execute_write", lambda sql, params=None: 1)

    with TestClient(app_module.app) as client:
        login(client)
        response = client.put("/api/zones/1", json={"name": "  东区  "})

    assert response.status_code == 409


def test_delete_area_blocked_when_related_records_exist(monkeypatch):
    mock_auth(monkeypatch)

    def fake_query_one(sql, params=None):
        lowered = sql.lower()
        if "from areas" in lowered and "where id" in lowered:
            return {"id": 1}
        if "from devices" in lowered and "count" in lowered:
            return {"cnt": 1}
        if "from points" in lowered and "count" in lowered:
            return {"cnt": 2}
        if "from routes" in lowered and "count" in lowered:
            return {"cnt": 1}
        return None

    monkeypatch.setattr(app_module, "query_one", fake_query_one)
    monkeypatch.setattr(
        app_module,
        "clear_table",
        lambda table_name, record_id: (_ for _ in ()).throw(AssertionError("有关联时不应执行删除")),
    )

    with TestClient(app_module.app) as client:
        login(client)
        response = client.delete("/api/areas/1")

    assert response.status_code == 409
    assert "关联" in str(response.json())


def test_batch_delete_areas_fails_all_when_any_item_blocked(monkeypatch):
    mock_auth(monkeypatch)
    clear_calls = []

    def fake_query_one(sql, params=None):
        lowered = sql.lower()
        area_id = params[0] if params else None
        if "from areas" in lowered and "where id" in lowered:
            return {"id": area_id}
        if "from devices" in lowered and "count" in lowered:
            return {"cnt": 1 if area_id == 2 else 0}
        if "from points" in lowered and "count" in lowered:
            return {"cnt": 0}
        if "from routes" in lowered and "count" in lowered:
            return {"cnt": 0}
        return None

    def fake_clear_table(table_name, record_id):
        clear_calls.append((table_name, record_id))
        return 1

    monkeypatch.setattr(app_module, "query_one", fake_query_one)
    monkeypatch.setattr(app_module, "clear_table", fake_clear_table)

    with TestClient(app_module.app) as client:
        login(client)
        response = client.post("/api/areas/batch-delete", json={"ids": [1, 2]})

    assert response.status_code == 409
    assert clear_calls == []


def test_zone_put_delete_regression_still_available(monkeypatch):
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
        update_response = client.put("/api/zones/1", json={"name": "新区域"})
        delete_response = client.delete("/api/zones/1")

    assert update_response.status_code == 200
    assert delete_response.status_code == 200
    assert events == ["zone_updated", "zone_deleted"]


def test_disabled_user_login_regression_still_blocked(monkeypatch):
    mock_auth(monkeypatch, user_status="disabled")
    monkeypatch.setattr(app_module, "mysql_ready", lambda: True)

    with TestClient(app_module.app) as client:
        response = client.post("/auth/login", json={"username": "admin", "password": "admin123"})

    assert response.status_code == 403
    assert "禁用" in response.json()["detail"]
