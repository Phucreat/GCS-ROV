"""
database/schema.py - SQLite DDL Schema & Default Seed Data for Commercial GCS ROV
==================================================================================
Defines 13 relational SQLite tables, WAL mode performance pragmas, high-speed indexes,
and default seed vehicle profiles & calibration parameters.
"""

# SQLite PRAGMA commands for High Performance WAL Mode & Foreign Keys
WAL_PRAGMAS = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA cache_size = -64000;
"""

# Complete DDL Schema Statements
CREATE_TABLES_SQL = """
-- 1. VEHICLE PROFILES
CREATE TABLE IF NOT EXISTS vehicle_profiles (
    vehicle_id TEXT PRIMARY KEY,
    vehicle_name TEXT NOT NULL,
    model_type TEXT DEFAULT '3DC',
    board_type TEXT DEFAULT 'DKBAY_V2',
    is_active INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    description TEXT
);

-- 2. VEHICLE CALIBRATION & PID GAINS
CREATE TABLE IF NOT EXISTS vehicle_calibration (
    calibration_id INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id TEXT NOT NULL,
    sensor_type TEXT NOT NULL,
    offset_x REAL DEFAULT 0.0,
    offset_y REAL DEFAULT 0.0,
    offset_z REAL DEFAULT 0.0,
    scale_x REAL DEFAULT 1.0,
    scale_y REAL DEFAULT 1.0,
    scale_z REAL DEFAULT 1.0,
    kp REAL DEFAULT 0.0,
    ki REAL DEFAULT 0.0,
    kd REAL DEFAULT 0.0,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(vehicle_id) REFERENCES vehicle_profiles(vehicle_id) ON DELETE CASCADE
);

-- 3. GAMEPAD CONFIGURATIONS
CREATE TABLE IF NOT EXISTS gamepad_configs (
    config_id INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id TEXT NOT NULL,
    profile_name TEXT NOT NULL,
    axis_pitch INTEGER DEFAULT 1,
    axis_roll INTEGER DEFAULT 0,
    axis_yaw INTEGER DEFAULT 2,
    axis_throttle INTEGER DEFAULT 3,
    button_arm INTEGER DEFAULT 0,
    button_disarm INTEGER DEFAULT 1,
    button_lights INTEGER DEFAULT 2,
    button_snapshot INTEGER DEFAULT 3,
    deadzone REAL DEFAULT 0.05,
    is_active INTEGER DEFAULT 1,
    FOREIGN KEY(vehicle_id) REFERENCES vehicle_profiles(vehicle_id) ON DELETE CASCADE
);

-- 4. SYSTEM SAFETY THRESHOLDS
CREATE TABLE IF NOT EXISTS system_thresholds (
    threshold_id INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id TEXT NOT NULL UNIQUE,
    min_voltage_v REAL DEFAULT 14.0,
    crit_voltage_v REAL DEFAULT 13.2,
    max_internal_temp_c REAL DEFAULT 65.0,
    max_depth_m REAL DEFAULT 100.0,
    rth_depth_m REAL DEFAULT 2.0,
    leak_failsafe_action TEXT DEFAULT 'EMERGENCY_SURFACE',
    FOREIGN KEY(vehicle_id) REFERENCES vehicle_profiles(vehicle_id) ON DELETE CASCADE
);

-- 5. MISSIONS (SURVEY PLANS)
CREATE TABLE IF NOT EXISTS missions (
    mission_id INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    planned_depth_m REAL DEFAULT 0.0,
    total_waypoints INTEGER DEFAULT 0,
    status TEXT DEFAULT 'DRAFT'
);

-- 6. MISSION WAYPOINTS
CREATE TABLE IF NOT EXISTS mission_waypoints (
    waypoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id INTEGER NOT NULL,
    seq_number INTEGER NOT NULL,
    x_m REAL NOT NULL,
    y_m REAL NOT NULL,
    z_depth_m REAL NOT NULL,
    lat REAL,
    lon REAL,
    heading_deg REAL DEFAULT 0.0,
    hold_time_sec REAL DEFAULT 0.0,
    action TEXT DEFAULT 'WAYPOINT',
    FOREIGN KEY(mission_id) REFERENCES missions(mission_id) ON DELETE CASCADE
);

-- 7. DIVE SESSIONS (MISSION ENCOUNTERS & BLACK BOX HEADER)
CREATE TABLE IF NOT EXISTS dive_sessions (
    session_id TEXT PRIMARY KEY,
    vehicle_id TEXT NOT NULL,
    mission_id INTEGER,
    pilot_name TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT,
    max_depth_m REAL DEFAULT 0.0,
    total_distance_m REAL DEFAULT 0.0,
    location_name TEXT,
    water_density_kg_m3 REAL DEFAULT 1000.0,
    status TEXT DEFAULT 'ONGOING',
    notes TEXT,
    FOREIGN KEY(vehicle_id) REFERENCES vehicle_profiles(vehicle_id),
    FOREIGN KEY(mission_id) REFERENCES missions(mission_id) ON DELETE SET NULL
);

-- 8. TELEMETRY LOGS (HIGH FREQUENCY 10-50Hz BLACK BOX)
CREATE TABLE IF NOT EXISTS telemetry_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    depth_m REAL NOT NULL,
    heading_deg REAL NOT NULL,
    pitch_deg REAL NOT NULL,
    roll_deg REAL NOT NULL,
    voltage_v REAL NOT NULL,
    current_a REAL NOT NULL,
    battery_pct INTEGER NOT NULL,
    water_temp_c REAL DEFAULT 0.0,
    internal_temp_c REAL DEFAULT 0.0,
    pressure_bar REAL DEFAULT 0.0,
    pos_x REAL DEFAULT 0.0,
    pos_y REAL DEFAULT 0.0,
    pos_z REAL DEFAULT 0.0,
    lat REAL,
    lon REAL,
    ekf_status INTEGER DEFAULT 0,
    mode TEXT NOT NULL,
    armed INTEGER NOT NULL,
    FOREIGN KEY(session_id) REFERENCES dive_sessions(session_id) ON DELETE CASCADE
);

-- 9. MEDIA RECORDS (SNAPSHOTS & VIDEOS CATALOG)
CREATE TABLE IF NOT EXISTS media_records (
    media_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    file_path TEXT NOT NULL UNIQUE,
    file_type TEXT NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    resolution TEXT DEFAULT '1920x1080',
    depth_m REAL NOT NULL,
    heading_deg REAL NOT NULL,
    pos_x REAL DEFAULT 0.0,
    pos_y REAL DEFAULT 0.0,
    pos_z REAL DEFAULT 0.0,
    notes TEXT,
    FOREIGN KEY(session_id) REFERENCES dive_sessions(session_id) ON DELETE CASCADE
);

-- 10. AI DETECTIONS CATALOG (YOLOV8 + AI AGENT)
CREATE TABLE IF NOT EXISTS ai_detections (
    detection_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    media_id INTEGER,
    timestamp REAL NOT NULL,
    class_name TEXT NOT NULL,
    confidence REAL NOT NULL,
    bbox_x1 INTEGER,
    bbox_y1 INTEGER,
    bbox_x2 INTEGER,
    bbox_y2 INTEGER,
    depth_m REAL NOT NULL,
    pos_x REAL DEFAULT 0.0,
    pos_y REAL DEFAULT 0.0,
    pos_z REAL DEFAULT 0.0,
    severity_level TEXT DEFAULT 'MEDIUM',
    is_verified INTEGER DEFAULT 0,
    FOREIGN KEY(session_id) REFERENCES dive_sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY(media_id) REFERENCES media_records(media_id) ON DELETE SET NULL
);

-- 11. SLAM 3D POINT CLOUDS (DIGITAL TWIN RECONSTRUCTION)
CREATE TABLE IF NOT EXISTS slam_point_clouds (
    point_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    x_m REAL NOT NULL,
    y_m REAL NOT NULL,
    z_m REAL NOT NULL,
    intensity REAL DEFAULT 1.0,
    rgb_color TEXT,
    feature_label TEXT,
    FOREIGN KEY(session_id) REFERENCES dive_sessions(session_id) ON DELETE CASCADE
);

-- 12. AUDIT LOGS (MILLISECOND AUDIT TRAIL FOR PILOT & AI VIC COMMANDS)
CREATE TABLE IF NOT EXISTS audit_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    source TEXT NOT NULL,
    event_category TEXT NOT NULL,
    event_name TEXT NOT NULL,
    details TEXT,
    severity TEXT DEFAULT 'INFO',
    FOREIGN KEY(session_id) REFERENCES dive_sessions(session_id) ON DELETE CASCADE
);

-- 13. SYSTEM ALERTS LOG
CREATE TABLE IF NOT EXISTS system_alerts (
    alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    alert_code TEXT NOT NULL,
    message TEXT NOT NULL,
    severity TEXT NOT NULL,
    action_taken TEXT,
    ack_by_pilot INTEGER DEFAULT 0,
    FOREIGN KEY(session_id) REFERENCES dive_sessions(session_id) ON DELETE CASCADE
);

-- HIGH-SPEED INDEXES FOR FLIGHT REPLAY & QUERY OPTIMIZATION
CREATE INDEX IF NOT EXISTS idx_telemetry_session_time ON telemetry_logs(session_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_ai_detections_session ON ai_detections(session_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_media_records_session ON media_records(session_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_logs_session ON audit_logs(session_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_system_alerts_session ON system_alerts(session_id, timestamp);
"""

# Default Initial Seed Data
DEFAULT_SEED_DATA_SQL = """
-- Default Vehicle Profile
INSERT OR IGNORE INTO vehicle_profiles (vehicle_id, vehicle_name, model_type, board_type, is_active, created_at, description)
VALUES ('ROV_SUBSEA_PRO_01', 'CNX Subsea Inspector Pro', '3DC', 'DKBAY_V2', 1, datetime('now'), 'Commercial Subsea Inspection ROV');

-- Default Thresholds
INSERT OR IGNORE INTO system_thresholds (vehicle_id, min_voltage_v, crit_voltage_v, max_internal_temp_c, max_depth_m, rth_depth_m, leak_failsafe_action)
VALUES ('ROV_SUBSEA_PRO_01', 14.0, 13.2, 65.0, 100.0, 2.0, 'EMERGENCY_SURFACE');

-- Default Gamepad Config
INSERT OR IGNORE INTO gamepad_configs (vehicle_id, profile_name, axis_pitch, axis_roll, axis_yaw, axis_throttle, button_arm, button_disarm, button_lights, button_snapshot, deadzone, is_active)
VALUES ('ROV_SUBSEA_PRO_01', 'Standard Xbox Gamepad', 1, 0, 2, 3, 0, 1, 2, 3, 0.05, 1);

-- Default Calibrations
INSERT OR IGNORE INTO vehicle_calibration (vehicle_id, sensor_type, offset_x, offset_y, offset_z, scale_x, scale_y, scale_z, kp, ki, kd, updated_at)
VALUES ('ROV_SUBSEA_PRO_01', 'IMU_ACCEL', 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, datetime('now'));

INSERT OR IGNORE INTO vehicle_calibration (vehicle_id, sensor_type, offset_x, offset_y, offset_z, scale_x, scale_y, scale_z, kp, ki, kd, updated_at)
VALUES ('ROV_SUBSEA_PRO_01', 'PID_DEPTH', 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.5, 0.2, 0.8, datetime('now'));
"""
