"""
database/report_exporter.py - Automated Mission Survey Report Generator
========================================================================
Queries SQLite database by session_id to generate commercial mission reports
in CSV, JSON, and formatted HTML/PDF formats for clients and engineers.
"""

import os
import csv
import json
import time
import datetime
from typing import Dict, Any, Optional

from .db_manager import DatabaseManager


class ReportExporter:
    """
    Export manager for generating commercial dive survey reports from SQLite database.
    """

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager()

    def export_telemetry_csv(self, session_id: str, output_path: str) -> str:
        """Export raw telemetry black box logs to CSV file."""
        records = self.db.get_session_telemetry(session_id, limit=100000)
        if not records:
            raise ValueError(f"No telemetry records found for session {session_id}")

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        keys = list(records[0].keys())
        with open(output_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(records)

        print(f"[ReportExporter] Telemetry CSV exported: {output_path}")
        return output_path

    def export_session_json(self, session_id: str, output_path: str) -> str:
        """Export complete dive session metadata, AI detections, and audit logs to JSON."""
        session = self.db.get_session_by_id(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found.")

        stats = self.db.get_session_telemetry_stats(session_id)
        media = self.db.get_session_media(session_id)
        detections = self.db.get_session_detections(session_id)
        audit_logs = self.db.get_session_audit_logs(session_id)
        alerts = self.db.get_session_alerts(session_id)

        package = {
            "session_header": session,
            "telemetry_summary": stats,
            "media_catalog": media,
            "ai_detections": detections,
            "audit_trail": audit_logs,
            "system_alerts": alerts,
            "export_timestamp": datetime.datetime.now().isoformat()
        }

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(package, f, indent=2, ensure_ascii=False)

        print(f"[ReportExporter] Full session JSON exported: {output_path}")
        return output_path

    def export_html(self, session_id: str, output_path: Optional[str] = None) -> str:
        """Alias for export_html_report with automatic safe default path in User Documents."""
        if not output_path:
            try:
                from utils.path_utils import get_default_media_dir
                media_dir = get_default_media_dir()
            except Exception:
                media_dir = os.path.join(os.path.expanduser("~"), "Documents", "CNC_NExora_Media")
            output_path = os.path.join(media_dir, f"report_{session_id}.html")
        return self.export_html_report(session_id, output_path)

    def export_html_report(self, session_id: str, output_path: str) -> str:
        """Generate an executive HTML Mission Survey Report for clients."""
        session = self.db.get_session_by_id(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found.")

        stats = self.db.get_session_telemetry_stats(session_id)
        media = self.db.get_session_media(session_id)
        detections = self.db.get_session_detections(session_id)
        alerts = self.db.get_session_alerts(session_id)

        # HTML Template
        html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>BÁO CÁO KHẢO SÁT CA LẶN ROV - {session_id}</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; background-color: #0A1423; color: #E2F1FF; margin: 0; padding: 20px; }}
        .container {{ max-width: 1100px; margin: 0 auto; background-color: #0F2035; border: 1px solid #1D3554; border-radius: 8px; padding: 30px; }}
        h1 {{ color: #00D4FF; border-bottom: 2px solid #00D4FF; padding-bottom: 10px; margin-top: 0; }}
        h2 {{ color: #00FF9D; margin-top: 30px; font-size: 18px; border-left: 4px solid #00FF9D; padding-left: 10px; }}
        .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 20px; }}
        .card {{ background: #142338; border: 1px solid #2B4C7E; border-radius: 6px; padding: 15px; text-align: center; }}
        .card .value {{ font-size: 22px; font-weight: bold; color: #00FF9D; margin-top: 5px; }}
        .card .label {{ font-size: 12px; color: #94A9C4; text-transform: uppercase; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
        th, td {{ border: 1px solid #1D3554; padding: 10px; text-align: left; font-size: 13px; }}
        th {{ background-color: #142338; color: #00D4FF; }}
        tr:nth-child(even) {{ background-color: #0B1728; }}
        .badge {{ padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 11px; display: inline-block; }}
        .badge-warning {{ background: #FFB300; color: #000; }}
        .badge-critical {{ background: #FF5252; color: #FFF; }}
        .footer {{ margin-top: 40px; text-align: center; font-size: 12px; color: #94A9C4; border-top: 1px solid #1D3554; padding-top: 15px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📑 BÁO CÁO KHẢO SÁT SUBSEA ROV</h1>
        <p><strong>Mã ca lặn:</strong> {session['session_id']} | <strong>Địa điểm:</strong> {session.get('location_name', 'N/A')} | <strong>Phi công:</strong> {session['pilot_name']}</p>
        <p><strong>Thời gian bắt đầu:</strong> {session['start_time']} | <strong>Trạng thái:</strong> <span class="badge badge-warning">{session['status']}</span></p>

        <h2>📊 TỔNG QUAN VIỄN TRẮC (TELEMETRY SUMMARY)</h2>
        <div class="grid">
            <div class="card">
                <div class="label">Độ sâu Tối đa</div>
                <div class="value">{stats.get('max_depth', 0.0):.2f} m</div>
            </div>
            <div class="card">
                <div class="label">Tổng Bản ghi Log</div>
                <div class="value">{stats.get('log_count', 0)}</div>
            </div>
            <div class="card">
                <div class="label">Điện áp Thấp nhất</div>
                <div class="value">{stats.get('min_voltage', 0.0):.1f} V</div>
            </div>
            <div class="card">
                <div class="label">Nhiệt độ Max</div>
                <div class="value">{stats.get('max_temp', 0.0):.1f} °C</div>
            </div>
        </div>

        <h2>🤖 PHÁT HIỆN NHẬN DIỆN AI (AI DETECTIONS CATALOG)</h2>
        <table>
            <thead>
                <tr>
                    <th>STT</th>
                    <th>Thời gian</th>
                    <th>Nhãn AI</th>
                    <th>Độ tin cậy</th>
                    <th>Độ sâu (m)</th>
                    <th>Mức độ</th>
                </tr>
            </thead>
            <tbody>
"""
        if detections:
            for idx, d in enumerate(detections, 1):
                ts_str = datetime.datetime.fromtimestamp(d['timestamp']).strftime('%H:%M:%S')
                sev_cls = "badge-critical" if d['severity_level'] in ("HIGH", "CRITICAL") else "badge-warning"
                html += f"""
                <tr>
                    <td>{idx}</td>
                    <td>{ts_str}</td>
                    <td><strong>{d['class_name']}</strong></td>
                    <td>{d['confidence']*100:.1f}%</td>
                    <td>{d['depth_m']:.2f} m</td>
                    <td><span class="badge {sev_cls}">{d['severity_level']}</span></td>
                </tr>
"""
        else:
            html += "<tr><td colspan='6' style='text-align:center;'>Không phát hiện mục tiêu AI trong ca lặn này.</td></tr>"

        html += """
            </tbody>
        </table>

        <h2>⚠️ NHẬT KÝ CẢNH BÁO AN TOÀN (SYSTEM ALERTS)</h2>
        <table>
            <thead>
                <tr>
                    <th>Thời gian</th>
                    <th>Mã cảnh báo</th>
                    <th>Nội dung thông điệp</th>
                    <th>Mức độ</th>
                </tr>
            </thead>
            <tbody>
"""
        if alerts:
            for a in alerts:
                ts_str = datetime.datetime.fromtimestamp(a['timestamp']).strftime('%H:%M:%S')
                html += f"""
                <tr>
                    <td>{ts_str}</td>
                    <td><code>{a['alert_code']}</code></td>
                    <td>{a['message']}</td>
                    <td><span class="badge badge-critical">{a['severity']}</span></td>
                </tr>
"""
        else:
            html += "<tr><td colspan='4' style='text-align:center;'>Hệ thống hoạt động an toàn 100%. Không có cảnh báo lỗi.</td></tr>"

        html += f"""
            </tbody>
        </table>

        <div class="footer">
            <p>Báo cáo tự động được xuất từ Phần mềm GCS ROV Thương mại - Ngày xuất: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
    </div>
</body>
</html>
"""

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

        print(f"[ReportExporter] HTML Mission Survey Report exported: {output_path}")
        return output_path
