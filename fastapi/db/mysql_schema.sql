CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(64) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(128) NOT NULL,
    created_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS zones (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(128) NOT NULL,
    type VARCHAR(64) NOT NULL,
    risk VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    frequency VARCHAR(64) NOT NULL,
    stroke_color VARCHAR(32) NULL,
    fill_color VARCHAR(64) NULL,
    path_json JSON NOT NULL,
    notes TEXT NULL,
    created_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS robots (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    model VARCHAR(128) NOT NULL,
    zone_id BIGINT NULL,
    status VARCHAR(32) NOT NULL,
    health INT NOT NULL,
    battery INT NOT NULL,
    speed DECIMAL(10,2) NOT NULL,
    `signal` INT NOT NULL,
    latency INT NOT NULL,
    lng DECIMAL(12,6) NOT NULL,
    lat DECIMAL(12,6) NOT NULL,
    heading INT NOT NULL,
    created_at DATETIME NOT NULL,
    CONSTRAINT fk_robots_zone FOREIGN KEY (zone_id) REFERENCES zones(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(128) NOT NULL,
    robot_id BIGINT NULL,
    zone_id BIGINT NULL,
    priority VARCHAR(32) NOT NULL,
    description TEXT NULL,
    start_at DATETIME NOT NULL,
    end_at DATETIME NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at DATETIME NOT NULL,
    CONSTRAINT fk_tasks_robot FOREIGN KEY (robot_id) REFERENCES robots(id) ON DELETE SET NULL,
    CONSTRAINT fk_tasks_zone FOREIGN KEY (zone_id) REFERENCES zones(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    level VARCHAR(32) NOT NULL,
    title VARCHAR(128) NOT NULL,
    detail TEXT NULL,
    happened_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    title VARCHAR(128) NOT NULL,
    value VARCHAR(64) NOT NULL,
    trend VARCHAR(64) NOT NULL,
    tone VARCHAR(32) NOT NULL,
    detail TEXT NULL,
    report_date DATE NOT NULL,
    created_at DATETIME NOT NULL
);
