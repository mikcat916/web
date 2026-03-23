-- ============================================================
-- robot_monitor 数据库完整 Schema
-- 业务关系：区域(areas) 包含 设备(devices) 和 巡检点(points)
--           巡检路线(routes) 由多个巡检点组成（N:M 关联表 route_points）
-- ============================================================

CREATE DATABASE IF NOT EXISTS robot_monitor
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE robot_monitor;

-- ------------------------------------------------------------
-- 用户表
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id           BIGINT       PRIMARY KEY AUTO_INCREMENT,
    username     VARCHAR(64)  NOT NULL UNIQUE          COMMENT '登录账号',
    password_hash VARCHAR(255) NOT NULL                COMMENT 'bcrypt 密码哈希',
    display_name VARCHAR(128) NOT NULL                 COMMENT '显示名称',
    status       VARCHAR(16)  NOT NULL DEFAULT 'active' COMMENT 'active | disabled',
    created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) COMMENT='系统用户';

-- ------------------------------------------------------------
-- 区域表（巡检责任区域，与 zones 区分：zones 是地图多边形区域）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS areas (
    id          BIGINT       PRIMARY KEY AUTO_INCREMENT,
    name        VARCHAR(128) NOT NULL                  COMMENT '区域名称',
    description TEXT         NULL                      COMMENT '区域描述',
    manager     VARCHAR(64)  NULL                      COMMENT '负责人姓名',
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) COMMENT='巡检责任区域';

-- ------------------------------------------------------------
-- 设备表
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS devices (
    id         BIGINT        PRIMARY KEY AUTO_INCREMENT,
    name       VARCHAR(128)  NOT NULL                  COMMENT '设备名称',
    model      VARCHAR(128)  NOT NULL                  COMMENT '设备型号',
    image_path VARCHAR(512)  NULL                      COMMENT '设备图片路径',
    status     VARCHAR(32)   NOT NULL DEFAULT 'normal' COMMENT 'normal | fault | offline',
    area_id    BIGINT        NULL                      COMMENT '所属区域',
    notes      TEXT          NULL                      COMMENT '备注',
    created_at DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_devices_area FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE SET NULL
) COMMENT='巡检设备';

-- ------------------------------------------------------------
-- 巡检点表
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS points (
    id          BIGINT        PRIMARY KEY AUTO_INCREMENT,
    name        VARCHAR(128)  NOT NULL                  COMMENT '巡检点名称',
    area_id     BIGINT        NULL                      COMMENT '所属区域',
    device_id   BIGINT        NULL                      COMMENT '关联设备',
    lat         DECIMAL(10,7) NOT NULL                  COMMENT '纬度',
    lng         DECIMAL(10,7) NOT NULL                  COMMENT '经度',
    description TEXT          NULL                      COMMENT '位置描述',
    created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_points_area   FOREIGN KEY (area_id)   REFERENCES areas(id)   ON DELETE SET NULL,
    CONSTRAINT fk_points_device FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE SET NULL
) COMMENT='巡检点';

-- ------------------------------------------------------------
-- 巡检路线表
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS routes (
    id          BIGINT       PRIMARY KEY AUTO_INCREMENT,
    name        VARCHAR(128) NOT NULL                  COMMENT '路线名称',
    description TEXT         NULL                      COMMENT '路线描述',
    area_id     BIGINT       NULL                      COMMENT '所属区域（可选）',
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_routes_area FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE SET NULL
) COMMENT='巡检路线';

-- ------------------------------------------------------------
-- 路线-巡检点关联表（N:M）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS route_points (
    id         BIGINT  PRIMARY KEY AUTO_INCREMENT,
    route_id   BIGINT  NOT NULL   COMMENT '路线ID',
    point_id   BIGINT  NOT NULL   COMMENT '巡检点ID',
    sort_order INT     NOT NULL DEFAULT 0 COMMENT '顺序（从0开始）',
    CONSTRAINT fk_rp_route FOREIGN KEY (route_id) REFERENCES routes(id) ON DELETE CASCADE,
    CONSTRAINT fk_rp_point FOREIGN KEY (point_id) REFERENCES points(id) ON DELETE CASCADE,
    UNIQUE KEY uk_route_point (route_id, point_id)
) COMMENT='巡检路线与巡检点的关联（含顺序）';

-- ------------------------------------------------------------
-- 地图区域表（机器人监控用，保留原有）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS zones (
    id           BIGINT       PRIMARY KEY AUTO_INCREMENT,
    name         VARCHAR(128) NOT NULL,
    type         VARCHAR(64)  NOT NULL,
    risk         VARCHAR(32)  NOT NULL,
    status       VARCHAR(32)  NOT NULL,
    frequency    VARCHAR(64)  NOT NULL,
    stroke_color VARCHAR(32)  NULL,
    fill_color   VARCHAR(64)  NULL,
    path_json    JSON         NOT NULL    COMMENT '地图多边形坐标点数组',
    notes        TEXT         NULL,
    created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) COMMENT='地图监控区域（多边形）';

-- ------------------------------------------------------------
-- 机器人表（保留原有）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS robots (
    id         BIGINT        PRIMARY KEY AUTO_INCREMENT,
    model      VARCHAR(128)  NOT NULL,
    zone_id    BIGINT        NULL,
    status     VARCHAR(32)   NOT NULL,
    health     INT           NOT NULL,
    battery    INT           NOT NULL,
    speed      DECIMAL(10,2) NOT NULL,
    `signal`   INT           NOT NULL,
    latency    INT           NOT NULL,
    lng        DECIMAL(12,6) NOT NULL,
    lat        DECIMAL(12,6) NOT NULL,
    heading    INT           NOT NULL,
    created_at DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_robots_zone FOREIGN KEY (zone_id) REFERENCES zones(id) ON DELETE SET NULL
) COMMENT='机器人设备';

-- ------------------------------------------------------------
-- 任务表（保留原有）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tasks (
    id          BIGINT       PRIMARY KEY AUTO_INCREMENT,
    name        VARCHAR(128) NOT NULL,
    robot_id    BIGINT       NULL,
    zone_id     BIGINT       NULL,
    priority    VARCHAR(32)  NOT NULL,
    description TEXT         NULL,
    start_at    DATETIME     NOT NULL,
    end_at      DATETIME     NOT NULL,
    status      VARCHAR(32)  NOT NULL,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_tasks_robot FOREIGN KEY (robot_id) REFERENCES robots(id) ON DELETE SET NULL,
    CONSTRAINT fk_tasks_zone  FOREIGN KEY (zone_id)  REFERENCES zones(id)  ON DELETE SET NULL
) COMMENT='巡检任务';

-- ------------------------------------------------------------
-- 报警表（保留原有）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS alerts (
    id          BIGINT       PRIMARY KEY AUTO_INCREMENT,
    level       VARCHAR(32)  NOT NULL,
    title       VARCHAR(128) NOT NULL,
    detail      TEXT         NULL,
    happened_at DATETIME     NOT NULL,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) COMMENT='报警记录';

-- ------------------------------------------------------------
-- 报告表（保留原有）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reports (
    id          BIGINT       PRIMARY KEY AUTO_INCREMENT,
    title       VARCHAR(128) NOT NULL,
    value       VARCHAR(64)  NOT NULL,
    trend       VARCHAR(64)  NOT NULL,
    tone        VARCHAR(32)  NOT NULL,
    detail      TEXT         NULL,
    report_date DATE         NOT NULL,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) COMMENT='统计报告';
