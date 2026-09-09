# -*- coding: utf-8 -*-
"""
tools/build_patch_package.py
Đóng gói bản cập nhật nâng cấp v1.1.0 cho khách hàng:
Bao gồm:
1. GCS_ROV.exe (đã tích hợp WebRTC mặc định + Patch Loader Hook + loại bỏ Webcam/Video File)
2. _internal/GUI/widgets/webrtc_player_widget.py
3. _internal/GUI/widgets/settings_dialog.py
4. _internal/GUI/widgets/ar_hud_widget.py
5. _internal/network/video_receiver.py
6. install_patch.bat (Tự động nhận diện thư mục cài đặt thực tế của khách hàng)
7. HUONG_DAN_CAP_NHAT_PHAN_MEM_GCS.pdf (Sổ tay hướng dẫn trực quan)
"""
import os
import sys
import zipfile
import shutil
import json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST_DIR = os.path.join(PROJECT_ROOT, "dist", "GCS_ROV")
PATCHES_OUTPUT_DIR = os.path.join(PROJECT_ROOT, "Output", "patches")
os.makedirs(PATCHES_OUTPUT_DIR, exist_ok=True)

# 1. Tạo file install_patch.bat thông minh
bat_script = r"""@echo off
chcp 65001 >nul
echo ================================================================
echo      CNC NEXORA GCS - CẬP NHẬT PHIÊN BẢN v1.1.0 (WebRTC 60FPS)
echo ================================================================
echo.
echo [1/4] Đang đóng ứng dụng CNC NExora GCS nếu đang mở...
taskkill /f /im GCS_ROV.exe >nul 2>&1
timeout /t 1 /nobreak >nul

set "APP_DIR="

:: 1. Kiểm tra nếu file .bat chạy ngay trong thư mục cài đặt
if exist "%~dp0GCS_ROV.exe" (
    if exist "%~dp0_internal" set "APP_DIR=%~dp0"
)

:: 2. Kiểm tra nếu file .bat nằm trong thư mục con giải nén (ví dụ patch\)
if not defined APP_DIR (
    if exist "%~dp0..\GCS_ROV.exe" (
        if exist "%~dp0..\_internal" set "APP_DIR=%~dp0..\"
    )
)

:: 3. Kiểm tra Registry Inno Setup
if not defined APP_DIR (
    for /f "tokens=2*" %%A in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\{8B49B0E1-831C-4B9A-99F2-4F17A91D3C08}_is1" /v "InstallLocation" 2^>nul') do (
        if exist "%%B\GCS_ROV.exe" set "APP_DIR=%%B\"
    )
)

:: 4. Kiểm tra LocalAppData Programs mặc định
if not defined APP_DIR (
    if exist "%LOCALAPPDATA%\Programs\CNC NExora GCS\GCS_ROV.exe" (
        set "APP_DIR=%LOCALAPPDATA%\Programs\CNC NExora GCS\"
    )
)

:: 5. Kiểm tra Program Files
if not defined APP_DIR (
    if exist "C:\Program Files\CNC NExora GCS\GCS_ROV.exe" (
        set "APP_DIR=C:\Program Files\CNC NExora GCS\"
    )
    if exist "C:\Program Files (x86)\CNC NExora GCS\GCS_ROV.exe" (
        set "APP_DIR=C:\Program Files (x86)\CNC NExora GCS\"
    )
)

:: 6. Kiểm tra các ổ đĩa tùy biến (như \rov\CNC NExora GCS trong hình khách hàng)
if not defined APP_DIR (
    if exist "C:\rov\CNC NExora GCS\GCS_ROV.exe" set "APP_DIR=C:\rov\CNC NExora GCS\"
    if exist "D:\rov\CNC NExora GCS\GCS_ROV.exe" set "APP_DIR=D:\rov\CNC NExora GCS\"
    if exist "E:\rov\CNC NExora GCS\GCS_ROV.exe" set "APP_DIR=E:\rov\CNC NExora GCS\"
)

if not defined APP_DIR (
    echo [CANH BAO] Khong tu dong tim thay thu muc cai dat phan mem.
    echo Vui long nhap hoac dan duong dan thu muc cai dat cua ban (noi co file GCS_ROV.exe):
    set /p "APP_DIR=Duong dan: "
    if not exist "%APP_DIR%\GCS_ROV.exe" (
        echo [LOI] Duong dan khong hop le hoac khong chua file GCS_ROV.exe!
        pause
        exit /b 1
    )
)

echo [OK] Da tim thay thu muc phan mem tai:
echo      "%APP_DIR%"
echo.

echo [2/4] Dang sao chep file thuc thi GCS_ROV.exe v1.1.0...
copy /y "%~dp0GCS_ROV.exe" "%APP_DIR%\GCS_ROV.exe" >nul
if errorlevel 1 (
    echo [LOI] Khong the ghi de GCS_ROV.exe. Vui long chuot phai vao file .bat va chon 'Run as administrator'!
    pause
    exit /b 1
)

echo [3/4] Dang cap nhat cac module WebRTC vao _internal...
if exist "%~dp0_internal" (
    xcopy /s /e /y /q "%~dp0_internal\*" "%APP_DIR%\_internal\" >nul
)

:: Xoa sach cache bytecode cu cua settings_dialog de dam bao Python load giao dien moi
del /q "%APP_DIR%\_internal\GUI\widgets\__pycache__\settings_dialog*.pyc" 2>nul

echo [4/4] Luu thong tin phien ban v1.1.0...
mkdir "%APP_DIR%\patches" 2>nul
if exist "%~dp0version.json" copy /y "%~dp0version.json" "%APP_DIR%\patches\version.json" >nul

echo.
echo ================================================================
echo  CAP NHAT THANH CONG PHAN MEM CNC NEXORA GCS LEN v1.1.0!
echo  - Nguon video mac dinh: WebRTC (60 FPS, Do tre cuc thap)
echo  - Da loai bo cac nguon thu nghiem Webcam va Video File
echo  - Giu nguyen 100%% Ban quyen va Cau hinh tay cam Gamepad
echo ================================================================
echo.
echo Dang khoi dong lai phan mem...
timeout /t 2 /nobreak >nul
start "" "%APP_DIR%\GCS_ROV.exe"
"""

bat_path = os.path.join(PATCHES_OUTPUT_DIR, "install_patch.bat")
with open(bat_path, "w", encoding="utf-8") as f:
    f.write(bat_script)
print(f"Created: {bat_path}")

# 2. Tạo version.json
version_data = {
    "version": "1.1.0",
    "release_date": "2026-09-09",
    "changelog": (
        "v1.1.0 Official Subsea Release:\n"
        "- WebRTC Ultra Low Latency (<80ms, 60 FPS) làm màn hình lái chính mặc định.\n"
        "- Đã loại bỏ hoàn toàn Webcam và Video File khỏi cấu hình Settings.\n"
        "- Sửa lỗi video: hỗ trợ chuẩn RTSP 8554 (BlueOS & Cockpit), WebRTC và UDP H.264.\n"
        "- Tích hợp kính ngắm AR HUD và Patch Loader Hook."
    ),
    "download_url": "",
    "file_size": "20 MB",
    "update_type": "patch",
    "default_video_source": "webrtc"
}
ver_path = os.path.join(PATCHES_OUTPUT_DIR, "version.json")
with open(ver_path, "w", encoding="utf-8") as f:
    json.dump(version_data, f, indent=2, ensure_ascii=False)
print(f"Created: {ver_path}")

# 3. Đóng gói file Update_GCS_ROV_v1.1.0.zip
zip_path = os.path.join(PATCHES_OUTPUT_DIR, "Update_GCS_ROV_v1.1.0.zip")
alt_zip_path = os.path.join(PATCHES_OUTPUT_DIR, "patch_v1.1.0.zip")
exe_source = os.path.join(DIST_DIR, "GCS_ROV.exe")
pdf_source = os.path.join(PROJECT_ROOT, "HUONG_DAN_CAP_NHAT_PHAN_MEM_GCS.pdf")

if not os.path.isfile(exe_source):
    print(f"ERROR: {exe_source} does not exist!")
    sys.exit(1)

print(f"Building zip package: {zip_path} ...")
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    # 1. GCS_ROV.exe
    z.write(exe_source, "GCS_ROV.exe")
    
    # 2. _internal modules
    internal_files = [
        ("main.py", os.path.join(DIST_DIR, "_internal", "main.py")),
        ("GUI/widgets/webrtc_player_widget.py", os.path.join(DIST_DIR, "_internal", "GUI", "widgets", "webrtc_player_widget.py")),
        ("GUI/widgets/settings_dialog.py", os.path.join(DIST_DIR, "_internal", "GUI", "widgets", "settings_dialog.py")),
        ("GUI/widgets/ar_hud_widget.py", os.path.join(DIST_DIR, "_internal", "GUI", "widgets", "ar_hud_widget.py")),
        ("network/video_receiver.py", os.path.join(DIST_DIR, "_internal", "network", "video_receiver.py")),
    ]
    for rel_name, abs_path in internal_files:
        if os.path.isfile(abs_path):
            z.write(abs_path, f"_internal/{rel_name}")
            # Cũng đưa vào root để backward-compatibility
            z.write(abs_path, rel_name)
    
    # 3. install_patch.bat
    z.write(bat_path, "install_patch.bat")
    
    # 4. version.json
    z.write(ver_path, "version.json")
    
    # 5. PDF Guide
    if os.path.isfile(pdf_source):
        z.write(pdf_source, "HUONG_DAN_CAP_NHAT_PHAN_MEM_GCS.pdf")

# Tạo bản sao tên patch_v1.1.0.zip để khách dùng tên nào cũng được
shutil.copyfile(zip_path, alt_zip_path)

zip_size_mb = os.path.getsize(zip_path) / (1024 * 1024)
print(f"SUCCESS: Package created at {zip_path} ({zip_size_mb:.1f} MB)")
print(f"Copied to {alt_zip_path}")
