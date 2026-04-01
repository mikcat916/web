from fastapi.testclient import TestClient

import main as app_module


def test_startup_invokes_iot_table_migration(monkeypatch):
    called = {"iot": False}

    monkeypatch.setattr(app_module, "mysql_configured", lambda: True)
    monkeypatch.setattr(app_module, "ensure_database", lambda: None)
    monkeypatch.setattr(app_module, "execute_schema", lambda: None)
    monkeypatch.setattr(app_module, "ensure_robot_ip_column", lambda: None)
    monkeypatch.setattr(app_module, "ensure_admin_user", lambda: None)
    monkeypatch.setattr(
        app_module,
        "ensure_iot_tables",
        lambda: called.__setitem__("iot", True),
    )

    with TestClient(app_module.app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert called["iot"] is True
