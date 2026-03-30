# Project4

机器人巡检监控系统，面向“后台管理 + 桌面控制 + IoT 设备上报”的一体化场景。

项目当前包含三个主要部分：

- `backend/`：基于 FastAPI 的 Web 管理后台，负责业务页面、CRUD 接口、登录鉴权、实时看板和 IoT 接口。
- `desktop/`：基于 PyQt 的桌面端，提供登录、主控界面、任务管理、状态监控和资产管理等能力。
- `scripts/`：数据库初始化、MySQL 诊断、树莓派 IoT 客户端和远程部署脚本。

## 功能概览

- 用户、设备、巡检区域、巡检点、巡检路线管理
- FastAPI + Jinja2 一体化 Web 页面
- Session 登录鉴权和基础健康检查
- WebSocket 实时看板数据推送
- 设备 IoT 打卡与遥测上报接口
- PyQt 桌面端任务执行和状态监控界面
- MySQL 建库、建表、诊断和部署辅助脚本

## 项目结构

```text
Project4/
├── backend/                 # Web 后端与页面模板
├── desktop/                 # PyQt 桌面端
├── logs/                    # 诊断脚本输出日志
├── scripts/                 # 建库、诊断、IoT 与部署脚本
├── .conda/                  # 本地 Python 环境（如果已创建）
├── create_database.bat      # 一键建库建表
├── start.bat                # 一键启动后端
├── start.ps1                # 后端启动脚本
├── test_mysql_connection.bat# 一键诊断 MySQL 连接
├── todolist.md              # 开发阶段与待办
└── README.md
```

## 技术栈

### Web 端

- Python
- FastAPI
- Jinja2
- PyMySQL
- Uvicorn
- MySQL 8
- 原生 JavaScript

### 桌面端

- Python
- PyQt5 / PyQtWebEngine
- PyQt-Fluent-Widgets
- PyMySQL / mysql-connector-python

## 当前进度

根据 [todolist.md](./todolist.md) 当前状态如下：

- 阶段一到阶段四已基本完成，包括数据库建模、后端 CRUD、Web 页面和 IoT 通信能力。
- 阶段五仍在进行中，主要是前后端联调、设备模拟和端到端流程测试。

如果你是第一次接手这个仓库，可以优先从 Web 后端启动和数据库连通性检查开始。

## 环境要求

- Windows + PowerShell（当前脚本优先按 Windows 开发环境组织）
- Python 3.10+ 推荐用于后端
- Python 3.9+ 可用于桌面端
- MySQL 8.0+

建议为 `backend` 和 `desktop` 分别准备独立 Python 环境，避免桌面依赖与后端依赖互相影响。

## 配置说明

根目录 `.env` 是共享数据库配置入口，`backend` 和 `desktop` 都会读取这里的配置。

示例：

```env
# Web 后端数据库
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=your_mysql_user
MYSQL_PASSWORD=your_mysql_password
MYSQL_DATABASE=robot_monitor
MYSQL_CHARSET=utf8mb4

# 桌面端数据库别名
UAV_DB_HOST=127.0.0.1
UAV_DB_PORT=3306
UAV_DB_USER=your_mysql_user
UAV_DB_PASSWORD=your_mysql_password
UAV_DB_NAME=robot_monitor

# 后端可选配置
SESSION_SECRET=replace-this-in-production
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
ADMIN_DISPLAY_NAME=系统管理员
AMAP_WEB_KEY=your_amap_web_js_key
```

说明：

- 后端启动时会优先读取根目录 `.env`，同时兼容 `backend/.env`。
- 桌面端数据库配置读取 `UAV_DB_*` 变量；未提供时会回退到默认值。
- `AMAP_WEB_KEY` 仅在需要地图功能时配置。
- 生产环境请务必修改 `SESSION_SECRET`、管理员账号密码和数据库密码。

## 快速开始

### 1. 安装依赖

后端：

```powershell
cd E:\Code\Project4\backend
python -m pip install -r requirements.txt
```

桌面端：

```powershell
cd E:\Code\Project4\desktop
python -m pip install -r requirements.txt
```

### 2. 初始化数据库

推荐直接使用根目录脚本：

```powershell
cd E:\Code\Project4
.\create_database.bat
```

等价命令：

```powershell
cd E:\Code\Project4
python scripts\create_database.py --with-device-pin
```

这个步骤会：

- 创建目标数据库
- 执行 `backend/db/mysql_schema.sql`
- 可选创建桌面端使用的 `device_pin` 表

### 3. 启动 Web 后端

最省事的方式：

```powershell
cd E:\Code\Project4
.\start.bat
```

或手动启动：

```powershell
cd E:\Code\Project4\backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

启动后可访问：

- 登录页：<http://127.0.0.1:8000/login>
- 健康检查：<http://127.0.0.1:8000/api/health>

如果没有在环境变量中覆盖管理员账号，默认登录信息通常为：

- 用户名：`admin`
- 密码：`admin123`

### 4. 启动桌面端

```powershell
cd E:\Code\Project4\desktop
python main.py
```

桌面端会读取根目录 `.env` 中的 `UAV_DB_*` 配置连接数据库。

## IoT 相关脚本

仓库已经包含设备侧接入的基础脚本，适合做本地联调或树莓派部署。

### 初始化 IoT 后端表并生成设备 Token

```powershell
cd E:\Code\Project4
python scripts\bootstrap_iot_backend.py --device-id 2
```

该脚本会补充创建：

- `device_tokens`
- `device_checkins`
- `device_telemetry`

如果目标设备存在，还会为该设备生成或复用一个可用 Token。

### 本地运行 IoT 客户端

```powershell
cd E:\Code\Project4\scripts
python iot_client.py --server http://127.0.0.1:8000 --token <DEVICE_TOKEN>
```

### 部署到树莓派

Linux 侧脚本：

```bash
bash scripts/setup_pi_iot.sh <SERVER_URL> <DEVICE_TOKEN> [INTERVAL] [POINT_ID] [ROUTE_ID]
```

Windows 远程部署脚本：

```powershell
python scripts\deploy_iot_client.py --host <PI_HOST> --password <PI_PASSWORD> --server <SERVER_URL> --token <DEVICE_TOKEN>
```

## 常用脚本

| 脚本 | 作用 |
| --- | --- |
| `start.bat` / `start.ps1` | 启动 Web 后端 |
| `create_database.bat` | 初始化数据库和表结构 |
| `test_mysql_connection.bat` | 诊断本地 MySQL 连通性 |
| `scripts/create_database.py` | 命令行建库建表 |
| `scripts/test_mysql_connection.py` | 输出详细诊断日志到 `logs/` |
| `scripts/bootstrap_iot_backend.py` | 初始化 IoT 表并生成设备 Token |
| `scripts/iot_client.py` | 设备侧打卡与遥测上报客户端 |
| `scripts/deploy_iot_client.py` | 将 IoT 客户端远程部署到树莓派 |

## 测试与排查

后端基础测试：

```powershell
cd E:\Code\Project4\backend
python -m pytest -q tests\test_auth_ui.py
```

数据库连通性诊断：

```powershell
cd E:\Code\Project4
.\test_mysql_connection.bat
```

诊断日志会输出到根目录 `logs/`。

## 子模块文档

- Web 端说明见 [backend/README.md](./backend/README.md)
- 桌面端说明见 [desktop/README.md](./desktop/README.md)

## 开发备注

- 根目录 `README.md` 负责项目总览与启动入口。
- `backend/README.md` 更适合写 API、页面路由和后端细节。
- `desktop/README.md` 更适合写桌面端 UI、环境和模块说明。
- 当前仓库仍处于联调阶段，文档会随着阶段五测试推进继续补充。
