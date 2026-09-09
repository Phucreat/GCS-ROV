"""
core/updater.py - Hybrid In-App Auto-Updater & Offline Delta Patch Engine
========================================================================
Quản lý cập nhật ứng dụng chuyên nghiệp cho CNC NExora GCS:
1. Online OTA: Kiểm tra phiên bản mới từ GitHub Releases / Server Web,
   tải bản vá nhẹ (patch .zip 1-2MB) và tự động cập nhật không cần cài lại 460MB.
2. Offline Patch: Nạp trực tiếp file patch .zip qua USB/Zalo, giải nén vào
   thư mục patches/ để ghi đè code mới ngay lập tức.
3. Patch Loader Hook: Tự động đưa thư mục patches/ lên ưu tiên cao nhất trong
   sys.meta_path để code mới luôn được nạp đè lên gói PYZ đóng băng.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from typing import Optional

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS & CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

CURRENT_VERSION = "1.0.0"
APP_DISPLAY_NAME = "CNC NExora GCS"

# URL mặc định kiểm tra cập nhật (có thể cấu hình trỏ sang GitHub Releases hoặc Server riêng)
DEFAULT_UPDATE_CHECK_URL = (
    "https://raw.githubusercontent.com/cncnexora/gcs-rov/main/version.json"
)


def get_app_dir() -> str:
    """Trả về thư mục gốc chứa file thực thi của ứng dụng."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_patches_dir() -> str:
    """Trả về đường dẫn thư mục patches/."""
    pdir = os.path.join(get_app_dir(), "patches")
    os.makedirs(pdir, exist_ok=True)
    return pdir


def get_active_version() -> str:
    """
    Trả về phiên bản hiện tại đang chạy.
    Nếu có patch trong patches/version.json thì ưu tiên lấy phiên bản của patch.
    """
    patch_ver_file = os.path.join(get_patches_dir(), "version.json")
    if os.path.isfile(patch_ver_file):
        try:
            with open(patch_ver_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("version", CURRENT_VERSION)
        except Exception:
            pass
    return CURRENT_VERSION


def compare_versions(ver_a: str, ver_b: str) -> int:
    """
    So sánh 2 chuỗi phiên bản dạng semver (ví dụ: '1.0.1' vs '1.0.0').
    Trả về:
      1 nếu ver_a > ver_b
      -1 nếu ver_a < ver_b
      0 nếu ver_a == ver_b
    """
    def _parse(v: str):
        v = v.lstrip("vV").strip()
        parts = []
        for token in v.split("."):
            num = ""
            for ch in token:
                if ch.isdigit():
                    num += ch
                else:
                    break
            parts.append(int(num) if num else 0)
        while len(parts) < 3:
            parts.append(0)
        return parts[:3]

    pa = _parse(ver_a)
    pb = _parse(ver_b)
    if pa > pb:
        return 1
    elif pa < pb:
        return -1
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class UpdateInfo:
    version: str
    release_date: str
    changelog: str
    download_url: str
    file_size: str
    update_type: str = "patch"   # "patch" hoặc "installer"
    sha256: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# BACKGROUND WORKERS
# ─────────────────────────────────────────────────────────────────────────────

class UpdateCheckerWorker(QThread):
    """Worker kiểm tra phiên bản mới từ máy chủ bất đồng bộ (không đơ GUI)."""
    sig_update_available = pyqtSignal(object)  # UpdateInfo
    sig_up_to_date = pyqtSignal(str)          # current_version
    sig_check_failed = pyqtSignal(str)        # error_message

    def __init__(self, check_url: str = DEFAULT_UPDATE_CHECK_URL, parent=None):
        super().__init__(parent)
        self.check_url = check_url

    def run(self):
        try:
            req = urllib.request.Request(
                self.check_url,
                headers={"User-Agent": f"{APP_DISPLAY_NAME}-Updater/{CURRENT_VERSION}"}
            )
            with urllib.request.urlopen(req, timeout=6.0) as resp:
                if resp.status != 200:
                    self.sig_check_failed.emit(f"HTTP Error {resp.status}")
                    return
                raw_data = resp.read().decode("utf-8")
                data = json.loads(raw_data)

            remote_ver = data.get("version", "").strip()
            if not remote_ver:
                self.sig_check_failed.emit("Dữ liệu phiên bản máy chủ không hợp lệ.")
                return

            local_ver = get_active_version()
            if compare_versions(remote_ver, local_ver) > 0:
                info = UpdateInfo(
                    version=remote_ver,
                    release_date=data.get("release_date", "Hôm nay"),
                    changelog=data.get("changelog", "Bản vá nâng cấp hệ thống."),
                    download_url=data.get("download_url", ""),
                    file_size=data.get("file_size", "2 MB"),
                    update_type=data.get("update_type", "patch"),
                    sha256=data.get("sha256", "")
                )
                self.sig_update_available.emit(info)
            else:
                self.sig_up_to_date.emit(local_ver)

        except Exception as exc:
            self.sig_check_failed.emit(str(exc))


class UpdateDownloaderWorker(QThread):
    """Worker tải gói cập nhật kèm theo tiến trình phần trăm (%)."""
    sig_progress = pyqtSignal(int, int, float)  # downloaded_bytes, total_bytes, percent
    sig_finished = pyqtSignal(str)              # local_saved_path
    sig_failed = pyqtSignal(str)                # error_message

    def __init__(self, download_url: str, save_filename: str = "patch_download.zip", parent=None):
        super().__init__(parent)
        self.download_url = download_url
        self.save_filename = save_filename
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        temp_dir = tempfile.gettempdir()
        save_path = os.path.join(temp_dir, self.save_filename)

        try:
            req = urllib.request.Request(
                self.download_url,
                headers={"User-Agent": "CNC-NExora-Updater"}
            )
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                total_size = int(resp.headers.get("content-length", 0))
                downloaded = 0
                chunk_size = 64 * 1024  # 64 KB chunks

                with open(save_path, "wb") as f_out:
                    while not self._is_cancelled:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f_out.write(chunk)
                        downloaded += len(chunk)
                        pct = (downloaded / total_size * 100.0) if total_size > 0 else 50.0
                        self.sig_progress.emit(downloaded, total_size, pct)

            if self._is_cancelled:
                if os.path.exists(save_path):
                    os.remove(save_path)
                self.sig_failed.emit("Đã hủy quá trình tải bản cập nhật.")
                return

            self.sig_finished.emit(save_path)

        except Exception as exc:
            self.sig_failed.emit(f"Lỗi tải bản cập nhật: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# PATCH APPLICATION LOGIC
# ─────────────────────────────────────────────────────────────────────────────

def apply_offline_patch(zip_file_path: str, restart_after: bool = True) -> tuple[bool, str]:
    """
    Giải nén bản vá (.zip) vào thư mục patches/ và tạo script khởi động lại.
    Trả về: (success: bool, message: str)
    """
    if not os.path.isfile(zip_file_path):
        return False, f"Tệp bản vá không tồn tại: {zip_file_path}"

    target_patch_dir = get_patches_dir()

    try:
        # Kiểm tra tính hợp lệ của file zip
        with zipfile.ZipFile(zip_file_path, "r") as zf:
            namelist = zf.namelist()
            if not namelist:
                return False, "Tệp zip rỗng, không chứa dữ liệu cập nhật."
            
            # Giải nén trực tiếp vào thư mục patches/
            zf.extractall(target_patch_dir)

        # Đọc thông tin version mới nếu có
        patch_ver = "mới"
        pver_path = os.path.join(target_patch_dir, "version.json")
        if os.path.isfile(pver_path):
            try:
                with open(pver_path, "r", encoding="utf-8") as f:
                    patch_ver = json.load(f).get("version", "mới")
            except Exception:
                pass

        if restart_after:
            _launch_restart_script(app_exe_path=sys.executable)

        return True, f"Đã nạp thành công bản vá phiên bản v{patch_ver}!"

    except Exception as exc:
        return False, f"Lỗi giải nén bản vá: {exc}"


def _launch_restart_script(app_exe_path: str):
    """
    Tạo và khởi chạy script batch ngầm để tắt ứng dụng hiện tại,
    chờ đóng hẳn và mở lại ứng dụng với code mới.
    """
    is_frozen = getattr(sys, "frozen", False)
    bat_path = os.path.join(tempfile.gettempdir(), "nexora_gcs_restart.bat")
    
    if is_frozen:
        exe_name = os.path.basename(app_exe_path)
        bat_content = f"""@echo off
timeout /t 1 /nobreak >nul
taskkill /f /im "{exe_name}" >nul 2>&1
timeout /t 1 /nobreak >nul
start "" "{app_exe_path}"
del "%~f0"
"""
    else:
        # Khi đang debug trong môi trường Python source
        main_py = os.path.join(get_app_dir(), "main.py")
        bat_content = f"""@echo off
timeout /t 1 /nobreak >nul
start "" "{sys.executable}" "{main_py}"
del "%~f0"
"""

    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)

    # Chạy script batch ẩn nền
    subprocess.Popen(
        ["cmd.exe", "/c", bat_path],
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        close_fds=True
    )

    # Thoát ứng dụng hiện tại để batch restart
    QtCore.QTimer.singleShot(200, lambda: QtWidgets.QApplication.quit())


# ─────────────────────────────────────────────────────────────────────────────
# UI DIALOGS
# ─────────────────────────────────────────────────────────────────────────────

class UpdateDialog(QDialog):
    """Hộp thoại hiển thị thông tin bản cập nhật mới và tải về trực tiếp."""

    def __init__(self, update_info: UpdateInfo, parent=None):
        super().__init__(parent)
        self.info = update_info
        self.downloader: Optional[UpdateDownloaderWorker] = None

        self.setWindowTitle(f"🚀 Cập Nhật Phần Mềm — {APP_DISPLAY_NAME}")
        self.resize(520, 420)
        self.setModal(True)

        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet("""
            QDialog {
                background: #070E18;
                color: #C2D6EC;
                font-family: 'Segoe UI', sans-serif;
            }
            QLabel {
                color: #C2D6EC;
            }
            QTextEdit {
                background: #0A1424;
                border: 1px solid #1D3554;
                border-radius: 6px;
                color: #A5C2E0;
                font-family: 'Consolas', 'Segoe UI', monospace;
                font-size: 11px;
                padding: 6px;
            }
            QProgressBar {
                background: #0A1424;
                border: 1px solid #1D3554;
                border-radius: 6px;
                text-align: center;
                color: #FFFFFF;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00FF9D, stop:1 #00E5FF);
                border-radius: 5px;
            }
            QPushButton {
                padding: 7px 18px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 11px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header Title
        lbl_title = QLabel(f"🎉 ĐÃ CÓ BẢN CẬP NHẬT MỚI: v{self.info.version}")
        lbl_title.setStyleSheet("color:#00FF9D; font-size:15px; font-weight:bold;")
        layout.addWidget(lbl_title)

        # Info details
        cur_ver = get_active_version()
        lbl_sub = QLabel(
            f"Phiên bản hiện tại: <b>v{cur_ver}</b> ➔ Bản mới nhất: <b>v{self.info.version}</b><br>"
            f"Ngày phát hành: <i>{self.info.release_date}</i> | Kích thước: <b>{self.info.file_size}</b>"
        )
        lbl_sub.setStyleSheet("color:#7B9BBF; font-size:11px;")
        layout.addWidget(lbl_sub)

        # Changelog
        lbl_cl = QLabel("Nhật ký cập nhật (Changelog):")
        lbl_cl.setStyleSheet("color:#00E5FF; font-weight:bold; font-size:11px;")
        layout.addWidget(lbl_cl)

        self.txt_changelog = QTextEdit()
        self.txt_changelog.setReadOnly(True)
        self.txt_changelog.setPlainText(self.info.changelog)
        layout.addWidget(self.txt_changelog, stretch=1)

        # Progress bar (mặc định ẩn)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color:#FFC800; font-size:10px;")
        self.lbl_status.setVisible(False)
        layout.addWidget(self.lbl_status)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Để sau")
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background: #0E1B2E;
                color: #8AACCB;
                border: 1px solid #1D3554;
            }
            QPushButton:hover {
                background: #152740;
                color: #FFFFFF;
            }
        """)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_update = QPushButton("⚡ Cập Nhật Ngay")
        self.btn_update.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0C3322, stop:1 #072015);
                color: #00FF9D;
                border: 1px solid #00FF9D;
            }
            QPushButton:hover {
                background: #00FF9D;
                color: #060B14;
            }
        """)
        self.btn_update.clicked.connect(self._start_download)
        btn_layout.addWidget(self.btn_update)

        layout.addLayout(btn_layout)

    def _start_download(self):
        if not self.info.download_url:
            QMessageBox.warning(self, "Lỗi", "Không tìm thấy đường dẫn tải về của bản cập nhật.")
            return

        self.btn_update.setEnabled(False)
        self.btn_cancel.setText("Hủy")
        self.progress_bar.setVisible(True)
        self.lbl_status.setVisible(True)
        self.lbl_status.setText("Đang tải gói bản vá siêu nhẹ...")

        self.downloader = UpdateDownloaderWorker(
            download_url=self.info.download_url,
            save_filename=f"patch_v{self.info.version}.zip",
            parent=self
        )
        self.downloader.sig_progress.connect(self._on_download_progress)
        self.downloader.sig_finished.connect(self._on_download_finished)
        self.downloader.sig_failed.connect(self._on_download_failed)
        self.downloader.start()

    def _on_download_progress(self, downloaded: int, total: int, pct: float):
        self.progress_bar.setValue(int(pct))
        mb_down = downloaded / (1024 * 1024)
        mb_tot = total / (1024 * 1024)
        self.lbl_status.setText(f"Đang tải: {mb_down:.1f} MB / {mb_tot:.1f} MB ({pct:.0f}%)")

    def _on_download_finished(self, saved_path: str):
        self.lbl_status.setText("Tải hoàn tất! Đang tiến hành áp dụng bản vá...")
        self.progress_bar.setValue(100)

        # Áp dụng bản vá
        ok, msg = apply_offline_patch(saved_path, restart_after=True)
        if ok:
            QMessageBox.information(
                self,
                "Cập Nhật Hoàn Tất",
                "Đã cài đặt bản vá thành công!\nỨng dụng sẽ tự động khởi động lại sau giây lát."
            )
            self.accept()
        else:
            QMessageBox.critical(self, "Lỗi Nạp Bản Vá", msg)
            self.btn_update.setEnabled(True)

    def _on_download_failed(self, err_msg: str):
        self.lbl_status.setText("Tải bản vá thất bại.")
        QMessageBox.critical(self, "Lỗi Tải Về", err_msg)
        self.btn_update.setEnabled(True)
        self.btn_cancel.setText("Đóng")


# ─────────────────────────────────────────────────────────────────────────────
# CONVENIENCE CONTROLLER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def check_for_updates_interactive(parent_widget=None, check_url: str = DEFAULT_UPDATE_CHECK_URL):
    """
    Gọi kiểm tra cập nhật khi người dùng chủ động bấm nút trong Settings.
    Hiển thị thông báo ngay cả khi đã là bản mới nhất hoặc có lỗi mạng.
    """
    checker = UpdateCheckerWorker(check_url=check_url, parent=parent_widget)

    # Tạo progress dialog nhỏ để phi công biết hệ thống đang kết nối mạng
    progress = QtWidgets.QProgressDialog(
        "Đang kết nối tới máy chủ kiểm tra phiên bản mới...",
        None, 0, 0, parent_widget
    )
    progress.setWindowTitle("Kiểm Tra Cập Nhật")
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.show()

    def _on_update(info: UpdateInfo):
        progress.close()
        dlg = UpdateDialog(info, parent=parent_widget)
        dlg.exec()

    def _on_latest(ver: str):
        progress.close()
        QMessageBox.information(
            parent_widget,
            "Phiên Bản Mới Nhất",
            f"Bạn đang sử dụng phiên bản mới nhất: v{ver}!\nKhông có bản cập nhật nào."
        )

    def _on_err(msg: str):
        progress.close()
        QMessageBox.warning(
            parent_widget,
            "Không Thể Kiểm Tra Cập Nhật",
            f"Không thể kết nối đến máy chủ cập nhật:\n{msg}\n\n"
            "Vui lòng kiểm tra lại kết nối mạng Internet hoặc sử dụng chức năng nạp bản vá Offline."
        )

    checker.sig_update_available.connect(_on_update)
    checker.sig_up_to_date.connect(_on_latest)
    checker.sig_check_failed.connect(_on_err)
    checker.start()

    # Giữ reference để không bị GC thu hồi
    if parent_widget:
        parent_widget._active_update_checker = checker


def install_offline_patch_interactive(parent_widget=None) -> bool:
    """
    Mở hộp thoại chọn file zip bản vá từ máy tính (USB/Zalo) và áp dụng ngay.
    """
    file_path, _ = QFileDialog.getOpenFileName(
        parent_widget,
        "Chọn Tệp Bản Vá Delta Patch (.zip)",
        "",
        "Patch Packages (*.zip);;All Files (*)"
    )
    if not file_path:
        return False

    reply = QMessageBox.question(
        parent_widget,
        "Xác Nhận Cài Đặt Bản Vá",
        f"Bạn có chắc chắn muốn nạp bản vá từ tệp:\n{os.path.basename(file_path)}?\n\n"
        "Ứng dụng sẽ tự động giải nén và khởi động lại sau khi hoàn tất.",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes
    )

    if reply != QMessageBox.StandardButton.Yes:
        return False

    ok, msg = apply_offline_patch(file_path, restart_after=True)
    if ok:
        QMessageBox.information(
            parent_widget,
            "Thành Công",
            f"{msg}\nPhần mềm sẽ tự khởi động lại ngay bây giờ."
        )
        return True
    else:
        QMessageBox.critical(parent_widget, "Lỗi Nạp Bản Vá", msg)
        return False
