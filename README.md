# Project4 — 机器人巡检监控系统

一个面向机器人巡检场景的全栈管理平台，包含 Web 后端、Web 前端和桌面端三个子项目。

## 项目结构

```
Project4/
├── backend/     # Web 后端（Python + FastAPI + MySQL）
├── frontend/    # Web 前端（React + TypeScript + Vite）
├── desktop/     # 桌面端（Python + PyQt5，UAV 控制 UI）
├── todolist.md  # 开发计划
└── README.md
```

## 各模块说明

### backend（Web 后端）
- 技术栈：Python、FastAPI、MySQL
- 提供 RESTful API，处理用户、设备、区域、巡检路线等业务逻辑
- 启动：`cd backend && pip install -r requirements.txt && python main.py`

### frontend（Web 前端）
- 技术栈：React、TypeScript、Vite
- 管理后台界面，对接 backend API
- 启动：`cd frontend && npm install && npm run dev`

### desktop（桌面端）
- 技术栈：Python、PyQt5、qfluentwidgets
- UAV 控制客户端，支持任务执行、状态监控
- 启动：`cd desktop && pip install -r requirements.txt && python main.py`

## 开发计划

详见 [todolist.md](./todolist.md)
