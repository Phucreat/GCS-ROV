@echo off
chcp 65001 >nul
title CNC NExora GCS - Launcher

echo =======================================================
echo    🚀 CNC NEXORA GCS - KHỞI CHẠY TRÊN WINDOWS
echo =======================================================
echo.

cd /d "%~dp0"

where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [LỖI] Không tìm thấy Python trên máy tính của bạn!
    echo Vui lòng cài đặt Python 3.10 trở lên từ https://www.python.org/
    echo Lưu ý: Hãy tích chọn "Add Python to PATH" khi cài đặt.
    echo.
    pause
    exit /b 1
)

if not exist "env\Scripts\python.exe" (
    echo [1/3] Đang khởi tạo môi trường ảo Python (env)...
    python -m venv env
    echo [2/3] Đang cài đặt các thư viện cần thiết từ requirements.txt...
    call env\Scripts\activate.bat
    python -m pip install --upgrade pip
    pip install -r requirements.txt
) else (
    call env\Scripts\activate.bat
)

echo [3/3] Đang khởi động giao diện GCS ROV...
python main.py %*

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Đã dừng ứng dụng. Nhấn phím bất kỳ để đóng cửa sổ...
    pause >nul
)
