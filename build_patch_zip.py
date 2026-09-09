"""
build_patch_zip.py - Automated Delta Patch Packager for GCS ROV
================================================================
Tạo gói vá cập nhật nhẹ (1-2 MB) để gửi cho người dùng:
1. Gom toàn bộ mã nguồn cập nhật mới (WebRTC, AR HUD, Settings, Video Receiver, main.py).
2. Tạo file version.json với mã băm SHA256 để chống lỗi file.
3. Đóng gói vào Output/patches/patch_v1.1.0.zip.
4. Cập nhật file install_patch.bat để người dùng có thể click đúp cài đặt ngay.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import zipfile
from datetime import datetime

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATCHES_DIR = os.path.join(PROJECT_ROOT, "Output", "patches")
os.makedirs(OUTPUT_PATCHES_DIR, exist_ok=True)

# Phiên bản cập nhật mới
PATCH_VERSION = "1.1.0"
RELEASE_DATE = datetime.now().strftime("%Y-%m-%d")
CHANGELOG = (
    "1. Tích hợp Camera WebRTC siêu mượt (<80ms, 60 FPS) giải mã phần cứng GPU.\n"
    "2. Thêm luồng RTSP ngầm 12 FPS cho AI YOLOv8 khi bật AI Detection.\n"
    "3. Tích hợp kính ngắm AR HUD và Bounding Box neon trên màn hình WebRTC.\n"
    "4. Sửa cổng kết nối RTSP mặc định thành 8555/cam và WebRTC 8889/cam."
)

# Danh sách các tệp và thư mục đưa vào gói Patch
PATCH_FILES = [
    "main.py",
    os.path.join("network", "video_receiver.py"),
    os.path.join("network", "mavlink_worker.py"),
    os.path.join("network", "slam_udp_receiver.py"),
    os.path.join("GUI", "widgets", "webrtc_player_widget.py"),
    os.path.join("GUI", "widgets", "ar_hud_widget.py"),
    os.path.join("GUI", "widgets", "settings_dialog.py"),
    os.path.join("GUI", "widgets", "ai_vision_processor.py"),
    os.path.join("GUI", "widgets", "ai_control_panel.py"),
    os.path.join("core", "updater.py"),
]

def compute_sha256(file_path: str) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest().lower()

def format_size(bytes_val: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_val < 1024.0:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.1f} TB"

def build_patch():
    print("=" * 70)
    print(f"📦 BẮT ĐẦU ĐÓNG GÓI BẢN VÁ PATCH v{PATCH_VERSION}")
    print("=" * 70)

    zip_filename = f"patch_v{PATCH_VERSION}.zip"
    zip_path = os.path.join(OUTPUT_PATCHES_DIR, zip_filename)

    # 1. Nén các tệp cần thiết vào ZIP
    print("\n[Bước 1/4] Đang nén các tệp cập nhật vào file ZIP...")
    added_count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel_path in PATCH_FILES:
            full_path = os.path.join(PROJECT_ROOT, rel_path)
            if os.path.isfile(full_path):
                # Chuẩn hóa đường dẫn trong zip dùng forward slash
                arc_name = rel_path.replace("\\", "/")
                zf.write(full_path, arc_name)
                print(f"  + Thêm: {arc_name}")
                added_count += 1
            else:
                print(f"  ⚠️ Cảnh báo: Tệp không tồn tại: {rel_path}")

        # Tạo file version.json tạm thời bên trong zip
        inner_ver_data = {
            "version": PATCH_VERSION,
            "release_date": RELEASE_DATE,
            "changelog": CHANGELOG,
        }
        zf.writestr("version.json", json.dumps(inner_ver_data, indent=2, ensure_ascii=False))
        print("  + Thêm: version.json")

    file_size_bytes = os.path.getsize(zip_path)
    file_size_str = format_size(file_size_bytes)
    sha256_hash = compute_sha256(zip_path)

    print(f"\n[Bước 2/4] Đã nén thành công {added_count + 1} tệp.")
    print(f"  📁 Tệp xuất: {zip_path}")
    print(f"  ⚖️ Kích thước: {file_size_str} ({file_size_bytes:,} bytes)")
    print(f"  🔒 SHA256 : {sha256_hash}")

    # 2. Tạo version.json phục vụ Online Update (nếu đẩy lên server / github)
    print("\n[Bước 3/4] Cập nhật tệp version.json máy chủ...")
    server_ver_data = {
        "version": PATCH_VERSION,
        "release_date": RELEASE_DATE,
        "changelog": CHANGELOG,
        "update_type": "patch",
        "download_url": f"https://raw.githubusercontent.com/cncnexora/gcs-rov/main/patches/{zip_filename}",
        "file_size": file_size_str,
        "sha256": sha256_hash,
    }
    server_ver_path = os.path.join(OUTPUT_PATCHES_DIR, "version.json")
    with open(server_ver_path, "w", encoding="utf-8") as f:
        json.dump(server_ver_data, f, indent=2, ensure_ascii=False)
    print(f"  ✅ Đã lưu: {server_ver_path}")

    # 3. Tạo script click đúp install_patch.bat cho khách hàng
    print("\n[Bước 4/4] Cập nhật tệp cài đặt nhanh install_patch.bat...")
    bat_content = f"""@echo off
chcp 65001 >nul
echo =======================================================
echo    CNC NEXORA GCS - CẬP NHẬT BẢN VÁ v{PATCH_VERSION}
echo =======================================================
echo.
echo 1. Đang đóng ứng dụng GCS nếu đang mở...
taskkill /f /im GCS_ROV.exe >nul 2>&1
timeout /t 1 /nobreak >nul

set "TARGET_DIR=%LOCALAPPDATA%\\Programs\\CNC NExora GCS\\patches"
if not exist "%LOCALAPPDATA%\\Programs\\CNC NExora GCS" (
    set "TARGET_DIR=%~dp0patches"
)
mkdir "%TARGET_DIR%" 2>nul

echo 2. Đang nạp bản vá WebRTC Camera v{PATCH_VERSION}...
tar -xf "%~dp0{zip_filename}" -C "%TARGET_DIR%"

echo.
echo =======================================================
echo ✅ ĐÃ CẬP NHẬT HOÀN TẤT LÊN PHIÊN BẢN v{PATCH_VERSION}!
echo =======================================================
echo.
if exist "%LOCALAPPDATA%\\Programs\\CNC NExora GCS\\GCS_ROV.exe" (
    echo Đang khởi động lại phần mềm CNC NExora GCS...
    start "" "%LOCALAPPDATA%\\Programs\\CNC NExora GCS\\GCS_ROV.exe"
) else (
    echo Bạn có thể mở lại phần mềm GCS ngay bây giờ.
    pause
)
"""
    bat_path = os.path.join(OUTPUT_PATCHES_DIR, "install_patch.bat")
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)
    print(f"  ✅ Đã lưu: {bat_path}")

    print("\n" + "=" * 70)
    print(f"🎉 HOÀN THÀNH TẠO BẢN VÁ: {zip_filename} ({file_size_str})")
    print("=" * 70)
    print("👉 Bây giờ bạn chỉ cần gửi file này cho khách hàng:")
    print(f"   {zip_path}")
    print("👉 Khách mở GCS -> Cài đặt -> Tab Cập nhật -> Bấm 'Nạp file Patch (.zip)'")
    print("   hoặc giải nén cùng thư mục với install_patch.bat rồi click đúp!")
    print("=" * 70)

if __name__ == "__main__":
    build_patch()
