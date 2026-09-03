"""
core/licensing.py - Commercial Hardware-Locked Licensing & Activation Engine
=============================================================================
CNC NExora Technologies - Proprietary & Confidential
Manages software licensing, hardware fingerprinting, offline activation keys,
and commercial trial enforcement.
"""

from __future__ import annotations

import os
import sys
import json
import time
import uuid
import hmac
import base64
import hashlib
import platform
import subprocess
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any

from PyQt6 import QtCore, QtGui, QtWidgets


# ─────────────────────────────────────────────────────────────────────────────
# CRYPTOGRAPHIC CONSTANTS & SALTS
# ─────────────────────────────────────────────────────────────────────────────
MASTER_SECRET_KEY = b"CNC_NEXORA_SUBSEA_ROBOTICS_MASTER_KEY_2026_SECRET"
APP_DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "CNC_NExora")
LICENSE_FILE_PATH = os.path.join(APP_DATA_DIR, "license.lic")
TRIAL_DURATION_DAYS = 30


@dataclass
class LicenseInfo:
    is_valid: bool
    license_type: str        # 'COMMERCIAL_PERPETUAL', 'ENTERPRISE', 'TRIAL', 'EXPIRED', 'INVALID'
    customer_name: str
    machine_id: str
    expires_timestamp: float # 0.0 for perpetual
    status_message: str
    days_remaining: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# HARDWARE FINGERPRINTING
# ─────────────────────────────────────────────────────────────────────────────
def get_machine_fingerprint() -> str:
    """
    Tạo mã nhận diện phần cứng máy tính (Machine ID) duy nhất và bảo mật.
    Kết hợp: Windows MachineGuid, CPU Processor ID, và Network MAC Node.
    """
    raw_components = []
    
    # 1. Windows MachineGuid
    if platform.system() == "Windows":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            winreg.CloseKey(key)
            if guid:
                raw_components.append(str(guid).strip())
        except Exception:
            pass

    # 2. CPU / Platform identifiers
    raw_components.append(platform.processor() or "UNKNOWN_PROC")
    raw_components.append(platform.machine() or "UNKNOWN_ARCH")
    raw_components.append(str(uuid.getnode()))  # MAC Address integer
    
    # Combine and hash
    combined = "|".join(raw_components)
    digest = hashlib.sha256(combined.encode("utf-8")).hexdigest().upper()
    
    # Format into user-friendly chunks: NEX-XXXX-XXXX-XXXX
    return f"NEX-{digest[0:4]}-{digest[4:8]}-{digest[8:12]}"


# ─────────────────────────────────────────────────────────────────────────────
# KEY GENERATOR & SIGNING (Core Crypto)
# ─────────────────────────────────────────────────────────────────────────────
def generate_license_key(machine_id: str, customer_name: str = "Client", license_type: str = "PERPETUAL", duration_days: int = 0) -> str:
    """
    Tạo License Key hợp lệ cho 1 Machine ID cụ thể.
    Cấu trúc: NEXOS-[TYPE]-[EXP_DAYS]-[CUSTOMER_HASH]-[HMAC_SIGNATURE]
    """
    m_clean = machine_id.strip().upper()
    cust_clean = customer_name.strip()
    
    exp_ts = 0.0
    if duration_days > 0:
        exp_ts = time.time() + (duration_days * 86400)
    
    payload = {
        "m": m_clean,
        "c": cust_clean,
        "t": license_type,
        "e": int(exp_ts)
    }
    
    payload_json = json.dumps(payload, sort_keys=True)
    signature = hmac.new(MASTER_SECRET_KEY, payload_json.encode("utf-8"), hashlib.sha256).hexdigest().upper()[:8]
    
    # Encoded compact string
    b64_payload = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("utf-8").rstrip("=")
    key_str = f"NEXOS-{b64_payload}-{signature}"
    return key_str


def verify_license_key(key_str: str, current_machine_id: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """
    Xác thực tính hợp lệ của License Key.
    """
    if not key_str or not key_str.startswith("NEXOS-"):
        return False, None, "Định dạng License Key không hợp lệ."
    
    parts = key_str.split("-")
    if len(parts) < 3:
        return False, None, "Cấu trúc License Key bị lỗi."
    
    b64_payload = parts[1]
    sig_provided = parts[2]
    
    # Add back padding if needed
    pad_len = 4 - (len(b64_payload) % 4)
    if pad_len != 4:
        b64_payload += "=" * pad_len
        
    try:
        payload_json = base64.urlsafe_b64decode(b64_payload.encode("utf-8")).decode("utf-8")
        payload = json.loads(payload_json)
    except Exception:
        return False, None, "Mã kích hoạt bị hỏng hoặc đã bị chỉnh sửa."
    
    # Verify HMAC signature
    expected_sig = hmac.new(MASTER_SECRET_KEY, payload_json.encode("utf-8"), hashlib.sha256).hexdigest().upper()[:8]
    if sig_provided != expected_sig:
        return False, None, "Chữ ký mật mã không hợp lệ. Key giả mạo."
    
    # Verify Machine ID lock (Allow ANY for universal master keys)
    key_machine = payload.get("m", "")
    if key_machine != "ANY" and key_machine != current_machine_id.strip().upper():
        return False, None, f"License Key này dành cho máy khác ({key_machine}), không khớp với máy hiện tại ({current_machine_id})."
    
    # Verify Expiration
    exp_ts = payload.get("e", 0)
    if exp_ts > 0 and time.time() > exp_ts:
        return False, payload, "License Key đã hết hạn sử dụng."
    
    return True, payload, "Bản quyền hợp lệ và đã được kích hoạt thành công."


# ─────────────────────────────────────────────────────────────────────────────
# LICENSE MANAGER
# ─────────────────────────────────────────────────────────────────────────────
class LicenseManager:
    """Singleton quản lý trạng thái bản quyền của phần mềm."""
    
    _instance: Optional[LicenseManager] = None
    
    @classmethod
    def get_instance(cls) -> LicenseManager:
        if cls._instance is None:
            cls._instance = LicenseManager()
        return cls._instance

    def __init__(self):
        self.machine_id = get_machine_fingerprint()
        os.makedirs(APP_DATA_DIR, exist_ok=True)
        self._cached_info: Optional[LicenseInfo] = None

    def get_license_info(self) -> LicenseInfo:
        """Kiểm tra và trả về thông tin bản quyền hiện tại."""
        if not os.path.exists(LICENSE_FILE_PATH):
            return self._handle_trial_mode()
        
        try:
            with open(LICENSE_FILE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            key = data.get("key", "")
            is_valid, payload, msg = verify_license_key(key, self.machine_id)
            
            if is_valid and payload:
                exp_ts = payload.get("e", 0)
                days_rem = 9999
                if exp_ts > 0:
                    days_rem = max(0, int((exp_ts - time.time()) / 86400))
                
                return LicenseInfo(
                    is_valid=True,
                    license_type=payload.get("t", "COMMERCIAL_PERPETUAL"),
                    customer_name=payload.get("c", "Valued Customer"),
                    machine_id=self.machine_id,
                    expires_timestamp=float(exp_ts),
                    status_message="Bản quyền thương mại chính hãng đã kích hoạt.",
                    days_remaining=days_rem
                )
            else:
                return LicenseInfo(
                    is_valid=False,
                    license_type="INVALID",
                    customer_name="Unknown",
                    machine_id=self.machine_id,
                    expires_timestamp=0.0,
                    status_message=msg,
                    days_remaining=0
                )
        except Exception as e:
            return self._handle_trial_mode()

    def _handle_trial_mode(self) -> LicenseInfo:
        """Khởi tạo hoặc kiểm tra chế độ dùng thử thương mại (Commercial Trial)."""
        trial_file = os.path.join(APP_DATA_DIR, ".trial.dat")
        now = time.time()
        
        if not os.path.exists(trial_file):
            # First launch -> Create trial
            trial_data = {"init": now, "machine": self.machine_id}
            try:
                with open(trial_file, "w", encoding="utf-8") as f:
                    json.dump(trial_data, f)
            except Exception:
                pass
            init_time = now
        else:
            try:
                with open(trial_file, "r", encoding="utf-8") as f:
                    d = json.load(f)
                init_time = float(d.get("init", now))
            except Exception:
                init_time = now

        elapsed_days = (now - init_time) / 86400.0
        remaining_days = max(0, int(TRIAL_DURATION_DAYS - elapsed_days))
        
        if elapsed_days <= TRIAL_DURATION_DAYS:
            return LicenseInfo(
                is_valid=True,
                license_type="TRIAL",
                customer_name="Commercial Evaluation User",
                machine_id=self.machine_id,
                expires_timestamp=init_time + (TRIAL_DURATION_DAYS * 86400),
                status_message=f"Đang sử dụng bản Dùng Thử Thương Mại ({remaining_days} ngày còn lại).",
                days_remaining=remaining_days
            )
        else:
            return LicenseInfo(
                is_valid=False,
                license_type="EXPIRED",
                customer_name="Commercial Evaluation User",
                machine_id=self.machine_id,
                expires_timestamp=init_time + (TRIAL_DURATION_DAYS * 86400),
                status_message="Thời gian dùng thử 30 ngày đã hết hạn. Vui lòng kích hoạt bản quyền chính thức.",
                days_remaining=0
            )

    def activate_key(self, key_str: str) -> Tuple[bool, str]:
        """Kích hoạt và lưu License Key vào hệ thống."""
        is_valid, payload, msg = verify_license_key(key_str, self.machine_id)
        if not is_valid:
            return False, msg
        
        try:
            with open(LICENSE_FILE_PATH, "w", encoding="utf-8") as f:
                json.dump({
                    "key": key_str.strip(),
                    "activated_at": time.time(),
                    "machine_id": self.machine_id,
                    "customer": payload.get("c", ""),
                    "type": payload.get("t", "")
                }, f, indent=2)
            self._cached_info = None
            return True, "Kích hoạt bản quyền thương mại thành công! Cảm ơn bạn đã lựa chọn CNC NExora."
        except Exception as e:
            return False, f"Không thể ghi tệp bản quyền: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# LICENSE DIALOG (PyQt6 Cyber Dark UI)
# ─────────────────────────────────────────────────────────────────────────────
class LicenseDialog(QtWidgets.QDialog):
    """Hộp thoại quản lý và kích hoạt bản quyền phần mềm GCS."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("QUẢN LÝ BẢN QUYỀN - CNC NEXORA GCS")
        self.setFixedSize(540, 420)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        self.mgr = LicenseManager.get_instance()
        self._init_ui()
        self._refresh_status()

    def _init_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #060C17;
                color: #DDE6F0;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLabel {
                color: #A0B2C6;
            }
            QLineEdit {
                background-color: #0B1626;
                border: 1px solid #1E385B;
                border-radius: 6px;
                padding: 10px 12px;
                color: #00F0FF;
                font-family: 'Consolas', monospace;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #00A8FF;
                background-color: #0E1D33;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0052D4, stop:0.5 #4364F7, stop:1 #6FB1FC);
                color: #FFFFFF;
                font-weight: bold;
                border-radius: 6px;
                padding: 10px 18px;
                font-size: 13px;
                border: none;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0066FF, stop:0.5 #5777F9, stop:1 #82BDFF);
            }
            QPushButton#btnCopy {
                background: #112238;
                border: 1px solid #1E385B;
                color: #00A8FF;
                padding: 8px 12px;
                font-size: 11px;
            }
            QPushButton#btnCopy:hover {
                background: #1A3354;
                border-color: #00A8FF;
            }
            QFrame#cardFrame {
                background-color: #0A1322;
                border: 1px solid #162B47;
                border-radius: 8px;
                padding: 12px;
            }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        # Header
        header = QtWidgets.QHBoxLayout()
        icon_lbl = QtWidgets.QLabel("🛡️")
        icon_lbl.setStyleSheet("font-size: 26px;")
        title_box = QtWidgets.QVBoxLayout()
        title = QtWidgets.QLabel("CNC NEXORA GCS COMMERCIAL LICENSE")
        title.setStyleSheet("color: #00F0FF; font-size: 15px; font-weight: bold; letter-spacing: 1px;")
        subtitle = QtWidgets.QLabel("Hệ thống xác thực bản quyền phần mềm robot lặn ngầm")
        subtitle.setStyleSheet("color: #6C829D; font-size: 11px;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addWidget(icon_lbl)
        header.addLayout(title_box)
        header.addStretch()
        layout.addLayout(header)

        # Info Card
        card = QtWidgets.QFrame()
        card.setObjectName("cardFrame")
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setSpacing(8)

        # Status row
        status_row = QtWidgets.QHBoxLayout()
        status_row.addWidget(QtWidgets.QLabel("Trạng thái bản quyền:"))
        self.lbl_status_badge = QtWidgets.QLabel("ĐANG KIỂM TRA...")
        self.lbl_status_badge.setStyleSheet("font-weight: bold; padding: 3px 8px; border-radius: 4px;")
        status_row.addWidget(self.lbl_status_badge)
        status_row.addStretch()
        card_layout.addLayout(status_row)

        self.lbl_cust = QtWidgets.QLabel("Chủ sở hữu: —")
        self.lbl_exp = QtWidgets.QLabel("Hạn dùng: —")
        card_layout.addWidget(self.lbl_cust)
        card_layout.addWidget(self.lbl_exp)

        # Machine ID row
        mid_row = QtWidgets.QHBoxLayout()
        mid_row.addWidget(QtWidgets.QLabel("Mã phần cứng (Machine ID):"))
        self.txt_mid = QtWidgets.QLabel(self.mgr.machine_id)
        self.txt_mid.setStyleSheet("color: #00F0FF; font-family: 'Consolas'; font-weight: bold; font-size: 13px;")
        mid_row.addWidget(self.txt_mid)
        mid_row.addStretch()
        
        btn_copy = QtWidgets.QPushButton("📋 Sao chép")
        btn_copy.setObjectName("btnCopy")
        btn_copy.clicked.connect(self._copy_mid)
        mid_row.addWidget(btn_copy)
        card_layout.addLayout(mid_row)

        layout.addWidget(card)

        # Activation Form
        lbl_input = QtWidgets.QLabel("Nhập License Key kích hoạt (NEXOS-XXXX-...):")
        lbl_input.setStyleSheet("color: #DDE6F0; font-size: 12px; font-weight: bold;")
        layout.addWidget(lbl_input)

        self.edit_key = QtWidgets.QLineEdit()
        self.edit_key.setPlaceholderText("Dán mã kích hoạt được cấp vào đây...")
        layout.addWidget(self.edit_key)

        # Button row
        btn_row = QtWidgets.QHBoxLayout()
        btn_activate = QtWidgets.QPushButton("🚀 Kích Hoạt Bản Quyền")
        btn_activate.clicked.connect(self._do_activate)
        btn_row.addWidget(btn_activate)

        btn_close = QtWidgets.QPushButton("Đóng")
        btn_close.setObjectName("btnCopy")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _refresh_status(self):
        info = self.mgr.get_license_info()
        self.lbl_cust.setText(f"Chủ sở hữu: <b>{info.customer_name}</b>")
        
        if info.expires_timestamp == 0.0:
            exp_str = "Vĩnh viễn (Perpetual Commercial License)"
        else:
            exp_str = time.strftime('%d/%m/%Y %H:%M', time.localtime(info.expires_timestamp))
            if info.days_remaining > 0:
                exp_str += f" ({info.days_remaining} ngày còn lại)"
        self.lbl_exp.setText(f"Thời hạn: <b>{exp_str}</b>")

        if info.license_type in ("COMMERCIAL_PERPETUAL", "ENTERPRISE", "PERPETUAL") and info.is_valid:
            self.lbl_status_badge.setText("✅ ĐÃ KÍCH HOẠT CHÍNH THỨC")
            self.lbl_status_badge.setStyleSheet("color: #00FF88; background-color: #0B331E; font-weight: bold;")
        elif info.license_type == "TRIAL" and info.is_valid:
            self.lbl_status_badge.setText(f"⏳ BẢN DÙNG THỬ ({info.days_remaining} NGÀY)")
            self.lbl_status_badge.setStyleSheet("color: #FFB800; background-color: #33260A; font-weight: bold;")
        else:
            self.lbl_status_badge.setText("❌ CHƯA KÍCH HOẠT / HẾT HẠN")
            self.lbl_status_badge.setStyleSheet("color: #FF4444; background-color: #330B0B; font-weight: bold;")

    def _copy_mid(self):
        QtWidgets.QApplication.clipboard().setText(self.mgr.machine_id)
        QtWidgets.QMessageBox.information(self, "Đã sao chép", "Đã sao chép Machine ID vào bộ nhớ tạm!\nHãy gửi mã này cho nhà sản xuất để nhận License Key.")

    def _do_activate(self):
        key = self.edit_key.text().strip()
        if not key:
            QtWidgets.QMessageBox.warning(self, "Lỗi", "Vui lòng nhập License Key trước khi bấm kích hoạt.")
            return
        
        success, msg = self.mgr.activate_key(key)
        if success:
            QtWidgets.QMessageBox.information(self, "Thành Công", msg)
            self._refresh_status()
            self.edit_key.clear()
        else:
            QtWidgets.QMessageBox.critical(self, "Kích Hoạt Thất Bại", msg)