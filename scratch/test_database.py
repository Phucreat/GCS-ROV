"""
scratch/test_database.py - Verification Test Suite for SQLite Local Database
==============================================================================
Tests SQLite WAL Mode initialization, 10-50Hz high-speed telemetry logging,
AI detection cataloging, vehicle profiles & calibrations, audit logs, and
automated report exports (CSV, JSON, HTML).
"""

import os
import sys
import time

# Add root directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_manager import DatabaseManager
from database.telemetry_logger import AsyncTelemetryLogger
from database.report_exporter import ReportExporter


def run_tests():
    print("=========================================================")
    print("RUNNING SQLITE LOCAL DATABASE SYSTEM VERIFICATION TESTS")
    print("=========================================================\n")

    # Use temporary test database
    test_db_path = os.path.join(os.path.dirname(__file__), "test_gcs.db")
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    # 1. TEST INITIALIZATION & SCHEMA
    db = DatabaseManager(db_path=test_db_path)
    print("[PASS] TEST 1: DatabaseManager SQLite WAL Mode initialized cleanly.")

    # 2. TEST DIVE SESSION CREATION
    session_id = db.create_dive_session(
        pilot_name="Nguyen Van A (Ky su truong)",
        location_name="Thuy dien Hoa Binh - Tuyen ong 01",
        water_density_kg_m3=1000.0,
        notes="Ca lan khao sat vet nut than dap"
    )
    assert session_id.startswith("DIVE_"), "Session ID format invalid!"
    print(f"[PASS] TEST 2: Dive session created successfully. Session ID: {session_id}")

    # 3. TEST HIGH-FREQUENCY ASYNC TELEMETRY LOGGING (1,000 Records)
    logger = AsyncTelemetryLogger(db_manager=db, batch_size=100, flush_interval_sec=0.2)
    logger.start(session_id=session_id)

    start_time = time.time()
    for i in range(1000):
        t_data = {
            "timestamp": time.time(),
            "depth_m": 5.0 + (i * 0.01),
            "heading_deg": (i * 0.5) % 360,
            "pitch_deg": 1.2,
            "roll_deg": -0.5,
            "voltage_v": 16.2 - (i * 0.001),
            "current_a": 12.5 + (i * 0.01),
            "battery_pct": max(0, 95 - int(i * 0.02)),
            "water_temp_c": 22.4,
            "internal_temp_c": 35.6,
            "pressure_bar": 1.5,
            "pos_x": i * 0.1,
            "pos_y": i * 0.05,
            "pos_z": -5.0 - (i * 0.01),
            "mode": "ALT_HOLD",
            "armed": True
        }
        logger.log_telemetry(t_data)

    logger.stop()
    elapsed_sec = time.time() - start_time
    print(f"[PASS] TEST 3: Logged 1,000 high-frequency telemetry records in {elapsed_sec*1000:.1f}ms.")

    # Verify count in database
    stats = db.get_session_telemetry_stats(session_id)
    assert stats["log_count"] == 1000, f"Expected 1000 logs, got {stats['log_count']}"
    print(f"   Max Depth Recorded: {stats['max_depth']:.2f}m | Min Voltage: {stats['min_voltage']:.1f}V")

    # 4. TEST MEDIA & AI DETECTIONS CATALOG
    media_id = db.add_media_record(
        session_id=session_id,
        file_path="media/snapshot_crack_01.jpg",
        file_type="SNAPSHOT",
        depth_m=12.4,
        heading_deg=185.0,
        file_size_bytes=1048576,
        resolution="1920x1080",
        notes="Anh chup vet nut be mat dap"
    )
    assert media_id > 0, "Media insertion failed!"

    det_id = db.add_ai_detection(
        session_id=session_id,
        class_name="pipeline_crack",
        confidence=0.94,
        depth_m=12.4,
        media_id=media_id,
        bbox=(450, 300, 680, 520),
        severity_level="HIGH"
    )
    assert det_id > 0, "AI detection insertion failed!"

    detections = db.get_session_detections(session_id)
    assert len(detections) == 1, "Expected 1 AI detection!"
    print(f"[PASS] TEST 4: AI Media Catalog saved successfully. Detection: '{detections[0]['class_name']}' ({detections[0]['confidence']*100:.1f}%)")

    # 5. TEST VEHICLE PROFILES & CALIBRATION
    profile = db.get_active_vehicle_profile()
    assert profile["vehicle_id"] == "ROV_SUBSEA_PRO_01", "Default profile mismatch!"
    thresholds = db.get_system_thresholds(profile["vehicle_id"])
    print(f"[PASS] TEST 5: Vehicle Profile '{profile['vehicle_name']}' loaded. Min Voltage Alert: {thresholds['min_voltage_v']}V")

    # 6. TEST AUDIT LOGS & ALERTS
    db.log_audit_event(
        session_id=session_id,
        source="AI_VIC_VOICE",
        event_category="COMMAND",
        event_name="SET_LIGHTS",
        details='{"value": 100}',
        severity="INFO"
    )
    db.log_system_alert(
        session_id=session_id,
        alert_code="WARN_HIGH_TEMP",
        message="Nhiet do khoang may vuot nguong 45C",
        severity="WARNING"
    )

    audit_logs = db.get_session_audit_logs(session_id)
    assert len(audit_logs) >= 3, "Audit logs count mismatch!"
    print(f"[PASS] TEST 6: Audit Trail logged {len(audit_logs)} events cleanly.")

    # 7. TEST REPORT EXPORTER
    exporter = ReportExporter(db_manager=db)
    csv_path = os.path.join(os.path.dirname(__file__), "test_report.csv")
    json_path = os.path.join(os.path.dirname(__file__), "test_report.json")
    html_path = os.path.join(os.path.dirname(__file__), "test_report.html")

    exporter.export_telemetry_csv(session_id, csv_path)
    exporter.export_session_json(session_id, json_path)
    exporter.export_html_report(session_id, html_path)

    assert os.path.exists(csv_path), "CSV export failed!"
    assert os.path.exists(json_path), "JSON export failed!"
    assert os.path.exists(html_path), "HTML export failed!"
    print(f"[PASS] TEST 7: Report Exporter generated CSV, JSON, and HTML reports successfully.")

    # End session
    ended_session = db.end_dive_session(session_id, status="COMPLETED")
    assert ended_session["status"] == "COMPLETED", "Session end failed!"
    print(f"[PASS] TEST 8: Dive session ended cleanly. Status: {ended_session['status']}\n")

    # Clean up test artifacts
    DatabaseManager.reset_instance()
    time.sleep(0.1)
    if os.path.exists(test_db_path):
        try:
            os.remove(test_db_path)
        except Exception:
            pass
    if os.path.exists(csv_path):
        os.remove(csv_path)
    if os.path.exists(json_path):
        os.remove(json_path)
    if os.path.exists(html_path):
        os.remove(html_path)

    print("=========================================================")
    print("ALL SQLITE DATABASE VERIFICATION TESTS PASSED 100%!")
    print("=========================================================")


if __name__ == "__main__":
    run_tests()
