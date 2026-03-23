# 机器人巡检平台

基于 `FastAPI + Jinja2 + MySQL + 高德地图` 的机器人巡检 Web 平台，提供登录鉴权、任务管理、机器人状态、告警、报告、区域控制和实时仪表盘能力。

## 功能概览

- 中文化 Web 管理界面
- Session 登录鉴权
- MySQL 自动建库、建表、初始化管理员
- 总览、任务、报告、机器人、维护、区域 6 个业务页面
- REST API
- `WebSocket` 实时仪表盘更新
- 高德地图接入
- 网页 GPS 定位
- 区域地图点击绘制
- 调色板选区颜色
- 基础测试与健康检查

## 技术栈

- Python
- FastAPI
- Jinja2
- PyMySQL
- Uvicorn
- MySQL 8
- AMap Web JS API

## 目录结构

```text
fastapi/
├─ db/
│  └─ mysql_schema.sql
├─ static/
│  ├─ dashboard.css
│  ├─ dashboard.js
│  └─ login.js
├─ templates/
│  ├─ app.html
│  └─ login.html
├─ tests/
│  └─ test_auth_ui.py
├─ tutorial_basic_routes/
│  └─ tests/
├─ .env
├─ main.py
├─ requirements.txt
└─ README.md
```

## 环境要求

- Python 3.10+
- MySQL 8.0+
- Windows PowerShell

## 安装依赖

```powershell
cd E:\Code\Project4\fastapi
E:\WorkApps\MiniConda\envs\ipv6mon\python.exe -m pip install -r requirements.txt
```

## 环境变量

项目使用根目录下的 `.env`。

示例：

```env
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root1
MYSQL_PASSWORD=123456
MYSQL_DATABASE=robot_monitor
MYSQL_CHARSET=utf8mb4

SESSION_SECRET=replace-this-in-production

ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
ADMIN_DISPLAY_NAME=系统管理员

AMAP_WEB_KEY=你的高德WebJSKey
```

说明：

- 首次启动会自动创建数据库和数据表
- 若管理员账号不存在，会自动初始化
- 生产环境必须修改 `SESSION_SECRET`、MySQL 密码和管理员密码
- 高德地图必须使用 `Web端(JS API)` 的 Key

## 启动项目

```powershell
cd E:\Code\Project4\fastapi
E:\WorkApps\MiniConda\envs\ipv6mon\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8022
```

启动后访问：

- 登录页: [http://127.0.0.1:8022/login](http://127.0.0.1:8022/login)
- 健康检查: [http://127.0.0.1:8022/api/health](http://127.0.0.1:8022/api/health)

## 默认账号

- 用户名：`admin`
- 密码：`admin123`

如果你已经在 `.env` 中修改过管理员配置，以 `.env` 为准。

## 页面路由

- `/overview` 总览
- `/tasks` 任务管理
- `/reports` 历史报告
- `/robots` 机器人状态
- `/maintenance` 设备维护
- `/zones` 区域控制
- `/login` 登录页

兼容旧路由：

- `/` -> `/overview`
- `/_3` -> `/tasks`
- `/_1` -> `/reports`
- `/monitoring_dashboard` -> `/robots`
- `/zone_control` -> `/zones`

## API 概览

### 认证

- `POST /auth/login`
- `POST /auth/logout`

### 页面数据

- `GET /api/dashboard`
- `GET /api/health`
- `WS /ws/dashboard`

### 任务

- `GET /api/tasks`
- `POST /api/tasks`
- `DELETE /api/tasks/{task_id}`

### 机器人

- `GET /api/robots`
- `POST /api/robots`
- `DELETE /api/robots/{robot_id}`

### 告警

- `GET /api/alerts`
- `POST /api/alerts`
- `DELETE /api/alerts/{alert_id}`

### 报告

- `GET /api/reports`
- `POST /api/reports`
- `DELETE /api/reports/{report_id}`

### 区域

- `GET /api/zones`
- `POST /api/zones`

## 登录与鉴权

- 页面和 API 默认都要求登录
- 未登录访问业务页面会重定向到 `/login`
- 未登录访问业务 API 会返回 `401`
- WebSocket `/ws/dashboard` 也要求登录态

## 区域绘制说明

区域控制页的新增区域不再手动输入经纬度，而是通过地图交互完成。

- 单击地图：添加一个顶点
- 双击地图：完成区域绘制
- 右键地图：撤销最后一个点
- `清空绘制`：重置当前草图
- 颜色选择：使用调色板，系统自动生成透明填充色

提交规则：

- 少于 3 个点不能提交
- 未双击完成绘制不能提交

## ID 边界规则

所有删除接口和关键外键都采用统一 ID 校验规则：

- 最小值：`1`
- 最大值：`2147483647`

错误语义：

- 非法 ID：返回 `422`
- ID 合法但记录不存在：返回 `404`

## 健康检查

`GET /api/health` 返回：

- `status`
- `mysqlConfigured`
- `mysqlReady`
- `detail`
- `timestamp`

当数据库不可用时，接口会返回 `503`。

## 实时更新

`WS /ws/dashboard` 支持：

- 首次连接推送仪表盘快照
- `ping` / `heartbeat`
- `refresh`
- 任务、机器人、告警、报告、区域新增或删除后的广播更新

## 测试

运行测试：

```powershell
cd E:\Code\Project4\fastapi
E:\WorkApps\MiniConda\envs\ipv6mon\python.exe -m pytest -q
```

当前已验证：

- 登录页可访问
- 登录与登出
- 页面登录保护
- 仪表盘 API
- 健康检查接口
- WebSocket 连通
- ID 边界与 422/404 语义

## 常见问题

### 1. 地图不显示

检查以下几项：

- `.env` 中是否配置了正确的 `AMAP_WEB_KEY`
- Key 是否为高德 `Web端(JS API)` 类型
- 浏览器是否拦截了定位权限
- 是否强刷了页面缓存

### 2. 登录失败

检查：

- MySQL 是否启动
- `.env` 中的 MySQL 配置是否正确
- 管理员账号是否被 `.env` 覆盖

### 3. 服务启动后报数据库错误

优先确认：

- `MYSQL_HOST`
- `MYSQL_PORT`
- `MYSQL_USER`
- `MYSQL_PASSWORD`
- `MYSQL_DATABASE`

## 开发说明

- 主入口文件：[main.py](/E:/Code/Project4/fastapi/main.py)
- 前端脚本：[dashboard.js](/E:/Code/Project4/fastapi/static/dashboard.js)
- 页面模板：[app.html](/E:/Code/Project4/fastapi/templates/app.html)
- 数据库 Schema：[mysql_schema.sql](/E:/Code/Project4/fastapi/db/mysql_schema.sql)

## 许可证

当前仓库根目录包含 [LICENSE](/E:/Code/Project4/fastapi/../ipv6intellmonitrsystem/LICENSE)。如需独立发布，建议在本项目目录补充单独许可证说明。
