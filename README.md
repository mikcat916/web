# Project4 — 机器人巡检监控系统

面向机器人巡检场景的管理平台，包含 Web 应用和桌面端两个子项目。

## 项目结构

```
Project4/
├── backend/     # Web 应用（FastAPI + Jinja2 + MySQL）
├── desktop/     # 桌面端（Python + PyQt5，UAV 控制 UI）
├── todolist.md  # 开发计划
└── README.md
```

## 各模块说明

### backend（Web 应用）
- 技术栈：Python、FastAPI、MySQL、Jinja2 模板、原生 JS
- 前后端一体：FastAPI 直接渲染 HTML 页面，WebSocket 实时推送数据
- 启动：`cd backend && pip install -r requirements.txt && python main.py`

### desktop（桌面端）
- 技术栈：Python、PyQt5、qfluentwidgets
- UAV 控制客户端，支持任务执行、状态监控
- 启动：`cd desktop && pip install -r requirements.txt && python main.py`

## 开发计划

详见 [todolist.md](./todolist.md)
