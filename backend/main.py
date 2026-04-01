from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import asyncio
import re
import shutil
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from threading import Lock
from typing import Any, Optional

import pymysql
from fastapi import FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pymysql.cursors import DictCursor
from starlette.middleware.sessions import SessionMiddleware

# Runtime paths and bootstrap file locations.
BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
PROTOTYPE_DIR = BASE_DIR / "stitch_monitoring_dashboard"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
ROOT_ENV_FILE = ROOT_DIR / ".env"
ENV_FILE = BASE_DIR / ".env"
SCHEMA_FILE = BASE_DIR / "db" / "mysql_schema.sql"


def asset_version() -> str:
    candidates = (
        STATIC_DIR / "dashboard.css",
        STATIC_DIR / "dashboard.js",
        STATIC_DIR / "login.js",
        TEMPLATES_DIR / "app.html",
        TEMPLATES_DIR / "login.html",
    )
    mtimes = [path.stat().st_mtime for path in candidates if path.exists()]
    return str(int(max(mtimes, default=time.time())))

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
    "users": {"route": "/users", "title": "用户管理", "kicker": "账号中心"},
    "devices": {"route": "/devices", "title": "设备管理", "kicker": "设备信息"},
    "areas": {"route": "/areas", "title": "巡检区域", "kicker": "区域配置"},
    "points": {"route": "/points", "title": "巡检点", "kicker": "点位配置"},
    "routes": {"route": "/routes", "title": "巡检路线", "kicker": "路线配置"},
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
ROBOT_DISCOVERY_TTL_SECONDS = 300
ROBOT_DISCOVERY_TIMEOUT_SECONDS = 0.18
ROBOT_IDENTITY_TTL_HOURS = 24
ROBOT_DISCOVERY_PORTS = (22, 80, 443, 8000)
ROBOT_TELEMETRY_OFFLINE_SECONDS = 180
ROBOT_WEAK_SIGNAL_THRESHOLD = 35
ROBOT_DISCOVERY_HOST_HINTS = ("raspberry", "robot", "agv", "car", "rover", "pi")
RASPBERRY_PI_MAC_PREFIXES = {
    "28CDC1",
    "2CCF67",
    "B827EB",
    "D83ADD",
    "DCA632",
    "E45F01",
}
ROBOT_DISCOVERY_CACHE: dict[str, Any] = {"items": [], "scanned_at": 0.0, "subnets": []}
ROBOT_DISCOVERY_LOCK = Lock()


def load_local_env(path: Path, overwrite: bool = True) -> None:
    # Minimal .env loader to keep deployment dependency-free.
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if overwrite or key not in os.environ:
            os.environ[key] = value


load_local_env(ROOT_ENV_FILE, overwrite=False)
load_local_env(ENV_FILE, overwrite=True)


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


def schema_tables_ready(table_names: tuple[str, ...]) -> bool:
    if not mysql_configured():
        return False
    settings = mysql_settings()
    connection = get_server_db()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) AS total
                FROM information_schema.tables
                WHERE table_schema = %s AND table_name IN %s
                """,
                (settings["database"], table_names),
            )
            row = cursor.fetchone() or {}
        return int(row.get("total", 0) or 0) == len(table_names)
    finally:
        connection.close()


def execute_schema() -> None:
    # Execute SQL bootstrap script in an idempotent way.
    if not mysql_configured() or not SCHEMA_FILE.exists():
        return
    if schema_tables_ready(("users", "robots", "zones", "tasks", "alerts", "reports")):
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


def ensure_iot_tables() -> None:
    if not mysql_configured():
        return
    connection = get_db()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS device_tokens (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT,
                    device_id BIGINT NOT NULL,
                    token VARCHAR(128) NOT NULL UNIQUE,
                    note VARCHAR(256) NULL,
                    is_active TINYINT(1) NOT NULL DEFAULT 1,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT fk_dt_device FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS device_checkins (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT,
                    device_id BIGINT NOT NULL,
                    point_id BIGINT NULL,
                    route_id BIGINT NULL,
                    lat DECIMAL(10,7) NULL,
                    lng DECIMAL(10,7) NULL,
                    note TEXT NULL,
                    checked_at DATETIME NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT fk_ci_device FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
                    CONSTRAINT fk_ci_point FOREIGN KEY (point_id) REFERENCES points(id) ON DELETE SET NULL,
                    CONSTRAINT fk_ci_route FOREIGN KEY (route_id) REFERENCES routes(id) ON DELETE SET NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS device_telemetry (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT,
                    device_id BIGINT NOT NULL,
                    battery TINYINT NULL,
                    `signal` TINYINT NULL,
                    status VARCHAR(32) NULL,
                    lat DECIMAL(10,7) NULL,
                    lng DECIMAL(10,7) NULL,
                    source_ip VARCHAR(64) NULL,
                    extra_json JSON NULL,
                    reported_at DATETIME NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT fk_tel_device FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
                )
                """
            )
            cursor.execute("SHOW COLUMNS FROM device_telemetry LIKE 'source_ip'")
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE device_telemetry ADD COLUMN source_ip VARCHAR(64) NULL AFTER lng")
            cursor.execute("SHOW INDEX FROM device_telemetry WHERE Key_name = 'idx_telemetry_device_time'")
            if not cursor.fetchone():
                cursor.execute("CREATE INDEX idx_telemetry_device_time ON device_telemetry (device_id, reported_at DESC)")
        connection.commit()
    finally:
        connection.close()


def ensure_robot_ip_column() -> None:
    if not mysql_configured():
        return
    connection = get_db()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SHOW COLUMNS FROM robots LIKE 'ip_address'")
            if cursor.fetchone():
                connection.commit()
                return
            cursor.execute("ALTER TABLE robots ADD COLUMN ip_address VARCHAR(64) NULL AFTER model")
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


def execute_insert(sql: str, params: tuple[Any, ...] | None = None) -> int:
    ensure_mysql_configured()
    connection = get_db()
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params or ())
            inserted_id = int(cursor.lastrowid or 0)
        connection.commit()
        return inserted_id
    finally:
        connection.close()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    return hmac.compare_digest(hash_password(password), password_hash)


def get_user_by_username(username: str) -> dict[str, Any] | None:
    return query_one(
        """
        SELECT id, username, password_hash, display_name, status, created_at
        FROM users
        WHERE username = %s
        LIMIT 1
        """,
        (username,),
    )


def validate_auth_user_payload(payload: dict[str, Any]) -> tuple[str, str, str]:
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", "")).strip()
    display_name = str(payload.get("displayName", username)).strip() or username
    if not username or not password:
        raise HTTPException(status_code=422, detail="用户名和密码不能为空。")
    if len(username) > 64:
        raise HTTPException(status_code=422, detail="用户名长度不能超过 64 个字符。")
    if len(password) < 6:
        raise HTTPException(status_code=422, detail="密码长度至少为 6 位。")
    if len(display_name) > 128:
        raise HTTPException(status_code=422, detail="显示名称长度不能超过 128 个字符。")
    return username, password, display_name


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
        INSERT INTO users (username, password_hash, display_name, status, created_at)
        VALUES (%s, %s, %s, 'active', %s)
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


def self_registration_allowed() -> bool:
    raw = os.getenv("ALLOW_SELF_REGISTER", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def admin_username() -> str:
    return os.getenv("ADMIN_USERNAME", "admin").strip() or "admin"


def is_admin_user(user: dict[str, Any] | None) -> bool:
    if not user:
        return False
    return str(user.get("username", "")).strip() == admin_username()


def require_admin_login(request: Request) -> dict[str, Any]:
    user = require_api_login(request)
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="仅管理员可执行此操作。")
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


def parse_ipv4(value: Any, field_name: str = "ipAddress") -> str:
    raw = str(value or "").strip()
    if not raw:
        raise HTTPException(status_code=422, detail=f"{field_name} 不能为空。")
    try:
        parsed = ipaddress.ip_address(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"{field_name} 必须是合法的 IPv4 地址。") from exc
    if parsed.version != 4:
        raise HTTPException(status_code=422, detail=f"{field_name} 必须是合法的 IPv4 地址。")
    return str(parsed)


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


def local_ipv4_networks() -> list[ipaddress.IPv4Network]:
    networks: list[ipaddress.IPv4Network] = []
    seen: set[str] = set()
    try:
        output = subprocess.check_output(
            ["ip", "-4", "-o", "addr", "show", "scope", "global"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
        )
        for raw_line in output.splitlines():
            parts = raw_line.split()
            if "inet" not in parts:
                continue
            cidr = parts[parts.index("inet") + 1]
            interface = ipaddress.ip_interface(cidr)
            network = interface.network
            if network.version != 4 or interface.ip.is_loopback:
                continue
            if network.num_addresses > 256:
                network = ipaddress.ip_interface(f"{interface.ip}/24").network
            key = str(network)
            if key not in seen:
                seen.add(key)
                networks.append(network)
    except Exception:
        pass

    if networks:
        return networks

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            ip_text = sock.getsockname()[0]
        fallback = ipaddress.ip_interface(f"{ip_text}/24").network
        return [fallback]
    except Exception:
        return []


def local_ipv4_addresses() -> set[str]:
    addresses: set[str] = set()
    try:
        output = subprocess.check_output(
            ["ip", "-4", "-o", "addr", "show", "scope", "global"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
        )
        for raw_line in output.splitlines():
            parts = raw_line.split()
            if "inet" not in parts:
                continue
            cidr = parts[parts.index("inet") + 1]
            interface = ipaddress.ip_interface(cidr)
            if interface.version == 4 and not interface.ip.is_loopback:
                addresses.add(str(interface.ip))
    except Exception:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            addresses.add(sock.getsockname()[0])
    except Exception:
        pass
    return {item for item in addresses if item}


def probe_tcp_ports(ip_address: str, ports: tuple[int, ...] = ROBOT_DISCOVERY_PORTS) -> list[int]:
    open_ports: list[int] = []
    for port in ports:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(ROBOT_DISCOVERY_TIMEOUT_SECONDS)
                if sock.connect_ex((ip_address, port)) == 0:
                    open_ports.append(port)
        except OSError:
            continue
    return open_ports


def reverse_lookup_host(ip_address: str) -> str:
    try:
        host_name, _, _ = socket.gethostbyaddr(ip_address)
        return host_name
    except OSError:
        return ""


def read_arp_mac(ip_address: str) -> str:
    arp_path = Path("/proc/net/arp")
    if not arp_path.exists():
        return ""
    try:
        for raw_line in arp_path.read_text(encoding="utf-8", errors="ignore").splitlines()[1:]:
            columns = raw_line.split()
            if len(columns) >= 4 and columns[0] == ip_address:
                return columns[3].upper()
    except Exception:
        return ""
    return ""


def normalize_mac_prefix(mac_address: str) -> str:
    return "".join(char for char in mac_address.upper() if char.isalnum())[:6]


def load_recent_iot_identity_map() -> dict[str, dict[str, Any]]:
    if not mysql_ready():
        return {}
    rows = query_all(
        f"""
        SELECT t.source_ip, t.device_id, d.name AS device_name, d.model AS device_model, t.reported_at
        FROM device_telemetry t
        JOIN devices d ON d.id = t.device_id
        WHERE t.source_ip IS NOT NULL
          AND t.source_ip <> ''
          AND t.reported_at >= DATE_SUB(NOW(), INTERVAL {ROBOT_IDENTITY_TTL_HOURS} HOUR)
        ORDER BY t.reported_at DESC, t.id DESC
        """
    )
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        source_ip = str(row.get("source_ip") or "").strip()
        if source_ip and source_ip not in result:
            result[source_ip] = {
                "deviceId": int(row["device_id"]),
                "deviceName": row.get("device_name") or "",
                "deviceModel": row.get("device_model") or "",
                "reportedAt": to_iso_datetime(row["reported_at"]),
            }
    return result


def load_recent_iot_log_identity_map() -> dict[str, dict[str, Any]]:
    if not mysql_ready():
        return {}
    rows = query_all(
        f"""
        SELECT t.device_id, d.name AS device_name, d.model AS device_model, MAX(t.reported_at) AS reported_at
        FROM device_telemetry t
        JOIN devices d ON d.id = t.device_id
        WHERE (t.source_ip IS NULL OR t.source_ip = '')
          AND t.reported_at >= DATE_SUB(NOW(), INTERVAL {ROBOT_IDENTITY_TTL_HOURS} HOUR)
        GROUP BY t.device_id, d.name, d.model
        ORDER BY reported_at DESC
        """
    )
    device_rows = [row for row in rows if row.get("device_id") is not None]
    if len(device_rows) != 1:
        return {}

    try:
        output = subprocess.check_output(
            ["journalctl", "-u", "project4-backend.service", "-n", "400", "--no-pager"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
    except Exception:
        return {}

    ip_matches = re.findall(r'(\d+\.\d+\.\d+\.\d+):\d+\s+-\s+"POST /api/iot/telemetry', output)
    unique_ips: list[str] = []
    for ip_text in ip_matches:
        try:
            normalized = parse_ipv4(ip_text, "source_ip")
        except HTTPException:
            continue
        if normalized not in unique_ips:
            unique_ips.append(normalized)

    if not unique_ips:
        return {}

    device = device_rows[0]
    payload = {
        "deviceId": int(device["device_id"]),
        "deviceName": device.get("device_name") or "",
        "deviceModel": device.get("device_model") or "",
        "reportedAt": to_iso_datetime(device["reported_at"]),
    }
    return {ip_text: dict(payload) for ip_text in unique_ips}


def classify_robot_candidate(
    host_name: str,
    mac_address: str,
    open_ports: list[int],
    iot_identity: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    host_token = host_name.lower()
    host_match = any(token in host_token for token in ROBOT_DISCOVERY_HOST_HINTS)
    mac_match = normalize_mac_prefix(mac_address) in RASPBERRY_PI_MAC_PREFIXES
    clues: list[str] = []
    if iot_identity:
        clues.append(
            f"iot={iot_identity.get('deviceName') or iot_identity.get('deviceModel') or iot_identity.get('deviceId')}"
        )
    if host_match and host_name:
        clues.append(f"hostname={host_name}")
    if mac_match and mac_address:
        clues.append(f"mac={mac_address}")
    if 22 in open_ports:
        clues.append("ssh")
    if any(port in open_ports for port in (80, 443, 8000)):
        clues.append("web")
    confirmed = bool(iot_identity)
    summary = ", ".join(clues) if clues else "reachable host"
    return confirmed, summary


def scan_robot_candidate(ip_address: str, iot_identity_map: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    open_ports = probe_tcp_ports(ip_address)
    if not open_ports:
        return None
    host_name = reverse_lookup_host(ip_address)
    mac_address = read_arp_mac(ip_address)
    iot_identity = iot_identity_map.get(ip_address)
    confirmed, summary = classify_robot_candidate(host_name, mac_address, open_ports, iot_identity)
    return {
        "ipAddress": ip_address,
        "hostName": host_name,
        "macAddress": mac_address,
        "openPorts": open_ports,
        "confirmed": confirmed,
        "summary": summary,
        "deviceId": iot_identity.get("deviceId") if iot_identity else None,
        "deviceName": iot_identity.get("deviceName") if iot_identity else "",
        "deviceModel": iot_identity.get("deviceModel") if iot_identity else "",
        "reportedAt": iot_identity.get("reportedAt") if iot_identity else "",
    }


def discover_robot_candidates(force: bool = False) -> dict[str, Any]:
    now = time.time()
    with ROBOT_DISCOVERY_LOCK:
        if (
            not force
            and ROBOT_DISCOVERY_CACHE["items"]
            and now - float(ROBOT_DISCOVERY_CACHE["scanned_at"] or 0.0) < ROBOT_DISCOVERY_TTL_SECONDS
        ):
            scanned_at = float(ROBOT_DISCOVERY_CACHE["scanned_at"])
            return {
                "items": list(ROBOT_DISCOVERY_CACHE["items"]),
                "scannedAt": datetime.fromtimestamp(scanned_at).isoformat(timespec="seconds"),
                "expiresAt": datetime.fromtimestamp(scanned_at + ROBOT_DISCOVERY_TTL_SECONDS).isoformat(
                    timespec="seconds"
                ),
                "subnets": list(ROBOT_DISCOVERY_CACHE["subnets"]),
            }

    networks = local_ipv4_networks()
    local_ips = local_ipv4_addresses()
    iot_identity_map = load_recent_iot_identity_map()
    if not iot_identity_map:
        iot_identity_map = load_recent_iot_log_identity_map()
    items: list[dict[str, Any]] = []
    futures = []
    with ThreadPoolExecutor(max_workers=48) as executor:
        for network in networks:
            for host in network.hosts():
                ip_text = str(host)
                if ip_text in local_ips:
                    continue
                futures.append(executor.submit(scan_robot_candidate, ip_text, iot_identity_map))
        for future in as_completed(futures):
            candidate = future.result()
            if candidate:
                items.append(candidate)

    items.sort(key=lambda item: (not item["confirmed"], item["hostName"] or item["ipAddress"], item["ipAddress"]))
    with ROBOT_DISCOVERY_LOCK:
        ROBOT_DISCOVERY_CACHE["items"] = items
        ROBOT_DISCOVERY_CACHE["scanned_at"] = now
        ROBOT_DISCOVERY_CACHE["subnets"] = [str(network) for network in networks]

    return {
        "items": list(items),
        "scannedAt": datetime.fromtimestamp(now).isoformat(timespec="seconds"),
        "expiresAt": datetime.fromtimestamp(now + ROBOT_DISCOVERY_TTL_SECONDS).isoformat(timespec="seconds"),
        "subnets": [str(network) for network in networks],
    }


def get_discovered_robot(ip_address: str) -> dict[str, Any] | None:
    with ROBOT_DISCOVERY_LOCK:
        scanned_at = float(ROBOT_DISCOVERY_CACHE["scanned_at"] or 0.0)
        if time.time() - scanned_at > ROBOT_DISCOVERY_TTL_SECONDS:
            return None
        for item in ROBOT_DISCOVERY_CACHE["items"]:
            if item.get("ipAddress") == ip_address:
                return dict(item)
    return None


def zone_center(path: list[list[float]]) -> list[float]:
    lng_total = sum(point[0] for point in path)
    lat_total = sum(point[1] for point in path)
    count = len(path)
    return [round(lng_total / count, 6), round(lat_total / count, 6)]


def point_in_polygon(lng: float, lat: float, polygon: list[list[float]]) -> bool:
    inside = False
    total = len(polygon)
    if total < 3:
        return False
    previous_index = total - 1
    for current_index in range(total):
        current_lng, current_lat = polygon[current_index]
        previous_lng, previous_lat = polygon[previous_index]
        intersects = ((current_lat > lat) != (previous_lat > lat)) and (
            lng
            < (previous_lng - current_lng) * (lat - current_lat) / ((previous_lat - current_lat) or 1e-12)
            + current_lng
        )
        if intersects:
            inside = not inside
        previous_index = current_index
    return inside


def resolve_zone_by_coordinates(lng: float, lat: float) -> dict[str, Any]:
    if not mysql_ready():
        raise HTTPException(status_code=503, detail="MySQL 当前不可用。")
    zones = load_zones()
    if not zones:
        raise HTTPException(status_code=422, detail="请先创建巡检区域，再配置巡检点。")
    for zone in zones:
        if point_in_polygon(lng, lat, zone["path"]):
            return zone
    raise HTTPException(status_code=422, detail="巡检点必须落在已配置的巡检区域内。")


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


def load_zone(zone_id: int) -> dict[str, Any] | None:
    row = query_one(
        """
        SELECT id, name, type, risk, status, frequency, stroke_color, fill_color, path_json, notes, created_at
        FROM zones
        WHERE id = %s
        LIMIT 1
        """,
        (zone_id,),
    )
    if not row:
        return None
    path = parse_zone_path(row["path_json"])
    return {
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


def _coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def derive_robot_network_status(telemetry_status: Any, signal: Any, reported_at: Any) -> str:
    reported_dt = _coerce_datetime(reported_at)
    status = str(telemetry_status or "").strip().lower()
    if status == "offline":
        return "offline"
    if status == "fault":
        return "warning"
    if reported_dt is None:
        return "offline"
    if (datetime.now() - reported_dt).total_seconds() > ROBOT_TELEMETRY_OFFLINE_SECONDS:
        return "offline"
    if signal is not None and int(signal) < ROBOT_WEAK_SIGNAL_THRESHOLD:
        return "warning"
    return "online"


def load_robots() -> list[dict[str, Any]]:
    rows = query_all(
        """
        SELECT r.id, r.model, r.ip_address, r.zone_id, z.name AS zone_name, r.status, r.health, r.battery, r.speed,
               r.`signal` AS signal_value, r.latency, r.lng, r.lat, r.heading, r.created_at,
               (
                   SELECT dt.battery
                   FROM device_telemetry dt
                   WHERE dt.source_ip = r.ip_address
                     AND dt.battery IS NOT NULL
                   ORDER BY dt.reported_at DESC, dt.id DESC
                   LIMIT 1
               ) AS telemetry_battery,
               (
                   SELECT dt.`signal`
                   FROM device_telemetry dt
                   WHERE dt.source_ip = r.ip_address
                     AND dt.`signal` IS NOT NULL
                   ORDER BY dt.reported_at DESC, dt.id DESC
                   LIMIT 1
               ) AS telemetry_signal,
               (
                   SELECT dt.status
                   FROM device_telemetry dt
                   WHERE dt.source_ip = r.ip_address
                     AND dt.status IS NOT NULL
                     AND dt.status <> ''
                   ORDER BY dt.reported_at DESC, dt.id DESC
                   LIMIT 1
               ) AS telemetry_status,
               (
                   SELECT dt.lat
                   FROM device_telemetry dt
                   WHERE dt.source_ip = r.ip_address
                     AND dt.lat IS NOT NULL
                   ORDER BY dt.reported_at DESC, dt.id DESC
                   LIMIT 1
               ) AS telemetry_lat,
               (
                   SELECT dt.lng
                   FROM device_telemetry dt
                   WHERE dt.source_ip = r.ip_address
                     AND dt.lng IS NOT NULL
                   ORDER BY dt.reported_at DESC, dt.id DESC
                   LIMIT 1
               ) AS telemetry_lng,
               (
                   SELECT dt.reported_at
                   FROM device_telemetry dt
                   WHERE dt.source_ip = r.ip_address
                   ORDER BY dt.reported_at DESC, dt.id DESC
                   LIMIT 1
               ) AS telemetry_reported_at,
               (
                   SELECT dt.source_ip
                   FROM device_telemetry dt
                   WHERE dt.source_ip = r.ip_address
                   ORDER BY dt.reported_at DESC, dt.id DESC
                   LIMIT 1
               ) AS telemetry_source_ip
        FROM robots r
        LEFT JOIN zones z ON z.id = r.zone_id
        ORDER BY r.created_at DESC, r.id DESC
        """
    )
    items: list[dict[str, Any]] = []
    for row in rows:
        battery_value = row["telemetry_battery"] if row.get("telemetry_battery") is not None else row["battery"]
        signal_value = row["telemetry_signal"] if row.get("telemetry_signal") is not None else row["signal_value"]
        lng_value = row["telemetry_lng"] if row.get("telemetry_lng") is not None else row["lng"]
        lat_value = row["telemetry_lat"] if row.get("telemetry_lat") is not None else row["lat"]
        last_seen_at = row.get("telemetry_reported_at") or row["created_at"]
        network_status = derive_robot_network_status(row.get("telemetry_status"), signal_value, row.get("telemetry_reported_at"))
        items.append(
            {
                "id": row["id"],
                "model": row["model"],
                "ipAddress": row.get("ip_address") or "",
                "zoneId": row["zone_id"],
                "zoneName": row["zone_name"] or "未分配",
                "status": row["status"],
                "health": int(row["health"]),
                "battery": int(battery_value),
                "speed": float(row["speed"]),
                "signal": int(signal_value),
                "latency": int(row["latency"]),
                "location": [float(lng_value), float(lat_value)],
                "heading": int(row["heading"]),
                "networkStatus": network_status,
                "telemetryStatus": str(row.get("telemetry_status") or ""),
                "lastSeenAt": to_iso_datetime(last_seen_at),
                "locationUpdatedAt": to_iso_datetime(last_seen_at),
                "isRealtime": row.get("telemetry_reported_at") is not None,
                "createdAt": to_iso_datetime(row["created_at"]),
            }
        )
    return items


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
    status_map = {
        "active": ("active", "正在执行巡检任务。"),
        "idle": ("healthy", "机器人待命中，状态正常。"),
        "charging": ("healthy", "机器人正在充电。"),
        "offline": ("critical", "机器人已离线，需要人工介入。"),
    }
    items = []
    for robot in robots:
        raw_status = str(robot.get("status", "")).lower()
        state, summary = status_map.get(raw_status, ("warning", "状态未知，请确认机器人连接。"))
        network_status = str(robot.get("networkStatus", "")).lower()
        if network_status == "offline":
            state = "critical"
            summary = f"网络已离线，最近上报时间 {robot.get('lastSeenAt') or robot['createdAt']}。"
        elif network_status == "warning" and state != "critical":
            state = "warning"
            summary = f"网络状态不稳定（信号 {robot['signal']}%），建议检查链路质量。"
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
                "lastCheck": robot.get("lastSeenAt") or robot["createdAt"],
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
            model, ip_address, zone_id, status, health, battery, speed, `signal`, latency, lng, lat, heading, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            record["model"],
            record["ip_address"],
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
    ip_address = parse_ipv4(payload.get("ipAddress"), "ipAddress")
    discovered = get_discovered_robot(ip_address)
    if not discovered or not discovered.get("confirmed"):
        raise HTTPException(status_code=422, detail="请先扫描当前 Wi-Fi 网络，并选择已确认的机器人后再添加。")
    zone_id = payload.get("zoneId")
    if zone_id is not None:
        zone_id = parse_strict_id(zone_id, "zoneId")
        if not zone_exists(zone_id):
            raise HTTPException(status_code=404, detail="未找到对应区域。")
    return {
        "model": model,
        "ip_address": ip_address,
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
            "asset_version": asset_version(),
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
            ensure_iot_tables()
            ensure_robot_ip_column()
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


app = FastAPI(title="机器人巡检平台", lifespan=lifespan)
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
            "allow_self_register": self_registration_allowed(),
            "current_user": template_user(current_user(request)),
            "asset_version": asset_version(),
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
    if str(user.get("status", "active")).strip().lower() == "disabled":
        raise HTTPException(status_code=403, detail="当前账号已被禁用。")
    request.session["username"] = user["username"]
    return JSONResponse(
        {
            "ok": True,
            "user": {"username": user["username"], "displayName": user["display_name"]},
            "redirect": PAGES["overview"]["route"],
        }
    )


@app.post("/auth/register")
async def register(request: Request) -> JSONResponse:
    if not mysql_ready():
        raise HTTPException(status_code=503, detail=APP_STATE["db_error"] or "MySQL 当前不可用。")
    if not self_registration_allowed():
        raise HTTPException(status_code=403, detail="当前环境未开放注册。")
    payload = await request.json()
    username, password, display_name = validate_auth_user_payload(payload)
    if get_user_by_username(username):
        raise HTTPException(status_code=409, detail="用户名已存在。")
    execute_write(
        "INSERT INTO users (username, password_hash, display_name, status, created_at) VALUES (%s, %s, %s, 'active', %s)",
        (username, hash_password(password), display_name, datetime.now()),
    )
    request.session["username"] = username
    return JSONResponse(
        {
            "ok": True,
            "user": {"username": username, "displayName": display_name},
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


@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request):
    return render_page(request, "users")


@app.get("/devices", response_class=HTMLResponse)
async def devices_page(request: Request):
    return render_page(request, "devices")


@app.get("/areas", response_class=HTMLResponse)
async def areas_page(request: Request):
    return render_page(request, "areas")


@app.get("/points", response_class=HTMLResponse)
async def points_page(request: Request):
    return render_page(request, "points")


@app.get("/routes", response_class=HTMLResponse)
async def routes_mgmt_page(request: Request):
    return render_page(request, "routes")


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


@app.get("/api/robots/discovery")
async def api_robot_discovery(request: Request, refresh: int = 0) -> JSONResponse:
    require_api_login(request)
    return JSONResponse(discover_robot_candidates(force=bool(refresh)))


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


@app.put("/api/zones/{zone_id}")
async def api_update_zone(zone_id: int, request: Request) -> JSONResponse:
    require_api_login(request)
    zone_id = parse_strict_id(zone_id, "zone_id")
    existing = load_zone(zone_id)
    if not existing:
        raise HTTPException(status_code=404, detail="未找到对应区域。")
    payload = await request.json()
    record = build_zone_record(
        {
            "name": payload.get("name", existing["name"]),
            "type": payload.get("type", existing["type"]),
            "risk": payload.get("risk", existing["risk"]),
            "status": payload.get("status", existing["status"]),
            "frequency": payload.get("frequency", existing["frequency"]),
            "strokeColor": payload.get("strokeColor", existing["strokeColor"]),
            "fillColor": payload.get("fillColor", existing["fillColor"]),
            "path": payload.get("path", existing["path"]),
            "notes": payload.get("notes", existing["notes"]),
        }
    )
    affected = execute_write(
        """
        UPDATE zones
        SET name=%s, type=%s, risk=%s, status=%s, frequency=%s, stroke_color=%s, fill_color=%s, path_json=%s, notes=%s
        WHERE id=%s
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
            zone_id,
        ),
    )
    if affected == 0:
        raise HTTPException(status_code=404, detail="未找到对应区域。")
    await ws_broadcast("zone_updated")
    return JSONResponse({"ok": True})


@app.delete("/api/zones/{zone_id}")
async def api_delete_zone(zone_id: int, request: Request) -> JSONResponse:
    require_api_login(request)
    zone_id = parse_strict_id(zone_id, "zone_id")
    if clear_table("zones", zone_id) == 0:
        raise HTTPException(status_code=404, detail="未找到对应区域。")
    await ws_broadcast("zone_deleted")
    return JSONResponse({"ok": True})


UPLOAD_DIR = STATIC_DIR / "uploads" / "devices"


def ensure_upload_dir() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# 鈹€鈹€ 鐢ㄦ埛绠＄悊 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
def load_users(page: int = 1, size: int = 20) -> dict[str, Any]:
    offset = (page - 1) * size
    total_row = query_one("SELECT COUNT(*) AS cnt FROM users")
    total = int(total_row["cnt"]) if total_row else 0
    rows = query_all(
        "SELECT id, username, display_name, status, created_at FROM users ORDER BY created_at DESC LIMIT %s OFFSET %s",
        (size, offset),
    )
    return {
        "items": [
            {
                "id": r["id"],
                "username": r["username"],
                "displayName": r["display_name"],
                "status": r["status"],
                "createdAt": to_iso_datetime(r["created_at"]),
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "size": size,
    }


@app.get("/api/users")
async def api_users(request: Request, page: int = 1, size: int = 20) -> JSONResponse:
    require_api_login(request)
    size = min(max(size, 1), 100)
    page = max(page, 1)
    return JSONResponse(
        load_users(page, size) if mysql_ready() else {"items": [], "total": 0, "page": page, "size": size}
    )


@app.post("/api/users")
async def api_create_user(request: Request) -> JSONResponse:
    require_api_login(request)
    payload = await request.json()
    username, password, display_name = validate_auth_user_payload(payload)
    if get_user_by_username(username):
        raise HTTPException(status_code=409, detail="用户名已存在。")
    execute_write(
        "INSERT INTO users (username, password_hash, display_name, status, created_at) VALUES (%s, %s, %s, 'active', %s)",
        (username, hash_password(password), display_name, datetime.now()),
    )
    return JSONResponse({"ok": True})


@app.put("/api/users/{user_id}")
async def api_update_user(user_id: int, request: Request) -> JSONResponse:
    require_api_login(request)
    user_id = parse_strict_id(user_id, "user_id")
    payload = await request.json()
    display_name = str(payload.get("displayName", "")).strip()
    password = str(payload.get("password", "")).strip()
    if not display_name and not password:
        raise HTTPException(status_code=422, detail="至少提供 displayName 或 password 之一。")
    if display_name:
        execute_write("UPDATE users SET display_name = %s WHERE id = %s", (display_name, user_id))
    if password:
        execute_write("UPDATE users SET password_hash = %s WHERE id = %s", (hash_password(password), user_id))
    return JSONResponse({"ok": True})


@app.patch("/api/users/{user_id}/status")
async def api_update_user_status(user_id: int, request: Request) -> JSONResponse:
    require_api_login(request)
    user_id = parse_strict_id(user_id, "user_id")
    payload = await request.json()
    status = str(payload.get("status", "")).strip()
    if status not in {"active", "disabled"}:
        raise HTTPException(status_code=422, detail="status 必须是 active 或 disabled。")
    target = query_one("SELECT username FROM users WHERE id = %s", (user_id,))
    if not target:
        raise HTTPException(status_code=404, detail="未找到对应用户。")
    me = current_user(request)
    if me and me.get("username") == target["username"] and status == "disabled":
        raise HTTPException(status_code=409, detail="不能禁用当前登录用户。")
    execute_write("UPDATE users SET status = %s WHERE id = %s", (status, user_id))
    return JSONResponse({"ok": True})


# 鈹€鈹€ 璁惧绠＄悊 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
def load_devices(area_id: Optional[int] = None, status: Optional[str] = None) -> list[dict[str, Any]]:
    sql = """
        SELECT d.id, d.name, d.model, d.image_path, d.status, d.area_id,
               a.name AS area_name, d.notes, d.created_at
        FROM devices d
        LEFT JOIN areas a ON a.id = d.area_id
        WHERE 1=1
    """
    params: list[Any] = []
    if area_id is not None:
        sql += " AND d.area_id = %s"
        params.append(area_id)
    if status:
        sql += " AND d.status = %s"
        params.append(status)
    sql += " ORDER BY d.created_at DESC, d.id DESC"
    rows = query_all(sql, tuple(params) if params else None)
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "model": r["model"],
            "imagePath": r["image_path"] or "",
            "status": r["status"],
            "areaId": r["area_id"],
            "areaName": r["area_name"] or "未分配",
            "notes": r["notes"] or "",
            "createdAt": to_iso_datetime(r["created_at"]),
        }
        for r in rows
    ]


@app.get("/api/devices")
async def api_devices(
    request: Request, area_id: Optional[int] = None, status: Optional[str] = None
) -> JSONResponse:
    require_api_login(request)
    return JSONResponse({"items": load_devices(area_id, status) if mysql_ready() else []})


@app.post("/api/devices")
async def api_create_device(request: Request) -> JSONResponse:
    require_api_login(request)
    payload = await request.json()
    name = str(payload.get("name", "")).strip()
    model = str(payload.get("model", "")).strip()
    if not name or not model:
        raise HTTPException(status_code=422, detail="设备名称和型号不能为空。")
    area_id = payload.get("areaId")
    if area_id is not None:
        area_id = parse_strict_id(area_id, "areaId")
    device_id = execute_insert(
        "INSERT INTO devices (name, model, image_path, status, area_id, notes, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (
            name, model, str(payload.get("imagePath", "")),
            str(payload.get("status", "normal")).strip() or "normal",
            area_id, str(payload.get("notes", "")).strip(), datetime.now(),
        ),
    )
    return JSONResponse({"ok": True, "deviceId": device_id})


@app.put("/api/devices/{device_id}")
async def api_update_device(device_id: int, request: Request) -> JSONResponse:
    require_api_login(request)
    device_id = parse_strict_id(device_id, "device_id")
    payload = await request.json()
    name = str(payload.get("name", "")).strip()
    model = str(payload.get("model", "")).strip()
    if not name or not model:
        raise HTTPException(status_code=422, detail="设备名称和型号不能为空。")
    area_id = payload.get("areaId")
    if area_id is not None:
        area_id = parse_strict_id(area_id, "areaId")
    affected = execute_write(
        "UPDATE devices SET name=%s, model=%s, status=%s, area_id=%s, notes=%s WHERE id=%s",
        (
            name, model, str(payload.get("status", "normal")).strip() or "normal",
            area_id, str(payload.get("notes", "")).strip(), device_id,
        ),
    )
    if affected == 0:
        raise HTTPException(status_code=404, detail="未找到对应设备。")
    return JSONResponse({"ok": True})


@app.delete("/api/devices/{device_id}")
async def api_delete_device(device_id: int, request: Request) -> JSONResponse:
    require_api_login(request)
    device_id = parse_strict_id(device_id, "device_id")
    if clear_table("devices", device_id) == 0:
        raise HTTPException(status_code=404, detail="未找到对应设备。")
    return JSONResponse({"ok": True})


@app.post("/api/devices/{device_id}/image")
async def api_upload_device_image(
    device_id: int, request: Request, file: UploadFile = File(...)
) -> JSONResponse:
    require_api_login(request)
    device_id = parse_strict_id(device_id, "device_id")
    if not query_one("SELECT id FROM devices WHERE id = %s", (device_id,)):
        raise HTTPException(status_code=404, detail="未找到对应设备。")
    ensure_upload_dir()
    ext = Path(file.filename or "img.jpg").suffix.lower() or ".jpg"
    filename = f"device_{device_id}{ext}"
    dest = UPLOAD_DIR / filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    url = f"/static/uploads/devices/{filename}"
    execute_write("UPDATE devices SET image_path = %s WHERE id = %s", (url, device_id))
    return JSONResponse({"ok": True, "url": url})


# 鈹€鈹€ 宸℃鍖哄煙 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
def load_areas() -> list[dict[str, Any]]:
    rows = query_all(
        "SELECT id, name, description, manager, created_at FROM areas ORDER BY created_at DESC, id DESC"
    )
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "description": r["description"] or "",
            "manager": r["manager"] or "",
            "createdAt": to_iso_datetime(r["created_at"]),
        }
        for r in rows
    ]


@app.get("/api/areas")
async def api_areas(request: Request) -> JSONResponse:
    require_api_login(request)
    return JSONResponse({"items": load_areas() if mysql_ready() else []})


@app.post("/api/areas")
async def api_create_area(request: Request) -> JSONResponse:
    require_api_login(request)
    payload = await request.json()
    name = str(payload.get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=422, detail="区域名称不能为空。")
    execute_write(
        "INSERT INTO areas (name, description, manager, created_at) VALUES (%s, %s, %s, %s)",
        (name, str(payload.get("description", "")).strip(), str(payload.get("manager", "")).strip(), datetime.now()),
    )
    return JSONResponse({"ok": True})


@app.put("/api/areas/{area_id}")
async def api_update_area(area_id: int, request: Request) -> JSONResponse:
    require_api_login(request)
    area_id = parse_strict_id(area_id, "area_id")
    payload = await request.json()
    name = str(payload.get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=422, detail="区域名称不能为空。")
    affected = execute_write(
        "UPDATE areas SET name=%s, description=%s, manager=%s WHERE id=%s",
        (name, str(payload.get("description", "")).strip(), str(payload.get("manager", "")).strip(), area_id),
    )
    if affected == 0:
        raise HTTPException(status_code=404, detail="未找到对应区域。")
    return JSONResponse({"ok": True})


@app.delete("/api/areas/{area_id}")
async def api_delete_area(area_id: int, request: Request) -> JSONResponse:
    require_api_login(request)
    area_id = parse_strict_id(area_id, "area_id")
    if clear_table("areas", area_id) == 0:
        raise HTTPException(status_code=404, detail="未找到对应区域。")
    return JSONResponse({"ok": True})


# 巡检点
def load_points(area_id: Optional[int] = None) -> list[dict[str, Any]]:
    sql = """
        SELECT p.id, p.name, p.area_id, a.name AS area_name,
               p.device_id, d.name AS device_name, p.lat, p.lng, p.description, p.created_at
        FROM points p
        LEFT JOIN areas a ON a.id = p.area_id
        LEFT JOIN devices d ON d.id = p.device_id
        WHERE 1=1
    """
    params: list[Any] = []
    if area_id is not None:
        sql += " AND p.area_id = %s"
        params.append(area_id)
    sql += " ORDER BY p.created_at DESC, p.id DESC"
    rows = query_all(sql, tuple(params) if params else None)
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "areaId": r["area_id"],
            "areaName": r["area_name"] or "未分配",
            "deviceId": r["device_id"],
            "deviceName": r["device_name"] or "无关联设备",
            "lat": float(r["lat"]),
            "lng": float(r["lng"]),
            "description": r["description"] or "",
            "createdAt": to_iso_datetime(r["created_at"]),
        }
        for r in rows
    ]


@app.get("/api/points")
async def api_points(request: Request, area_id: Optional[int] = None) -> JSONResponse:
    require_api_login(request)
    return JSONResponse({"items": load_points(area_id) if mysql_ready() else []})


@app.post("/api/points")
async def api_create_point(request: Request) -> JSONResponse:
    require_api_login(request)
    payload = await request.json()
    name = str(payload.get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=422, detail="巡检点名称不能为空。")
    lat = parse_float(payload.get("lat", 0), "lat")
    lng = parse_float(payload.get("lng", 0), "lng")
    resolve_zone_by_coordinates(lng, lat)
    area_id = payload.get("areaId")
    device_id = payload.get("deviceId")
    if area_id is not None:
        area_id = parse_strict_id(area_id, "areaId")
    if device_id is not None:
        device_id = parse_strict_id(device_id, "deviceId")
    execute_write(
        "INSERT INTO points (name, area_id, device_id, lat, lng, description, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (name, area_id, device_id, lat, lng, str(payload.get("description", "")).strip(), datetime.now()),
    )
    return JSONResponse({"ok": True})


@app.put("/api/points/{point_id}")
async def api_update_point(point_id: int, request: Request) -> JSONResponse:
    require_api_login(request)
    point_id = parse_strict_id(point_id, "point_id")
    payload = await request.json()
    name = str(payload.get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=422, detail="巡检点名称不能为空。")
    lat = parse_float(payload.get("lat", 0), "lat")
    lng = parse_float(payload.get("lng", 0), "lng")
    resolve_zone_by_coordinates(lng, lat)
    area_id = payload.get("areaId")
    device_id = payload.get("deviceId")
    if area_id is not None:
        area_id = parse_strict_id(area_id, "areaId")
    if device_id is not None:
        device_id = parse_strict_id(device_id, "deviceId")
    affected = execute_write(
        "UPDATE points SET name=%s, area_id=%s, device_id=%s, lat=%s, lng=%s, description=%s WHERE id=%s",
        (name, area_id, device_id, lat, lng, str(payload.get("description", "")).strip(), point_id),
    )
    if affected == 0:
        raise HTTPException(status_code=404, detail="未找到对应巡检点。")
    return JSONResponse({"ok": True})


@app.delete("/api/points/{point_id}")
async def api_delete_point(point_id: int, request: Request) -> JSONResponse:
    require_api_login(request)
    point_id = parse_strict_id(point_id, "point_id")
    if clear_table("points", point_id) == 0:
        raise HTTPException(status_code=404, detail="未找到对应巡检点。")
    return JSONResponse({"ok": True})


# 鈹€鈹€ 宸℃璺嚎 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
def load_routes() -> list[dict[str, Any]]:
    rows = query_all("""
        SELECT r.id, r.name, r.description, r.area_id, a.name AS area_name,
               COUNT(rp.id) AS point_count, r.created_at
        FROM routes r
        LEFT JOIN areas a ON a.id = r.area_id
        LEFT JOIN route_points rp ON rp.route_id = r.id
        GROUP BY r.id, r.name, r.description, r.area_id, a.name, r.created_at
        ORDER BY r.created_at DESC, r.id DESC
    """)
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "description": r["description"] or "",
            "areaId": r["area_id"],
            "areaName": r["area_name"] or "未分配",
            "pointCount": int(r["point_count"]),
            "createdAt": to_iso_datetime(r["created_at"]),
        }
        for r in rows
    ]


def load_route_points(route_id: int) -> list[dict[str, Any]]:
    rows = query_all("""
        SELECT p.id, p.name, p.lat, p.lng, p.description, rp.sort_order
        FROM route_points rp
        JOIN points p ON p.id = rp.point_id
        WHERE rp.route_id = %s
        ORDER BY rp.sort_order ASC, rp.id ASC
    """, (route_id,))
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "lat": float(r["lat"]),
            "lng": float(r["lng"]),
            "description": r["description"] or "",
            "sortOrder": int(r["sort_order"]),
        }
        for r in rows
    ]


@app.get("/api/routes")
async def api_routes(request: Request) -> JSONResponse:
    require_api_login(request)
    return JSONResponse({"items": load_routes() if mysql_ready() else []})


@app.post("/api/routes")
async def api_create_route(request: Request) -> JSONResponse:
    require_api_login(request)
    payload = await request.json()
    name = str(payload.get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=422, detail="路线名称不能为空。")
    area_id = payload.get("areaId")
    if area_id is not None:
        area_id = parse_strict_id(area_id, "areaId")
    execute_write(
        "INSERT INTO routes (name, description, area_id, created_at) VALUES (%s, %s, %s, %s)",
        (name, str(payload.get("description", "")).strip(), area_id, datetime.now()),
    )
    return JSONResponse({"ok": True})


@app.put("/api/routes/{route_id}")
async def api_update_route(route_id: int, request: Request) -> JSONResponse:
    require_api_login(request)
    route_id = parse_strict_id(route_id, "route_id")
    payload = await request.json()
    name = str(payload.get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=422, detail="路线名称不能为空。")
    area_id = payload.get("areaId")
    if area_id is not None:
        area_id = parse_strict_id(area_id, "areaId")
    affected = execute_write(
        "UPDATE routes SET name=%s, description=%s, area_id=%s WHERE id=%s",
        (name, str(payload.get("description", "")).strip(), area_id, route_id),
    )
    if affected == 0:
        raise HTTPException(status_code=404, detail="未找到对应路线。")
    return JSONResponse({"ok": True})


@app.delete("/api/routes/{route_id}")
async def api_delete_route(route_id: int, request: Request) -> JSONResponse:
    require_api_login(request)
    route_id = parse_strict_id(route_id, "route_id")
    if clear_table("routes", route_id) == 0:
        raise HTTPException(status_code=404, detail="未找到对应路线。")
    return JSONResponse({"ok": True})


@app.get("/api/routes/{route_id}/points")
async def api_route_points_get(route_id: int, request: Request) -> JSONResponse:
    require_api_login(request)
    route_id = parse_strict_id(route_id, "route_id")
    if not query_one("SELECT id FROM routes WHERE id = %s", (route_id,)):
        raise HTTPException(status_code=404, detail="未找到对应路线。")
    return JSONResponse({"routeId": route_id, "items": load_route_points(route_id) if mysql_ready() else []})


@app.put("/api/routes/{route_id}/points")
async def api_route_points_set(route_id: int, request: Request) -> JSONResponse:
    require_api_login(request)
    route_id = parse_strict_id(route_id, "route_id")
    if not query_one("SELECT id FROM routes WHERE id = %s", (route_id,)):
        raise HTTPException(status_code=404, detail="未找到对应路线。")
    payload = await request.json()
    point_ids = payload.get("pointIds", [])
    if not isinstance(point_ids, list):
        raise HTTPException(status_code=422, detail="pointIds 必须是数组。")
    connection = get_db()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM route_points WHERE route_id = %s", (route_id,))
            for order, pid in enumerate(point_ids):
                pid = parse_strict_id(pid, f"pointIds[{order}]")
                cursor.execute(
                    "INSERT INTO route_points (route_id, point_id, sort_order) VALUES (%s, %s, %s)",
                    (route_id, pid, order),
                )
        connection.commit()
    finally:
        connection.close()
    return JSONResponse({"ok": True, "count": len(point_ids)})


# 设备通信（物联网对接）
#
# 鉴权方案：
# 1. 设备上报接口使用 X-Device-Token 请求头，不依赖 Session。
# 2. 管理接口（创建、吊销 Token、查询记录）仍然要求后台登录。
#
# 接口一览：
#   POST   /api/iot/tokens               管理员为设备创建 Token
#   DELETE /api/iot/tokens/{id}          管理员吊销 Token
#   GET    /api/iot/tokens               管理员查看 Token 列表
#   POST   /api/iot/checkin              设备上报巡检打卡（X-Device-Token 鉴权）
#   POST   /api/iot/telemetry            设备上报遥测状态（X-Device-Token 鉴权）
#   GET    /api/iot/checkins             管理员查询打卡记录
#   GET    /api/iot/telemetry            管理员查询遥测记录
#   GET    /api/iot/devices/{id}/status  查询指定设备的最新遥测状态

def _generate_device_token(device_id: int) -> str:
    """为指定设备生成新的鉴权 Token。"""
    import secrets
    raw = f"{device_id}-{secrets.token_hex(16)}-{datetime.now().isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _resolve_device_token(token_value: str) -> dict[str, Any] | None:
    """根据 Token 查询有效的设备绑定记录。"""
    return query_one(
        "SELECT id, device_id FROM device_tokens WHERE token = %s AND is_active = 1 LIMIT 1",
        (token_value,),
    )


def require_device_token(request: Request) -> int:
    """校验设备 Token，并返回对应的 device_id。"""
    token_value = request.headers.get("X-Device-Token", "").strip()
    if not token_value:
        raise HTTPException(status_code=401, detail="缺少 X-Device-Token 请求头。")
    row = _resolve_device_token(token_value)
    if not row:
        raise HTTPException(status_code=403, detail="Token 无效或已被吊销。")
    return int(row["device_id"])


# Token 管理接口（仅管理员）

@app.get("/api/iot/tokens")
async def api_iot_list_tokens(request: Request) -> JSONResponse:
    """获取设备 Token 列表。"""
    require_admin_login(request)
    rows = query_all(
        """
        SELECT dt.id, dt.device_id, d.name AS device_name, dt.token,
               dt.note, dt.is_active, dt.created_at
        FROM device_tokens dt
        JOIN devices d ON d.id = dt.device_id
        ORDER BY dt.created_at DESC
        """
    ) if mysql_ready() else []
    return JSONResponse({
        "items": [
            {
                "id": r["id"],
                "deviceId": r["device_id"],
                "deviceName": r["device_name"],
                "token": r["token"],
                "note": r["note"] or "",
                "isActive": bool(r["is_active"]),
                "createdAt": to_iso_datetime(r["created_at"]),
            }
            for r in rows
        ]
    })


@app.post("/api/iot/tokens")
async def api_iot_create_token(request: Request) -> JSONResponse:
    """为指定设备创建新的 Token。"""
    require_admin_login(request)
    payload = await request.json()
    device_id = parse_strict_id(payload.get("deviceId"), "deviceId")
    if not query_one("SELECT id FROM devices WHERE id = %s", (device_id,)):
        raise HTTPException(status_code=404, detail="未找到对应设备。")
    note = str(payload.get("note", "")).strip()
    token_value = _generate_device_token(device_id)
    token_id = execute_insert(
        "INSERT INTO device_tokens (device_id, token, note, is_active, created_at) VALUES (%s,%s,%s,1,%s)",
        (device_id, token_value, note, datetime.now()),
    )
    return JSONResponse({"ok": True, "tokenId": token_id, "token": token_value})


@app.delete("/api/iot/tokens/{token_id}")
async def api_iot_revoke_token(token_id: int, request: Request) -> JSONResponse:
    """吊销指定 Token。"""
    require_admin_login(request)
    token_id = parse_strict_id(token_id, "token_id")
    affected = execute_write(
        "UPDATE device_tokens SET is_active = 0 WHERE id = %s", (token_id,)
    )
    if affected == 0:
        raise HTTPException(status_code=404, detail="未找到对应 Token。")
    return JSONResponse({"ok": True})


# 设备打卡上报接口

@app.post("/api/iot/checkin")
async def api_iot_checkin(request: Request) -> JSONResponse:
    """
    设备到达巡检点后主动上报打卡记录。
    请求头：
        X-Device-Token: <token>

    请求体（JSON）：
        {
          "pointId": 1,
          "routeId": 2,
          "lat": 31.09161,
          "lng": 121.81742,
          "note": "抵达 A2 点位",
          "checkedAt": "2026-03-30T10:00:00"
        }
    """
    device_id = require_device_token(request)
    payload = await request.json()

    point_id = payload.get("pointId")
    route_id = payload.get("routeId")
    lat_raw = payload.get("lat")
    lng_raw = payload.get("lng")
    note = str(payload.get("note", "")).strip()
    checked_at_raw = payload.get("checkedAt")

    if point_id is not None:
        point_id = parse_strict_id(point_id, "pointId")
        if not query_one("SELECT id FROM points WHERE id = %s", (point_id,)):
            raise HTTPException(status_code=404, detail="未找到对应巡检点。")
    if route_id is not None:
        route_id = parse_strict_id(route_id, "routeId")
        if not query_one("SELECT id FROM routes WHERE id = %s", (route_id,)):
            raise HTTPException(status_code=404, detail="未找到对应巡检路线。")

    lat = parse_float(lat_raw, "lat") if lat_raw is not None else None
    lng = parse_float(lng_raw, "lng") if lng_raw is not None else None
    checked_at = parse_datetime(checked_at_raw, "checkedAt") if checked_at_raw else datetime.now()

    checkin_id = execute_insert(
        """
        INSERT INTO device_checkins
            (device_id, point_id, route_id, lat, lng, note, checked_at, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (device_id, point_id, route_id, lat, lng, note, checked_at, datetime.now()),
    )
    await ws_broadcast("device_checkin")
    return JSONResponse({"ok": True, "checkinId": checkin_id})


# 设备遥测上报接口

@app.post("/api/iot/telemetry")
async def api_iot_telemetry(request: Request) -> JSONResponse:
    """
    设备遥测状态上报接口，设备定期调用并写入历史记录。
    请求头：
        X-Device-Token: <token>

    请求体（JSON）：
        {
          "battery": 85,
          "signal": 72,
          "status": "online",
          "lat": 31.09161,
          "lng": 121.81742,
          "reportedAt": "2026-03-30T10:00:00",
          "extra": {"temp": 25.3}
        }
    """
    device_id = require_device_token(request)
    payload = await request.json()

    battery_raw = payload.get("battery")
    signal_raw = payload.get("signal")
    status_raw = str(payload.get("status", "")).strip() or None
    lat_raw = payload.get("lat")
    lng_raw = payload.get("lng")
    extra = payload.get("extra")
    reported_at_raw = payload.get("reportedAt")

    battery = parse_int_range(battery_raw, "battery", 0, 100) if battery_raw is not None else None
    signal = parse_int_range(signal_raw, "signal", 0, 100) if signal_raw is not None else None
    if status_raw and status_raw not in {"online", "offline", "fault"}:
        raise HTTPException(status_code=422, detail="status 必须是 online、offline 或 fault。")
    lat = parse_float(lat_raw, "lat") if lat_raw is not None else None
    lng = parse_float(lng_raw, "lng") if lng_raw is not None else None
    reported_at = parse_datetime(reported_at_raw, "reportedAt") if reported_at_raw else datetime.now()
    extra_json = json.dumps(extra, ensure_ascii=False) if extra is not None else None
    source_ip = ""
    if request.client and request.client.host:
        try:
            source_ip = parse_ipv4(request.client.host, "source_ip")
        except HTTPException:
            source_ip = str(request.client.host).strip()

    # 写入遥测历史
    execute_insert(
        """
        INSERT INTO device_telemetry
            (device_id, battery, `signal`, status, lat, lng, source_ip, extra_json, reported_at, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (device_id, battery, signal, status_raw, lat, lng, source_ip or None, extra_json, reported_at, datetime.now()),
    )

    # 同步更新设备当前状态，仅在状态字段有值时覆盖
    if status_raw:
        execute_write(
            "UPDATE devices SET status = %s WHERE id = %s",
            (_map_iot_status_to_device(status_raw), device_id),
        )

    await ws_broadcast("device_telemetry")
    return JSONResponse({"ok": True})


def _map_iot_status_to_device(iot_status: str) -> str:
    """将 IoT 状态映射到 devices.status。"""
    return {"online": "normal", "offline": "offline", "fault": "fault"}.get(iot_status, "normal")


# 管理端查询接口（Session 鉴权）

@app.get("/api/iot/checkins")
async def api_iot_list_checkins(
    request: Request,
    device_id: Optional[int] = None,
    route_id: Optional[int] = None,
    limit: int = 50,
) -> JSONResponse:
    """查询设备打卡记录。"""
    require_api_login(request)
    limit = min(max(limit, 1), 200)
    sql = """
        SELECT ci.id, ci.device_id, d.name AS device_name,
               ci.point_id, p.name AS point_name,
               ci.route_id, r.name AS route_name,
               ci.lat, ci.lng, ci.note, ci.checked_at, ci.created_at
        FROM device_checkins ci
        JOIN devices d ON d.id = ci.device_id
        LEFT JOIN points p ON p.id = ci.point_id
        LEFT JOIN routes r ON r.id = ci.route_id
        WHERE 1=1
    """
    params: list[Any] = []
    if device_id is not None:
        sql += " AND ci.device_id = %s"
        params.append(device_id)
    if route_id is not None:
        sql += " AND ci.route_id = %s"
        params.append(route_id)
    sql += " ORDER BY ci.checked_at DESC, ci.id DESC LIMIT %s"
    params.append(limit)

    rows = query_all(sql, tuple(params)) if mysql_ready() else []
    return JSONResponse({
        "items": [
            {
                "id": r["id"],
                "deviceId": r["device_id"],
                "deviceName": r["device_name"],
                "pointId": r["point_id"],
                "pointName": r["point_name"] or "",
                "routeId": r["route_id"],
                "routeName": r["route_name"] or "",
                "lat": float(r["lat"]) if r["lat"] is not None else None,
                "lng": float(r["lng"]) if r["lng"] is not None else None,
                "note": r["note"] or "",
                "checkedAt": to_iso_datetime(r["checked_at"]),
                "createdAt": to_iso_datetime(r["created_at"]),
            }
            for r in rows
        ]
    })


@app.get("/api/iot/telemetry")
async def api_iot_list_telemetry(
    request: Request,
    device_id: Optional[int] = None,
    limit: int = 100,
) -> JSONResponse:
    """查询设备遥测记录。"""
    require_api_login(request)
    limit = min(max(limit, 1), 500)
    sql = """
        SELECT t.id, t.device_id, d.name AS device_name,
               t.battery, t.`signal` AS signal_value, t.status, t.lat, t.lng,
               t.extra_json, t.reported_at, t.created_at
        FROM device_telemetry t
        JOIN devices d ON d.id = t.device_id
        WHERE 1=1
    """
    params: list[Any] = []
    if device_id is not None:
        sql += " AND t.device_id = %s"
        params.append(device_id)
    sql += " ORDER BY t.reported_at DESC, t.id DESC LIMIT %s"
    params.append(limit)

    rows = query_all(sql, tuple(params)) if mysql_ready() else []
    return JSONResponse({
        "items": [
            {
                "id": r["id"],
                "deviceId": r["device_id"],
                "deviceName": r["device_name"],
                "battery": r["battery"],
                "signal": r["signal_value"],
                "status": r["status"] or "",
                "lat": float(r["lat"]) if r["lat"] is not None else None,
                "lng": float(r["lng"]) if r["lng"] is not None else None,
                "extra": json.loads(r["extra_json"]) if r["extra_json"] else None,
                "reportedAt": to_iso_datetime(r["reported_at"]),
                "createdAt": to_iso_datetime(r["created_at"]),
            }
            for r in rows
        ]
    })


@app.get("/api/iot/devices/{device_id}/status")
async def api_iot_device_latest_status(device_id: int, request: Request) -> JSONResponse:
    """获取指定设备的最新遥测状态。"""
    require_api_login(request)
    device_id = parse_strict_id(device_id, "device_id")
    device = query_one("SELECT id, name, status FROM devices WHERE id = %s", (device_id,))
    if not device:
        raise HTTPException(status_code=404, detail="未找到对应设备。")
    latest = query_one(
        """
        SELECT battery, `signal` AS signal_value, status, lat, lng, extra_json, reported_at
        FROM device_telemetry
        WHERE device_id = %s
        ORDER BY reported_at DESC, id DESC
        LIMIT 1
        """,
        (device_id,),
    ) if mysql_ready() else None
    return JSONResponse({
        "deviceId": device_id,
        "deviceName": device["name"],
        "deviceStatus": device["status"],
        "telemetry": {
            "battery": latest["battery"] if latest else None,
            "signal": latest["signal_value"] if latest else None,
            "status": latest["status"] if latest else None,
            "lat": float(latest["lat"]) if latest and latest["lat"] is not None else None,
            "lng": float(latest["lng"]) if latest and latest["lng"] is not None else None,
            "extra": json.loads(latest["extra_json"]) if latest and latest["extra_json"] else None,
            "reportedAt": to_iso_datetime(latest["reported_at"]) if latest else None,
        } if latest else None,
    })


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


