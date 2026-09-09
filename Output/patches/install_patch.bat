@echo off
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
