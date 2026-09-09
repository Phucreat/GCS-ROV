@echo off
chcp 65001 >nul
echo =======================================================
echo    CNC NEXORA GCS - CẬP NHẬT BẢN VÁ v1.1.0
echo =======================================================
echo.
echo 1. Đang đóng ứng dụng GCS nếu đang mở...
taskkill /f /im GCS_ROV.exe >nul 2>&1
timeout /t 1 /nobreak >nul

set "TARGET_DIR=%LOCALAPPDATA%\Programs\CNC NExora GCS\patches"
if not exist "%LOCALAPPDATA%\Programs\CNC NExora GCS" (
    set "TARGET_DIR=%~dp0patches"
)
mkdir "%TARGET_DIR%" 2>nul

echo 2. Đang nạp bản vá WebRTC Camera v1.1.0...
tar -xf "%~dp0patch_v1.1.0.zip" -C "%TARGET_DIR%"

echo.
echo =======================================================
echo ✅ ĐÃ CẬP NHẬT HOÀN TẤT LÊN PHIÊN BẢN v1.1.0!
echo =======================================================
echo.
if exist "%LOCALAPPDATA%\Programs\CNC NExora GCS\GCS_ROV.exe" (
    echo Đang khởi động lại phần mềm CNC NExora GCS...
    start "" "%LOCALAPPDATA%\Programs\CNC NExora GCS\GCS_ROV.exe"
) else (
    echo Bạn có thể mở lại phần mềm GCS ngay bây giờ.
    pause
)
