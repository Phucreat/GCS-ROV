"""
database/db_manager.py - Core SQLite Database Manager Singleton for GCS ROV
==========================================================================
Provides thread-safe access to local SQLite WAL database. Handles ca lặn (dive sessions),
telemetry black box logging, AI detections, vehicle profiles, calibrations, missions,
SLAM 3D points, and millisecond audit logs.
"""

import os
import sqlite3
import time
import datetime
import threading
import json
from typing import Dict, List, Any, Optional, Tuple

from .schema import WAL_PRAGMAS, CREATE_TABLES_SQL, DEFAULT_SEED_DATA_SQL


class DatabaseManager:
    """
    Singleton Database Manager for GCS ROV SQLite persistence.
    Provides WAL mode, foreign key integrity, and CRUD operations for all modules.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DatabaseManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, db_path: Optional[str] = None):
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return

            if db_path is None:
                try:
                    from utils.path_utils import get_db_path
                    self.db_path = get_db_path()
                except Exception:
                    base_dir = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
                    db_dir = os.path.join(base_dir, "CNC_NExora", "logs", "db")
                    os.makedirs(db_dir, exist_ok=True)
                    self.db_path = os.path.join(db_dir, "gcs_database.db")
            else:
                self.db_path = db_path
                os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

            self.db_lock = threading.Lock()
            self._active_session_id = None
            self._init_db()
            self._initialized = True
            print(f"[DatabaseManager] SQLite WAL Database initialized successfully at: {self.db_path}")

    @classmethod
    def reset_instance(cls):
        """Reset singleton instance for testing."""
        with cls._lock:
            cls._instance = None

    def _get_connection(self) -> sqlite3.Connection:
        """Create connection with WAL mode and row factory."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode and foreign keys
        conn.executescript(WAL_PRAGMAS)
        return conn

    def _init_db(self):
        """Execute DDL schema creation and default seed data."""
        with self.db_lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.executescript(CREATE_TABLES_SQL)
                cursor.executescript(DEFAULT_SEED_DATA_SQL)
                conn.commit()

    # ── DIVE SESSION MANAGEMENT (CA LẶN & HỘP ĐEN HEADER) ────────── #

    def create_dive_session(
        self,
        pilot_name: str = "Pilot Administrator",
        vehicle_id: str = "ROV_SUBSEA_PRO_01",
        mission_id: Optional[int] = None,
        location_name: Optional[str] = "Offshore Facility",
        water_density_kg_m3: float = 1000.0,
        notes: Optional[str] = None,
    ) -> str:
        """Create a new dive session (Ca lặn mới). Returns unique session_id."""
        now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        session_id = f"DIVE_{now_str}"
        start_time_iso = datetime.datetime.now().isoformat()

        with self.db_lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO dive_sessions (
                        session_id, vehicle_id, mission_id, pilot_name, start_time,
                        location_name, water_density_kg_m3, status, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'ONGOING', ?)
                    """,
                    (session_id, vehicle_id, mission_id, pilot_name, start_time_iso,
                     location_name, water_density_kg_m3, notes)
                )
                conn.commit()

        self._active_session_id = session_id

        # Log audit event for session creation
        self.log_audit_event(
            session_id=session_id,
            source="PILOT_GUI",
            event_category="DIVE_SESSION",
            event_name="START_DIVE_SESSION",
            details=f"Ca lặn mới được tạo bởi {pilot_name} tại {location_name}",
            severity="INFO"
        )
        print(f"[DatabaseManager] Created active dive session: {session_id}")
        return session_id

    def get_active_session_id(self) -> Optional[str]:
        return self._active_session_id

    @property
    def active_session_id(self) -> Optional[str]:
        return self._active_session_id

    def set_active_session_id(self, session_id: str):
        self._active_session_id = session_id

    def end_dive_session(
        self,
        session_id: Optional[str] = None,
        status: str = "COMPLETED",
        notes: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """End an ongoing dive session, calculating final statistics."""
        sid = session_id or self._active_session_id
        if not sid:
            return None

        end_time_iso = datetime.datetime.now().isoformat()

        with self.db_lock:
            with self._get_connection() as conn:
                # Calculate max depth and stats from telemetry_logs
                row = conn.execute(
                    "SELECT MAX(depth_m) as max_depth FROM telemetry_logs WHERE session_id = ?",
                    (sid,)
                ).fetchone()
                max_depth = float(row["max_depth"]) if row and row["max_depth"] is not None else 0.0

                conn.execute(
                    """
                    UPDATE dive_sessions
                    SET end_time = ?, status = ?, max_depth_m = ?, notes = COALESCE(?, notes)
                    WHERE session_id = ?
                    """,
                    (end_time_iso, status, max_depth, notes, sid)
                )
                conn.commit()

                session_row = conn.execute(
                    "SELECT * FROM dive_sessions WHERE session_id = ?", (sid,)
                ).fetchone()

        if self._active_session_id == sid:
            self._active_session_id = None

        self.log_audit_event(
            session_id=sid,
            source="PILOT_GUI",
            event_category="DIVE_SESSION",
            event_name="END_DIVE_SESSION",
            details=f"Kết thúc ca lặn. Trạng thái: {status}, Độ sâu max: {max_depth:.2f}m",
            severity="INFO"
        )
        print(f"[DatabaseManager] Ended dive session: {sid} ({status})")
        return dict(session_row) if session_row else None

    def get_all_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent dive sessions list."""
        with self.db_lock:
            with self._get_connection() as conn:
                rows = conn.execute(
                    "SELECT * FROM dive_sessions ORDER BY start_time DESC LIMIT ?", (limit,)
                ).fetchall()
                return [dict(r) for r in rows]

    def get_session_by_id(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get dive session details by session_id."""
        with self.db_lock:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT * FROM dive_sessions WHERE session_id = ?", (session_id,)
                ).fetchone()
                return dict(row) if row else None

    # ── TELEMETRY LOGGING (HỘP ĐEN VIỄN TRẮC 10-50Hz) ────────── #

    def insert_telemetry_batch(self, session_id: str, telemetry_records: List[Dict[str, Any]]):
        """Batch insert telemetry records into telemetry_logs (called by AsyncTelemetryLogger)."""
        if not telemetry_records or not session_id:
            return

        tuples_to_insert = []
        for t in telemetry_records:
            tuples_to_insert.append((
                session_id,
                float(t.get("timestamp", time.time())),
                float(t.get("depth_m", t.get("depth", 0.0))),
                float(t.get("heading_deg", t.get("heading", 0.0))),
                float(t.get("pitch_deg", t.get("pitch", 0.0))),
                float(t.get("roll_deg", t.get("roll", 0.0))),
                float(t.get("voltage_v", t.get("voltage", 16.8))),
                float(t.get("current_a", t.get("current", 0.0))),
                int(t.get("battery_pct", 100)),
                float(t.get("water_temp_c", 0.0)),
                float(t.get("internal_temp_c", t.get("temp", 25.0))),
                float(t.get("pressure_bar", 0.0)),
                float(t.get("pos_x", 0.0)),
                float(t.get("pos_y", 0.0)),
                float(t.get("pos_z", 0.0)),
                t.get("lat"),
                t.get("lon"),
                int(t.get("ekf_status", 0)),
                str(t.get("mode", "ALT_HOLD")),
                1 if t.get("armed", False) else 0
            ))

        sql = """
        INSERT INTO telemetry_logs (
            session_id, timestamp, depth_m, heading_deg, pitch_deg, roll_deg,
            voltage_v, current_a, battery_pct, water_temp_c, internal_temp_c,
            pressure_bar, pos_x, pos_y, pos_z, lat, lon, ekf_status, mode, armed
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        with self.db_lock:
            with self._get_connection() as conn:
                conn.executemany(sql, tuples_to_insert)
                conn.commit()

    def get_session_telemetry(self, session_id: str, limit: int = 10000) -> List[Dict[str, Any]]:
        """Retrieve telemetry records for flight replay / analysis."""
        with self.db_lock:
            with self._get_connection() as conn:
                rows = conn.execute(
                    "SELECT * FROM telemetry_logs WHERE session_id = ? ORDER BY timestamp ASC LIMIT ?",
                    (session_id, limit)
                ).fetchall()
                return [dict(r) for r in rows]

    def get_session_telemetry_stats(self, session_id: str) -> Dict[str, Any]:
        """Aggregate statistical summary for a dive session."""
        with self.db_lock:
            with self._get_connection() as conn:
                row = conn.execute(
                    """
                    SELECT 
                        COUNT(*) as log_count,
                        MAX(depth_m) as max_depth,
                        AVG(depth_m) as avg_depth,
                        MIN(voltage_v) as min_voltage,
                        MAX(internal_temp_c) as max_temp,
                        AVG(current_a) as avg_current
                    FROM telemetry_logs WHERE session_id = ?
                    """,
                    (session_id,)
                ).fetchone()
                return dict(row) if row else {}

    # ── AI DETECTIONS & MEDIA CATALOG ────────── #

    def add_media_record(
        self,
        session_id: str,
        file_path: str,
        file_type: str = "SNAPSHOT",
        depth_m: float = 0.0,
        heading_deg: float = 0.0,
        file_size_bytes: int = 0,
        resolution: str = "1920x1080",
        pos_x: float = 0.0, pos_y: float = 0.0, pos_z: float = 0.0,
        notes: Optional[str] = None
    ) -> int:
        """Add media file (photo/video) catalog entry. Returns media_id."""
        now_ts = time.time()
        with self.db_lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO media_records (
                        session_id, timestamp, file_path, file_type, file_size_bytes,
                        resolution, depth_m, heading_deg, pos_x, pos_y, pos_z, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (session_id, now_ts, file_path, file_type, file_size_bytes,
                     resolution, depth_m, heading_deg, pos_x, pos_y, pos_z, notes)
                )
                conn.commit()
                return cursor.lastrowid

    def add_ai_detection(
        self,
        session_id: str,
        class_name: str,
        confidence: float,
        depth_m: float,
        media_id: Optional[int] = None,
        bbox: Optional[Tuple[int, int, int, int]] = None,
        pos_x: float = 0.0, pos_y: float = 0.0, pos_z: float = 0.0,
        severity_level: str = "MEDIUM"
    ) -> int:
        """Log AI Vision target detection (YOLOv8 / AI Agent). Returns detection_id."""
        now_ts = time.time()
        bbox_x1, bbox_y1, bbox_x2, bbox_y2 = bbox if bbox else (None, None, None, None)

        with self.db_lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO ai_detections (
                        session_id, media_id, timestamp, class_name, confidence,
                        bbox_x1, bbox_y1, bbox_x2, bbox_y2, depth_m,
                        pos_x, pos_y, pos_z, severity_level, is_verified
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (session_id, media_id, now_ts, class_name, confidence,
                     bbox_x1, bbox_y1, bbox_x2, bbox_y2, depth_m,
                     pos_x, pos_y, pos_z, severity_level)
                )
                conn.commit()
                det_id = cursor.lastrowid

        self.log_audit_event(
            session_id=session_id,
            source="AI_YOLO_VISION",
            event_category="AI_DETECTION",
            event_name="TARGET_DETECTED",
            details=f"Phát hiện '{class_name}' ({confidence*100:.1f}%) ở độ sâu {depth_m:.2f}m",
            severity="WARNING" if severity_level in ("HIGH", "CRITICAL") else "INFO"
        )
        return det_id

    def get_session_media(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all media files recorded for a session."""
        with self.db_lock:
            with self._get_connection() as conn:
                rows = conn.execute(
                    "SELECT * FROM media_records WHERE session_id = ? ORDER BY timestamp ASC",
                    (session_id,)
                ).fetchall()
                return [dict(r) for r in rows]

    def get_session_detections(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all AI detections logged for a session."""
        with self.db_lock:
            with self._get_connection() as conn:
                rows = conn.execute(
                    "SELECT * FROM ai_detections WHERE session_id = ? ORDER BY timestamp ASC",
                    (session_id,)
                ).fetchall()
                return [dict(r) for r in rows]

    # ── VEHICLE PROFILES & CALIBRATION ────────── #

    def get_active_vehicle_profile(self) -> Dict[str, Any]:
        """Get currently active ROV vehicle profile."""
        with self.db_lock:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT * FROM vehicle_profiles WHERE is_active = 1 LIMIT 1"
                ).fetchone()
                if row:
                    return dict(row)
                # Fallback to default if no profile active
                row_def = conn.execute("SELECT * FROM vehicle_profiles LIMIT 1").fetchone()
                return dict(row_def) if row_def else {}

    def get_system_thresholds(self, vehicle_id: str = "ROV_SUBSEA_PRO_01") -> Dict[str, Any]:
        """Get failsafe thresholds for vehicle."""
        with self.db_lock:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT * FROM system_thresholds WHERE vehicle_id = ?", (vehicle_id,)
                ).fetchone()
                return dict(row) if row else {
                    "min_voltage_v": 14.0,
                    "crit_voltage_v": 13.2,
                    "max_internal_temp_c": 65.0,
                    "max_depth_m": 100.0,
                    "rth_depth_m": 2.0,
                    "leak_failsafe_action": "EMERGENCY_SURFACE"
                }

    # ── AUDIT TRAIL & SYSTEM ALERTS ────────── #

    def log_audit_event(
        self,
        session_id: Optional[str],
        source: str,
        event_category: str,
        event_name: str,
        details: Optional[str] = None,
        severity: str = "INFO"
    ):
        """Log millisecond audit trail event for legal & safety compliance."""
        sid = session_id or self._active_session_id or "SYSTEM"
        now_ts = time.time()

        with self.db_lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO audit_logs (
                        session_id, timestamp, source, event_category, event_name, details, severity
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (sid, now_ts, source, event_category, event_name, details, severity)
                )
                conn.commit()

    def log_system_alert(
        self,
        session_id: Optional[str],
        alert_code: str,
        message: str,
        severity: str = "WARNING",
        action_taken: Optional[str] = None
    ):
        """Log system safety alert event."""
        sid = session_id or self._active_session_id or "SYSTEM"
        now_ts = time.time()

        with self.db_lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO system_alerts (
                        session_id, timestamp, alert_code, message, severity, action_taken, ack_by_pilot
                    ) VALUES (?, ?, ?, ?, ?, ?, 0)
                    """,
                    (sid, now_ts, alert_code, message, severity, action_taken)
                )
                conn.commit()

        self.log_audit_event(
            session_id=sid,
            source="SAFETY_GUARD",
            event_category="SYSTEM_ALERT",
            event_name=alert_code,
            details=message,
            severity=severity
        )

    def get_session_audit_logs(self, session_id: str) -> List[Dict[str, Any]]:
        """Retrieve complete audit trail for a dive session."""
        with self.db_lock:
            with self._get_connection() as conn:
                rows = conn.execute(
                    "SELECT * FROM audit_logs WHERE session_id = ? ORDER BY timestamp ASC",
                    (session_id,)
                ).fetchall()
                return [dict(r) for r in rows]

    def get_session_alerts(self, session_id: str) -> List[Dict[str, Any]]:
        """Retrieve system alerts for a dive session."""
        with self.db_lock:
            with self._get_connection() as conn:
                rows = conn.execute(
                    "SELECT * FROM system_alerts WHERE session_id = ? ORDER BY timestamp ASC",
                    (session_id,)
                ).fetchall()
                return [dict(r) for r in rows]
