from __future__ import annotations

import hashlib
import hmac
import json
import os
import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pymysql
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pymysql.cursors import DictCursor
from starlette.middleware.sessions import SessionMiddleware

# Runtime paths and bootstrap file locations.
BASE_DIR = Path(__file__).resolve().parent
PROTOTYPE_DIR = BASE_DIR / "stitch_monitoring_dashboard"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
ENV_FILE = BASE_DIR / ".env"
SCHEMA_FILE = BASE_DIR / "db" / "mysql_schema.sql"

# Legacy prototype routes are kept for compatibility/debug pages.
PROTOTYPES = {
    "_1": "历史报告",
    "_2": "总览",
    "_3": "任务管理",
    "maintenance": "设备维护",
    "monitoring_dashboard": "机器人状态",
    "zone_control": "区域控制",
}

# Canonical page map: used by template navigation and redirects.
PAGES = {
    "overview": {"route": "/overview", "title": "总览", "kicker": "系统概览"},
    "tasks": {"route": "/tasks", "title": "任务管理", "kicker": "任务中心"},
    "reports": {"route": "/reports", "title": "历史报告", "kicker": "数据报告"},
    "status": {"route": "/robots", "title": "机器人状态", "kicker": "设备状态"},
    "maintenance": {"route": "/maintenance", "title": "设备维护", "kicker": "维护中心"},
    "zones": {"route": "/zones", "title": "区域控制", "kicker": "区域管理"},
}

REQUIRED_MYSQL_ENV = (
    "MYSQL_HOST",
    "MYSQL_PORT",
    "MYSQL_USER",
    "MYSQL_PASSWORD",
    "MYSQL_DATABASE",
)
MAX_ID_VALUE = 2_147_483_647

DEFAULT_SITE = {
    "name": "机器人巡检指挥中心",
    "subtitle": "巡检作业控制台",
    "city": "上海临港",
    "center": [121.81742, 31.09161],
    "zoom": 15.8,
}

# Global runtime state shared by startup and health checks.
APP_STATE = {
    "db_ready": False,
    "db_error": "",
}
# In-memory websocket registry for dashboard realtime updates.
WS_CLIENTS: set[WebSocket] = set()
WS_LOCK = asyncio.Lock()


def load_local_env() -> None:
    # Minimal .env loader to keep deployment dependency-free.
    if not ENV_FILE.exists():
        return
    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip()


load_local_env()


def mysql_configured() -> bool:
    # All required MySQL env vars must be present.
    return all(os.getenv(key, "").strip() for key in REQUIRED_MYSQL_ENV)


def mysql_ready() -> bool:
    return mysql_configured() and APP_STATE["db_ready"]


def mysql_settings() -> dict[str, Any]:
    return {
        "host": os.getenv("MYSQL_HOST", "").strip(),
        "port": int(os.getenv("MYSQL_PORT", "3306").strip() or "3306"),
        "user": os.getenv("MYSQL_USER", "").strip(),
        "password": os.getenv("MYSQL_PASSWORD", "").strip(),
        "database": os.getenv("MYSQL_DATABASE", "").strip(),
        "charset": os.getenv("MYSQL_CHARSET", "utf8mb4").strip() or "utf8mb4",
    }


def get_server_db():
    settings = mysql_settings()
    return pymysql.connect(
        host=settings["host"],
        port=settings["port"],
        user=settings["user"],
        password=settings["password"],
        charset=settings["charset"],
        cursorclass=DictCursor,
        autocommit=False,
    )


def get_db():
    settings = mysql_settings()
    return pymysql.connect(
        host=settings["host"],
        port=settings["port"],
        user=settings["user"],
        password=settings["password"],
        database=settings["database"],
        charset=settings["charset"],
        cursorclass=DictCursor,
        autocommit=False,
    )


def ensure_mysql_configured() -> None:
    if mysql_configured():
        return
    raise HTTPException(
        status_code=503,
        detail="MySQL 未配置，请先在 .env 中设置 MYSQL_HOST、MYSQL_PORT、MYSQL_USER、MYSQL_PASSWORD、MYSQL_DATABASE。",
    )


def ensure_database() -> None:
    # Create database if missing before schema execution.
    if not mysql_configured():
        return
    settings = mysql_settings()
    connection = get_server_db()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{settings['database']}` CHARACTER SET {settings['charset']}"
            )
        connection.commit()
    finally:
        connection.close()


def execute_schema() -> None:
    # Execute SQL bootstrap script in an idempotent way.
    if not mysql_configured() or not SCHEMA_FILE.exists():
        return
    statements = [item.strip() for item in SCHEMA_FILE.read_text(encoding="utf-8").split(";") if item.strip()]
    connection = get_db()
    try:
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
        connection.commit()
    finally:
        connection.close()


def query_all(sql: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
    ensure_mysql_configured()
    connection = get_db()
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params or ())
            return list(cursor.fetchall())
    finally:
        connection.close()


def query_one(sql: str, params: tuple[Any, ...] | None = None) -> dict[str, Any] | None:
    ensure_mysql_configured()
    connection = get_db()
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params or ())
            return cursor.fetchone()
    finally:
        connection.close()


def execute_write(sql: str, params: tuple[Any, ...] | None = None) -> int:
    ensure_mysql_configured()
    connection = get_db()
    try:
        with connection.cursor() as cursor:
            affected = cursor.execute(sql, params or ())
        connection.commit()
        return affected
    finally:
        connection.close()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    return hmac.compare_digest(hash_password(password), password_hash)


def get_user_by_username(username: str) -> dict[str, Any] | None:
    return query_one(
        """
        SELECT id, username, password_hash, display_name, created_at
        FROM users
        WHERE username = %s
        LIMIT 1
        """,
        (username,),
    )


def ensure_admin_user() -> None:
    # Ensure default admin account exists for first login.
    if not mysql_configured():
        return
    username = os.getenv("ADMIN_USERNAME", "admin").strip() or "admin"
    password = os.getenv("ADMIN_PASSWORD", "admin123").strip() or "admin123"
    display_name = os.getenv("ADMIN_DISPLAY_NAME", "系统管理员").strip() or "系统管理员"
    existing = get_user_by_username(username)
    if existing:
        return
    execute_write(
        """
        INSERT INTO users (username, password_hash, display_name, created_at)
        VALUES (%s, %s, %s, %s)
        """,
        (username, hash_password(password), display_name, datetime.now()),
    )


def current_user(request: Request) -> dict[str, Any] | None:
    username = request.session.get("username")
    if not username:
        return None
    if not mysql_ready():
        return {"username": username, "display_name": username}
    return get_user_by_username(username)


def template_user(user: dict[str, Any] | None) -> dict[str, str] | None:
    if not user:
        return None
    return {
        "username": str(user.get("username", "")),
        "display_name": str(user.get("display_name", "") or user.get("username", "")),
    }


def require_page_login(request: Request):
    # HTML pages use redirect semantics for anonymous users.
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return user


def require_api_login(request: Request) -> dict[str, Any]:
    # APIs return 401 for anonymous users.
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录。")
    return user


def to_iso_date(value: Any) -> str:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    return str(value or "")


def to_iso_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat(timespec="minutes")
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time()).isoformat(timespec="minutes")
    return str(value or "")


def parse_datetime(value: Any, field_name: str) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise HTTPException(status_code=422, detail=f"{field_name} 不能为空。")
    try:
        return datetime.fromisoformat(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"{field_name} 必须是合法的日期时间格式。") from exc


def parse_date(value: Any, field_name: str) -> date:
    raw = str(value or "").strip()
    if not raw:
        raise HTTPException(status_code=422, detail=f"{field_name} 不能为空。")
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"{field_name} 必须是合法的日期格式。") from exc


def parse_int_range(value: Any, field_name: str, min_value: int = 0, max_value: int = 100) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"{field_name} 必须是整数。") from exc
    if number < min_value or number > max_value:
        raise HTTPException(status_code=422, detail=f"{field_name} 必须在 {min_value} 到 {max_value} 之间。")
    return number


def parse_strict_id(value: Any, field_name: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"{field_name} 必须是整数。") from exc
    if number < 1 or number > MAX_ID_VALUE:
        raise HTTPException(status_code=422, detail=f"{field_name} 必须在 1 到 {MAX_ID_VALUE} 之间。")
    return number


def parse_float(value: Any, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"{field_name} 必须是数字。") from exc


def format_window(start_at: Any, end_at: Any) -> str:
    start_value = to_iso_datetime(start_at)
    end_value = to_iso_datetime(end_at)
    if not start_value and not end_value:
        return "未排期"
    if start_value and end_value:
        return f"{start_value} - {end_value}"
    return start_value or end_value


def parse_zone_path(value: Any) -> list[list[float]]:
    # Accept both JSON string and parsed list payload formats.
    if isinstance(value, list):
        path = value
    else:
        raw = str(value or "").strip()
        if not raw:
            raise HTTPException(status_code=422, detail="区域路径不能为空。")
        try:
            path = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail="区域路径必须是合法的 JSON。") from exc
    points: list[list[float]] = []
    for item in path:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise HTTPException(status_code=422, detail="区域路径中的每个点都必须包含经度和纬度。")
        lng = parse_float(item[0], "区域经度")
        lat = parse_float(item[1], "区域纬度")
        points.append([lng, lat])
    if len(points) < 3:
        raise HTTPException(status_code=422, detail="区域路径至少需要三个点。")
    return points


def zone_exists(zone_id: Any) -> bool:
    if zone_id is None:
        return False
    return bool(query_one("SELECT id FROM zones WHERE id = %s LIMIT 1", (zone_id,)))


def robot_exists(robot_id: Any) -> bool:
    if robot_id is None:
        return False
    return bool(query_one("SELECT id FROM robots WHERE id = %s LIMIT 1", (robot_id,)))


def zone_center(path: list[list[float]]) -> list[float]:
    lng_total = sum(point[0] for point in path)
    lat_total = sum(point[1] for point in path)
    count = len(path)
    return [round(lng_total / count, 6), round(lat_total / count, 6)]


def load_zones() -> list[dict[str, Any]]:
    # Normalize DB fields to frontend-friendly keys.
    rows = query_all(
        """
        SELECT id, name, type, risk, status, frequency, stroke_color, fill_color, path_json, notes, created_at
        FROM zones
        ORDER BY created_at DESC, id DESC
        """
    )
    zones = []
    for row in rows:
        path = parse_zone_path(row["path_json"])
        zones.append(
            {
                "id": row["id"],
                "name": row["name"],
                "type": row["type"],
                "risk": row["risk"],
                "status": row["status"],
                "frequency": row["frequency"],
                "strokeColor": row["stroke_color"] or "#7cc7ff",
                "fillColor": row["fill_color"] or "rgba(124, 199, 255, 0.18)",
                "path": path,
                "notes": row["notes"] or "",
                "createdAt": to_iso_datetime(row["created_at"]),
                "center": zone_center(path),
            }
        )
    return zones


def load_robots() -> list[dict[str, Any]]:
    rows = query_all(
        """
        SELECT r.id, r.model, r.zone_id, z.name AS zone_name, r.status, r.health, r.battery, r.speed,
               r.`signal` AS signal_value, r.latency, r.lng, r.lat, r.heading, r.created_at
        FROM robots r
        LEFT JOIN zones z ON z.id = r.zone_id
        ORDER BY r.created_at DESC, r.id DESC
        """
    )
    return [
        {
            "id": row["id"],
            "model": row["model"],
            "zoneId": row["zone_id"],
            "zoneName": row["zone_name"] or "未分配",
            "status": row["status"],
            "health": int(row["health"]),
            "battery": int(row["battery"]),
            "speed": float(row["speed"]),
            "signal": int(row["signal_value"]),
            "latency": int(row["latency"]),
            "location": [float(row["lng"]), float(row["lat"])],
            "heading": int(row["heading"]),
            "createdAt": to_iso_datetime(row["created_at"]),
        }
        for row in rows
    ]


def load_tasks() -> list[dict[str, Any]]:
    rows = query_all(
        """
        SELECT t.id, t.name, t.robot_id, r.model AS robot_name, t.zone_id, z.name AS zone_name,
               t.priority, t.description, t.start_at, t.end_at, t.status, t.created_at
        FROM tasks t
        LEFT JOIN robots r ON r.id = t.robot_id
        LEFT JOIN zones z ON z.id = t.zone_id
        ORDER BY t.start_at DESC, t.id DESC
        """
    )
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "robotId": row["robot_id"],
            "robotName": row["robot_name"] or "未分配",
            "zoneId": row["zone_id"],
            "zoneName": row["zone_name"] or "未分配",
            "priority": row["priority"],
            "description": row["description"] or "",
            "startAt": to_iso_datetime(row["start_at"]),
            "endAt": to_iso_datetime(row["end_at"]),
            "status": row["status"],
            "window": format_window(row["start_at"], row["end_at"]),
            "createdAt": to_iso_datetime(row["created_at"]),
        }
        for row in rows
    ]


def load_alerts() -> list[dict[str, Any]]:
    rows = query_all(
        """
        SELECT id, level, title, detail, happened_at, created_at
        FROM alerts
        ORDER BY happened_at DESC, id DESC
        """
    )
    return [
        {
            "id": row["id"],
            "level": row["level"],
            "title": row["title"],
            "detail": row["detail"] or "",
            "happenedAt": to_iso_datetime(row["happened_at"]),
            "createdAt": to_iso_datetime(row["created_at"]),
        }
        for row in rows
    ]


def load_reports() -> list[dict[str, Any]]:
    rows = query_all(
        """
        SELECT id, title, value, trend, tone, detail, report_date, created_at
        FROM reports
        ORDER BY report_date DESC, id DESC
        """
    )
    return [
        {
            "id": row["id"],
            "title": row["title"],
            "value": row["value"],
            "trend": row["trend"],
            "tone": row["tone"],
            "detail": row["detail"] or "",
            "reportDate": to_iso_date(row["report_date"]),
            "createdAt": to_iso_datetime(row["created_at"]),
        }
        for row in rows
    ]


def build_maintenance_items(robots: list[dict[str, Any]], alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Aggregate maintenance feed using real robot status from DB.
    _STATUS_MAP = {
        "active": ("active", "正在执行巡检任务。"),
        "idle": ("healthy", "机器人待命中，状态正常。"),
        "charging": ("healthy", "机器人正在充电。"),
        "offline": ("critical", "机器人已离线，需要人工介入。"),
    }
    items = []
    for robot in robots:
        raw_status = str(robot.get("status", "")).lower()
        state, summary = _STATUS_MAP.get(raw_status, ("warning", "状态未知，请确认机器人连接。"))
        # Low battery overrides to warning unless already critical.
        if state != "critical" and robot["battery"] < 20:
            state = "warning"
            summary = f"电量偏低（{robot['battery']}%），建议及时充电。"
        items.append(
            {
                "id": f"robot-{robot['id']}",
                "asset": robot["model"],
                "zoneName": robot["zoneName"],
                "state": state,
                "summary": summary,
                "lastCheck": robot["createdAt"],
                "battery": robot["battery"],
                "health": robot["health"],
            }
        )
    for alert in alerts[:4]:
        items.append(
            {
                "id": f"alert-{alert['id']}",
                "asset": alert["title"],
                "zoneName": "系统",
                "state": "critical" if alert["level"] == "critical" else "warning",
                "summary": alert["detail"] or "需要后续处理。",
                "lastCheck": alert["happenedAt"],
                "battery": None,
                "health": None,
            }
        )
    return items


def empty_dashboard_payload() -> dict[str, Any]:
    return {
        "site": DEFAULT_SITE,
        "counts": {"robots": 0, "tasks": 0, "alerts": 0, "reports": 0, "zones": 0},
        "robots": [],
        "tasks": [],
        "alerts": [],
        "reports": [],
        "zones": [],
        "maintenance": [],
        "generatedAt": datetime.now().isoformat(timespec="minutes"),
    }


def build_dashboard_payload() -> dict[str, Any]:
    if not mysql_ready():
        return empty_dashboard_payload()
    zones = load_zones()
    robots = load_robots()
    tasks = load_tasks()
    alerts = load_alerts()
    reports = load_reports()
    return {
        "site": DEFAULT_SITE,
        "counts": {
            "robots": len(robots),
            "tasks": len(tasks),
            "alerts": len(alerts),
            "reports": len(reports),
            "zones": len(zones),
        },
        "robots": robots,
        "tasks": tasks,
        "alerts": alerts,
        "reports": reports,
        "zones": zones,
        "maintenance": build_maintenance_items(robots, alerts),
        "generatedAt": datetime.now().isoformat(timespec="minutes"),
    }


def ws_dashboard_message(event: str) -> dict[str, Any]:
    # Unified websocket payload shape used by all push events.
    return {
        "type": "dashboard_update",
        "event": event,
        "pages": PAGES,
        "data": build_dashboard_payload(),
        "serverTime": datetime.now().isoformat(timespec="seconds"),
    }


async def ws_register(websocket: WebSocket) -> None:
    async with WS_LOCK:
        WS_CLIENTS.add(websocket)


async def ws_unregister(websocket: WebSocket) -> None:
    async with WS_LOCK:
        WS_CLIENTS.discard(websocket)


async def ws_broadcast(event: str) -> None:
    # Broadcast full dashboard snapshot and prune dead connections.
    async with WS_LOCK:
        clients = list(WS_CLIENTS)
    if not clients:
        return
    message = ws_dashboard_message(event)
    stale: list[WebSocket] = []
    for client in clients:
        try:
            await client.send_json(message)
        except Exception:
            stale.append(client)
    if stale:
        async with WS_LOCK:
            for client in stale:
                WS_CLIENTS.discard(client)






def build_alert_record(payload: dict[str, Any]) -> dict[str, Any]:
    title = str(payload.get("title", "")).strip()
    if not title:
        raise HTTPException(status_code=422, detail="告警标题不能为空。")
    level = str(payload.get("level", "warning")).strip() or "warning"
    if level not in {"info", "warning", "critical"}:
        raise HTTPException(status_code=422, detail="告警等级必须是 info、warning 或 critical。")
    happened_at = payload.get("happenedAt")
    return {
        "level": level,
        "title": title,
        "detail": str(payload.get("detail", "")).strip(),
        "happened_at": parse_datetime(happened_at, "happenedAt") if happened_at else datetime.now(),
        "created_at": datetime.now(),
    }


def build_report_record(payload: dict[str, Any]) -> dict[str, Any]:
    title = str(payload.get("title", "")).strip()
    value = str(payload.get("value", "")).strip()
    if not title or not value:
        raise HTTPException(status_code=422, detail="报告标题和指标值不能为空。")
    return {
        "title": title,
        "value": value,
        "trend": str(payload.get("trend", "0%")).strip() or "0%",
        "tone": str(payload.get("tone", "neutral")).strip() or "neutral",
        "detail": str(payload.get("detail", "")).strip(),
        "report_date": parse_date(payload.get("reportDate"), "reportDate"),
        "created_at": datetime.now(),
    }


def build_zone_record(payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=422, detail="区域名称不能为空。")
    path = parse_zone_path(payload.get("path"))
    return {
        "name": name,
        "type": str(payload.get("type", "inspection")).strip() or "inspection",
        "risk": str(payload.get("risk", "medium")).strip() or "medium",
        "status": str(payload.get("status", "active")).strip() or "active",
        "frequency": str(payload.get("frequency", "30分钟/次")).strip() or "30分钟/次",
        "stroke_color": str(payload.get("strokeColor", "#7cc7ff")).strip() or "#7cc7ff",
        "fill_color": str(payload.get("fillColor", "rgba(124, 199, 255, 0.18)")).strip()
        or "rgba(124, 199, 255, 0.18)",
        "path_json": json.dumps(path, ensure_ascii=False),
        "notes": str(payload.get("notes", "")).strip(),
        "created_at": datetime.now(),
    }


def insert_robot(record: dict[str, Any]) -> None:
    execute_write(
        """
        INSERT INTO robots (
            model, zone_id, status, health, battery, speed, `signal`, latency, lng, lat, heading, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            record["model"],
            record["zone_id"],
            record["status"],
            record["health"],
            record["battery"],
            record["speed"],
            record["signal"],
            record["latency"],
            record["lng"],
            record["lat"],
            record["heading"],
            record["created_at"],
        ),
    )


def insert_task(record: dict[str, Any]) -> None:
    execute_write(
        """
        INSERT INTO tasks (
            name, robot_id, zone_id, priority, description, start_at, end_at, status, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            record["name"],
            record["robot_id"],
            record["zone_id"],
            record["priority"],
            record["description"],
            record["start_at"],
            record["end_at"],
            record["status"],
            record["created_at"],
        ),
    )


def insert_alert(record: dict[str, Any]) -> None:
    execute_write(
        """
        INSERT INTO alerts (level, title, detail, happened_at, created_at)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            record["level"],
            record["title"],
            record["detail"],
            record["happened_at"],
            record["created_at"],
        ),
    )


def insert_report(record: dict[str, Any]) -> None:
    execute_write(
        """
        INSERT INTO reports (title, value, trend, tone, detail, report_date, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            record["title"],
            record["value"],
            record["trend"],
            record["tone"],
            record["detail"],
            record["report_date"],
            record["created_at"],
        ),
    )


def insert_zone(record: dict[str, Any]) -> None:
    execute_write(
        """
        INSERT INTO zones (
            name, type, risk, status, frequency, stroke_color, fill_color, path_json, notes, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            record["name"],
            record["type"],
            record["risk"],
            record["status"],
            record["frequency"],
            record["stroke_color"],
            record["fill_color"],
            record["path_json"],
            record["notes"],
            record["created_at"],
        ),
    )




def build_robot_record(payload: dict[str, Any]) -> dict[str, Any]:
    model = str(payload.get("model", "")).strip()
    if not model:
        raise HTTPException(status_code=422, detail="机器人名称不能为空。")
    zone_id = payload.get("zoneId")
    if zone_id is not None:
        zone_id = parse_strict_id(zone_id, "zoneId")
        if not zone_exists(zone_id):
            raise HTTPException(status_code=404, detail="未找到对应区域。")
    return {
        "model": model,
        "zone_id": zone_id,
        "status": str(payload.get("status", "idle")).strip() or "idle",
        "health": parse_int_range(payload.get("health", 92), "health"),
        "battery": parse_int_range(payload.get("battery", 78), "battery"),
        "speed": parse_float(payload.get("speed", 1.2), "speed"),
        "signal": parse_int_range(payload.get("signal", 88), "signal"),
        "latency": parse_int_range(payload.get("latency", 28), "latency", 0, 1000),
        "lng": parse_float(payload.get("lng", DEFAULT_SITE["center"][0]), "lng"),
        "lat": parse_float(payload.get("lat", DEFAULT_SITE["center"][1]), "lat"),
        "heading": parse_int_range(payload.get("heading", 0), "heading", 0, 359),
        "created_at": datetime.now(),
    }


def build_task_record(payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=422, detail="任务名称不能为空。")
    robot_id = payload.get("robotId")
    zone_id = payload.get("zoneId")
    if robot_id is not None:
        robot_id = parse_strict_id(robot_id, "robotId")
        if not robot_exists(robot_id):
            raise HTTPException(status_code=404, detail="未找到对应机器人。")
    if zone_id is not None:
        zone_id = parse_strict_id(zone_id, "zoneId")
        if not zone_exists(zone_id):
            raise HTTPException(status_code=404, detail="未找到对应区域。")
    start_at = parse_datetime(payload.get("startAt"), "startAt")
    end_at = parse_datetime(payload.get("endAt"), "endAt")
    if end_at <= start_at:
        raise HTTPException(status_code=422, detail="结束时间必须晚于开始时间。")
    return {
        "name": name,
        "robot_id": robot_id,
        "zone_id": zone_id,
        "priority": str(payload.get("priority", "medium")).strip() or "medium",
        "description": str(payload.get("description", "")).strip(),
        "start_at": start_at,
        "end_at": end_at,
        "status": str(payload.get("status", "scheduled")).strip() or "scheduled",
        "created_at": datetime.now(),
    }


def clear_table(table_name: str, record_id: int) -> int:
    return execute_write(f"DELETE FROM {table_name} WHERE id = %s", (record_id,))


def amap_script_tag() -> str:
    amap_key = os.getenv("AMAP_WEB_KEY", "").strip()
    if not amap_key:
        return ""
    return (
        '<script src="https://webapi.amap.com/maps?v=2.0&key='
        f"{amap_key}"
        '&plugin=AMap.Scale,AMap.ToolBar,AMap.PolygonEditor,AMap.Geolocation,AMap.Geocoder"></script>'
    )


def render_page(request: Request, page_id: str) -> HTMLResponse | RedirectResponse:
    # Common page renderer for all protected web pages.
    user = require_page_login(request)
    if isinstance(user, RedirectResponse):
        return user
    safe_user = template_user(user)
    page = PAGES[page_id]
    return templates.TemplateResponse(
        request,
        "app.html",
        {
            "page_id": page_id,
            "page_title": page["title"],
            "page_route": page["route"],
            "page_kicker": page["kicker"],
            "amap_key": os.getenv("AMAP_WEB_KEY", "").strip(),
            "amap_script": amap_script_tag(),
            "current_user": safe_user,
            "pages": PAGES,
            "site": DEFAULT_SITE,
            "mysql_ready": mysql_ready(),
        },
    )


def redirect_legacy_page(request: Request, page_id: str) -> RedirectResponse:
    user = require_page_login(request)
    if isinstance(user, RedirectResponse):
        return user
    return RedirectResponse(url=PAGES[page_id]["route"], status_code=302)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Application startup bootstrap: DB + schema + admin seed.
    if mysql_configured():
        try:
            ensure_database()
            execute_schema()
            ensure_admin_user()
            APP_STATE["db_ready"] = True
            APP_STATE["db_error"] = ""
        except Exception as exc:  # pragma: no cover - startup resilience
            APP_STATE["db_ready"] = False
            APP_STATE["db_error"] = str(exc)
    else:
        APP_STATE["db_ready"] = False
        APP_STATE["db_error"] = "MySQL 未配置。"
    yield


app = FastAPI(title="鏈哄櫒浜哄贰妫€骞冲彴", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "change-me"))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# Auth + page routes
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "mysql_ready": mysql_ready(),
            "mysql_error": APP_STATE["db_error"],
            "current_user": template_user(current_user(request)),
        },
    )


@app.post("/auth/login")
async def login(request: Request) -> JSONResponse:
    if not mysql_ready():
        raise HTTPException(status_code=503, detail=APP_STATE["db_error"] or "MySQL 当前不可用。")
    payload = await request.json()
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", "")).strip()
    if not username or not password:
        raise HTTPException(status_code=422, detail="用户名和密码不能为空。")
    user = get_user_by_username(username)
    if not user or not verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误。")
    request.session["username"] = user["username"]
    return JSONResponse(
        {
            "ok": True,
            "user": {"username": user["username"], "displayName": user["display_name"]},
            "redirect": PAGES["overview"]["route"],
        }
    )


@app.post("/auth/logout")
async def logout(request: Request) -> JSONResponse:
    request.session.clear()
    return JSONResponse({"ok": True, "redirect": "/login"})


@app.get("/", response_class=HTMLResponse)
async def root_page(request: Request):
    return redirect_legacy_page(request, "overview")


@app.get("/overview", response_class=HTMLResponse)
async def overview_page(request: Request):
    return render_page(request, "overview")


@app.get("/_3", response_class=HTMLResponse)
async def legacy_tasks_page(request: Request):
    return redirect_legacy_page(request, "tasks")


@app.get("/tasks", response_class=HTMLResponse)
async def tasks_page(request: Request):
    return render_page(request, "tasks")


@app.get("/_1", response_class=HTMLResponse)
async def legacy_reports_page(request: Request):
    return redirect_legacy_page(request, "reports")


@app.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request):
    return render_page(request, "reports")


@app.get("/monitoring_dashboard", response_class=HTMLResponse)
async def legacy_status_page(request: Request):
    return redirect_legacy_page(request, "status")


@app.get("/robots", response_class=HTMLResponse)
async def status_page(request: Request):
    return render_page(request, "status")


@app.get("/maintenance", response_class=HTMLResponse)
async def maintenance_page(request: Request):
    return render_page(request, "maintenance")


@app.get("/zone_control", response_class=HTMLResponse)
async def legacy_zones_page(request: Request):
    return redirect_legacy_page(request, "zones")


@app.get("/zones", response_class=HTMLResponse)
async def zones_page(request: Request):
    return render_page(request, "zones")


@app.get("/api/dashboard")
async def api_dashboard(request: Request) -> JSONResponse:
    require_api_login(request)
    return JSONResponse({"pages": PAGES, "data": build_dashboard_payload()})


# Health + realtime routes
@app.get("/api/health")
async def api_health() -> JSONResponse:
    configured = mysql_configured()
    ready = mysql_ready()
    status = "ok" if ready else "degraded"
    payload = {
        "status": status,
        "mysqlConfigured": configured,
        "mysqlReady": ready,
        "detail": APP_STATE["db_error"] if APP_STATE["db_error"] else "",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    return JSONResponse(payload, status_code=200 if ready else 503)


@app.websocket("/ws/dashboard")
async def ws_dashboard(websocket: WebSocket):
    session = websocket.scope.get("session") or {}
    if not session.get("username"):
        await websocket.close(code=4401)
        return
    await websocket.accept()
    await ws_register(websocket)
    try:
        await websocket.send_json(ws_dashboard_message("connected"))
        while True:
            message = await websocket.receive_text()
            if message.strip().lower() in {"ping", "heartbeat"}:
                await websocket.send_json({"type": "pong", "serverTime": datetime.now().isoformat(timespec="seconds")})
            elif message.strip().lower() == "refresh":
                await websocket.send_json(ws_dashboard_message("refresh"))
    except WebSocketDisconnect:
        pass
    finally:
        await ws_unregister(websocket)


# CRUD API routes
@app.get("/api/tasks")
async def api_tasks(request: Request) -> JSONResponse:
    require_api_login(request)
    return JSONResponse({"items": load_tasks() if mysql_ready() else []})


@app.post("/api/tasks")
async def api_create_task(request: Request) -> JSONResponse:
    require_api_login(request)
    record = build_task_record(await request.json())
    insert_task(record)
    await ws_broadcast("task_created")
    return JSONResponse({"ok": True})


@app.delete("/api/tasks/{task_id}")
async def api_delete_task(task_id: int, request: Request) -> JSONResponse:
    require_api_login(request)
    task_id = parse_strict_id(task_id, "task_id")
    if clear_table("tasks", task_id) == 0:
        raise HTTPException(status_code=404, detail="未找到对应任务。")
    await ws_broadcast("task_deleted")
    return JSONResponse({"ok": True})


@app.get("/api/robots")
async def api_robots(request: Request) -> JSONResponse:
    require_api_login(request)
    return JSONResponse({"items": load_robots() if mysql_ready() else []})


@app.post("/api/robots")
async def api_create_robot(request: Request) -> JSONResponse:
    require_api_login(request)
    record = build_robot_record(await request.json())
    insert_robot(record)
    await ws_broadcast("robot_created")
    return JSONResponse({"ok": True})


@app.delete("/api/robots/{robot_id}")
async def api_delete_robot(robot_id: int, request: Request) -> JSONResponse:
    require_api_login(request)
    robot_id = parse_strict_id(robot_id, "robot_id")
    if clear_table("robots", robot_id) == 0:
        raise HTTPException(status_code=404, detail="未找到对应机器人。")
    await ws_broadcast("robot_deleted")
    return JSONResponse({"ok": True})


@app.get("/api/alerts")
async def api_alerts(request: Request) -> JSONResponse:
    require_api_login(request)
    return JSONResponse({"items": load_alerts() if mysql_ready() else []})


@app.post("/api/alerts")
async def api_create_alert(request: Request) -> JSONResponse:
    require_api_login(request)
    record = build_alert_record(await request.json())
    insert_alert(record)
    await ws_broadcast("alert_created")
    return JSONResponse({"ok": True})


@app.delete("/api/alerts/{alert_id}")
async def api_delete_alert(alert_id: int, request: Request) -> JSONResponse:
    require_api_login(request)
    alert_id = parse_strict_id(alert_id, "alert_id")
    if clear_table("alerts", alert_id) == 0:
        raise HTTPException(status_code=404, detail="未找到对应告警。")
    await ws_broadcast("alert_deleted")
    return JSONResponse({"ok": True})


@app.get("/api/reports")
async def api_reports(request: Request) -> JSONResponse:
    require_api_login(request)
    return JSONResponse({"items": load_reports() if mysql_ready() else []})


@app.post("/api/reports")
async def api_create_report(request: Request) -> JSONResponse:
    require_api_login(request)
    record = build_report_record(await request.json())
    insert_report(record)
    await ws_broadcast("report_created")
    return JSONResponse({"ok": True})


@app.delete("/api/reports/{report_id}")
async def api_delete_report(report_id: int, request: Request) -> JSONResponse:
    require_api_login(request)
    report_id = parse_strict_id(report_id, "report_id")
    if clear_table("reports", report_id) == 0:
        raise HTTPException(status_code=404, detail="未找到对应报告。")
    await ws_broadcast("report_deleted")
    return JSONResponse({"ok": True})


@app.get("/api/zones")
async def api_zones(request: Request) -> JSONResponse:
    require_api_login(request)
    return JSONResponse({"items": load_zones() if mysql_ready() else []})


@app.post("/api/zones")
async def api_create_zone(request: Request) -> JSONResponse:
    require_api_login(request)
    record = build_zone_record(await request.json())
    insert_zone(record)
    await ws_broadcast("zone_created")
    return JSONResponse({"ok": True})


# Utility + prototype routes
@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204)


@app.get("/prototype/{prototype_name}", response_class=HTMLResponse)
async def prototype_page(prototype_name: str) -> HTMLResponse:
    if prototype_name not in PROTOTYPES:
        raise HTTPException(status_code=404, detail="未找到原型页面。")
    html_file = PROTOTYPE_DIR / prototype_name / "code.html"
    if not html_file.exists():
        raise HTTPException(status_code=404, detail="原型文件不存在。")
    return HTMLResponse(html_file.read_text(encoding="utf-8"))


@app.get("/prototype/{prototype_name}/screen.png", include_in_schema=False)
async def prototype_screen(prototype_name: str):
    if prototype_name not in PROTOTYPES:
        raise HTTPException(status_code=404, detail="未找到原型页面。")
    png_file = PROTOTYPE_DIR / prototype_name / "screen.png"
    if not png_file.exists():
        raise HTTPException(status_code=404, detail="原型截图不存在。")
    return FileResponse(path=png_file)
