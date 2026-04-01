-- ============================================================
-- robot_monitor 数据库结构
-- 包含用户、区域、设备、点位、路线，以及机器人、任务、告警、报告和 IoT 相关表
-- ============================================================

CREATE DATABASE IF NOT EXISTS robot_monitor
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE robot_monitor;

-- ------------------------------------------------------------
-- 用户表
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id            BIGINT        PRIMARY KEY AUTO_INCREMENT,
    username      VARCHAR(64)   NOT NULL UNIQUE           COMMENT '登录用户名',
    password_hash VARCHAR(255)  NOT NULL                  COMMENT 'bcrypt 密码哈希',
    display_name  VARCHAR(128)  NOT NULL                  COMMENT '显示名称',
    status        VARCHAR(16)   NOT NULL DEFAULT 'active' COMMENT 'active | disabled',
    created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
) COMMENT='系统用户';

-- ------------------------------------------------------------
-- 巡检区域表
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS areas (
    id          BIGINT        PRIMARY KEY AUTO_INCREMENT,
    name        VARCHAR(128)  NOT NULL                  COMMENT '区域名称',
    description TEXT          NULL                      COMMENT '区域说明',
    manager     VARCHAR(64)   NULL                      COMMENT '负责人',
    created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
) COMMENT='巡检区域';

-- ------------------------------------------------------------
-- 设备表
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS devices (
    id         BIGINT        PRIMARY KEY AUTO_INCREMENT,
    name       VARCHAR(128)  NOT NULL                  COMMENT '设备名称',
    model      VARCHAR(128)  NOT NULL                  COMMENT '设备型号',
    image_path VARCHAR(512)  NULL                      COMMENT '设备图片路径',
    status     VARCHAR(32)   NOT NULL DEFAULT 'normal' COMMENT 'normal | fault | offline',
    area_id    BIGINT        NULL                      COMMENT '所属区域 ID',
    notes      TEXT          NULL                      COMMENT '备注',
    created_at DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_devices_area FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE SET NULL
) COMMENT='巡检设备';

-- ------------------------------------------------------------
-- 巡检点表
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS points (
    id          BIGINT         PRIMARY KEY AUTO_INCREMENT,
    name        VARCHAR(128)   NOT NULL                  COMMENT '点位名称',
    area_id     BIGINT         NULL                      COMMENT '所属区域 ID',
    device_id   BIGINT         NULL                      COMMENT '关联设备 ID',
    lat         DECIMAL(10,7)  NOT NULL                  COMMENT '纬度',
    lng         DECIMAL(10,7)  NOT NULL                  COMMENT '经度',
    description TEXT           NULL                      COMMENT '点位说明',
    created_at  DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_points_area   FOREIGN KEY (area_id)   REFERENCES areas(id)   ON DELETE SET NULL,
    CONSTRAINT fk_points_device FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE SET NULL
) COMMENT='巡检点';

-- ------------------------------------------------------------
-- 巡检路线表
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS routes (
    id          BIGINT        PRIMARY KEY AUTO_INCREMENT,
    name        VARCHAR(128)  NOT NULL                  COMMENT '路线名称',
    description TEXT          NULL                      COMMENT '路线说明',
    area_id     BIGINT        NULL                      COMMENT '所属区域 ID，可为空',
    created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_routes_area FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE SET NULL
) COMMENT='巡检路线';

-- ------------------------------------------------------------
-- 路线与点位关系表（多对多）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS route_points (
    id         BIGINT  PRIMARY KEY AUTO_INCREMENT,
    route_id   BIGINT  NOT NULL   COMMENT '路线 ID',
    point_id   BIGINT  NOT NULL   COMMENT '点位 ID',
    sort_order INT     NOT NULL DEFAULT 0 COMMENT '排序序号，越小越靠前',
    CONSTRAINT fk_rp_route FOREIGN KEY (route_id) REFERENCES routes(id) ON DELETE CASCADE,
    CONSTRAINT fk_rp_point FOREIGN KEY (point_id) REFERENCES points(id) ON DELETE CASCADE,
    UNIQUE KEY uk_route_point (route_id, point_id)
) COMMENT='路线点位关联及排序';

-- ------------------------------------------------------------
-- 巡检区域绘制表
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS zones (
    id           BIGINT        PRIMARY KEY AUTO_INCREMENT,
    name         VARCHAR(128)  NOT NULL,
    type         VARCHAR(64)   NOT NULL,
    risk         VARCHAR(32)   NOT NULL,
    status       VARCHAR(32)   NOT NULL,
    frequency    VARCHAR(64)   NOT NULL,
    stroke_color VARCHAR(32)   NULL,
    fill_color   VARCHAR(64)   NULL,
    path_json    JSON          NOT NULL    COMMENT '区域多边形路径 JSON',
    notes        TEXT          NULL,
    created_at   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
) COMMENT='巡检区域控制配置';

-- ------------------------------------------------------------
-- 机器人表
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS robots (
    id         BIGINT         PRIMARY KEY AUTO_INCREMENT,
    model      VARCHAR(128)   NOT NULL,
    ip_address VARCHAR(64)    NULL,
    zone_id    BIGINT         NULL,
    status     VARCHAR(32)    NOT NULL,
    health     INT            NOT NULL,
    battery    INT            NOT NULL,
    speed      DECIMAL(10,2)  NOT NULL,
    `signal`   INT            NOT NULL,
    latency    INT            NOT NULL,
    lng        DECIMAL(12,6)  NOT NULL,
    lat        DECIMAL(12,6)  NOT NULL,
    heading    INT            NOT NULL,
    created_at DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_robots_zone FOREIGN KEY (zone_id) REFERENCES zones(id) ON DELETE SET NULL
) COMMENT='巡检机器人';

-- ------------------------------------------------------------
-- 任务表
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tasks (
    id          BIGINT        PRIMARY KEY AUTO_INCREMENT,
    name        VARCHAR(128)  NOT NULL,
    robot_id    BIGINT        NULL,
    zone_id     BIGINT        NULL,
    priority    VARCHAR(32)   NOT NULL,
    description TEXT          NULL,
    start_at    DATETIME      NOT NULL,
    end_at      DATETIME      NOT NULL,
    status      VARCHAR(32)   NOT NULL,
    created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_tasks_robot FOREIGN KEY (robot_id) REFERENCES robots(id) ON DELETE SET NULL,
    CONSTRAINT fk_tasks_zone  FOREIGN KEY (zone_id)  REFERENCES zones(id)  ON DELETE SET NULL
) COMMENT='巡检任务';

-- ------------------------------------------------------------
-- 告警表
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS alerts (
    id          BIGINT        PRIMARY KEY AUTO_INCREMENT,
    level       VARCHAR(32)   NOT NULL,
    title       VARCHAR(128)  NOT NULL,
    detail      TEXT          NULL,
    happened_at DATETIME      NOT NULL,
    created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
) COMMENT='系统告警';

-- ------------------------------------------------------------
-- 报告表
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reports (
    id          BIGINT        PRIMARY KEY AUTO_INCREMENT,
    title       VARCHAR(128)  NOT NULL,
    value       VARCHAR(64)   NOT NULL,
    trend       VARCHAR(64)   NOT NULL,
    tone        VARCHAR(32)   NOT NULL,
    detail      TEXT          NULL,
    report_date DATE          NOT NULL,
    created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
) COMMENT='运行报告';

-- ------------------------------------------------------------
-- IoT：设备 Token 表
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS device_tokens (
    id         BIGINT        PRIMARY KEY AUTO_INCREMENT,
    device_id  BIGINT        NOT NULL                   COMMENT '设备 ID',
    token      VARCHAR(128)  NOT NULL UNIQUE            COMMENT '设备访问 Token（SHA-256 十六进制）',
    note       VARCHAR(256)  NULL                       COMMENT '备注',
    is_active  TINYINT(1)    NOT NULL DEFAULT 1         COMMENT '是否启用',
    created_at DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_dt_device FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
) COMMENT='设备访问 Token';

-- ------------------------------------------------------------
-- IoT：设备签到表
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS device_checkins (
    id         BIGINT         PRIMARY KEY AUTO_INCREMENT,
    device_id  BIGINT         NOT NULL                   COMMENT '设备 ID',
    point_id   BIGINT         NULL                       COMMENT '巡检点 ID',
    route_id   BIGINT         NULL                       COMMENT '路线 ID',
    lat        DECIMAL(10,7)  NULL                       COMMENT '纬度',
    lng        DECIMAL(10,7)  NULL                       COMMENT '经度',
    note       TEXT           NULL                       COMMENT '备注',
    checked_at DATETIME       NOT NULL                   COMMENT '签到时间',
    created_at DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_ci_device FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
    CONSTRAINT fk_ci_point  FOREIGN KEY (point_id)  REFERENCES points(id)  ON DELETE SET NULL,
    CONSTRAINT fk_ci_route  FOREIGN KEY (route_id)  REFERENCES routes(id)  ON DELETE SET NULL
) COMMENT='设备签到记录';

-- ------------------------------------------------------------
-- IoT：设备遥测表
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS device_telemetry (
    id          BIGINT         PRIMARY KEY AUTO_INCREMENT,
    device_id   BIGINT         NOT NULL                   COMMENT '设备 ID',
    battery     TINYINT        NULL                       COMMENT '电量 0-100',
    `signal`    TINYINT        NULL                       COMMENT '信号强度 0-100',
    status      VARCHAR(32)    NULL                       COMMENT '状态 online|offline|fault',
    lat         DECIMAL(10,7)  NULL                       COMMENT '纬度',
    lng         DECIMAL(10,7)  NULL                       COMMENT '经度',
    extra_json  JSON           NULL                       COMMENT '附加信息',
    reported_at DATETIME       NOT NULL                   COMMENT '上报时间',
    created_at  DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_tel_device FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
) COMMENT='设备遥测记录';

CREATE INDEX idx_telemetry_device_time ON device_telemetry (device_id, reported_at DESC);
