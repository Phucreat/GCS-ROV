"""
tools/create_patch.py - 1-Click Delta Patch Packaging Tool for Developers
========================================================================
Dành cho lập trình viên: Mỗi khi bạn sửa code, chạy công cụ này để:
1. Tự động gom các file code Python và tài nguyên giao diện đã thay đổi.
2. Đóng gói thành file zip siêu nhẹ (1–3 MB): Output/patches/patch_vX.X.X.zip
3. Sinh file version.json để upload lên GitHub Releases / Server cho Online OTA.
4. Sinh file install_patch.bat đi kèm cho khách hàng nạp Offline 1-click.

Cách dùng:
    python tools/create_patch.py --version 1.0.1 --changelog "Tối ưu video RTSP Zero-Latency, nâng cấp Nexos"
"""

import argparse
import datetime
import hashlib
import json
import os
import sys
import zipfile

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Danh sách các thư mục và file mã nguồn cần đưa vào bản vá
INCLUDE_DIRS = [
    "network",
    "GUI",
    "AI",
    "core",
    "database",
    "utils",
    "assets",
]

INCLUDE_FILES = [
    "main.py",
]

EXCLUDE_EXTENSIONS = {
    ".pyc", ".pyo", ".pyd", ".log", ".tmp", ".bak", ".swp"
}

EXCLUDE_DIRS = {
    "__pycache__", ".git", ".idea", ".vscode", "env", "build", "dist", "Output", "logs", "media"
}


def calculate_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def create_patch(version: str, changelog: str, output_dir: str, download_base_url: str):
    print(f"\n==================================================")
    print(f"📦 BẮT ĐẦU ĐÓNG GÓI BẢN VÁ DELTA PATCH: v{version}")
    print(f"==================================================")

    os.makedirs(output_dir, exist_ok=True)
    patch_zip_name = f"patch_v{version}.zip"
    patch_zip_path = os.path.join(output_dir, patch_zip_name)

    # 1. Tạo file zip chứa code
    total_files = 0
    total_uncompressed_bytes = 0

    with zipfile.ZipFile(patch_zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        # A. Đóng gói các file lẻ
        for fname in INCLUDE_FILES:
            fpath = os.path.join(PROJECT_ROOT, fname)
            if os.path.isfile(fpath):
                zf.write(fpath, arcname=fname)
                total_files += 1
                total_uncompressed_bytes += os.path.getsize(fpath)
                print(f" [+] Thêm file: {fname}")

        # B. Đóng gói các thư mục mã nguồn
        for dname in INCLUDE_DIRS:
            dir_path = os.path.join(PROJECT_ROOT, dname)
            if not os.path.isdir(dir_path):
                continue
            for root, dirs, files in os.walk(dir_path):
                # Loại bỏ thư mục loại trừ
                dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

                for file in files:
                    _, ext = os.path.splitext(file)
                    if ext.lower() in EXCLUDE_EXTENSIONS:
                        continue
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, PROJECT_ROOT)
                    zf.write(full_path, arcname=rel_path)
                    total_files += 1
                    total_uncompressed_bytes += os.path.getsize(full_path)

        # C. Nhúng version.json nội bộ vào trong file zip để GCS nhận biết sau giải nén
        internal_version_data = {
            "version": version,
            "release_date": datetime.date.today().strftime("%Y-%m-%d"),
            "changelog": changelog,
            "packaged_at": datetime.datetime.now().isoformat(),
        }
        zf.writestr("version.json", json.dumps(internal_version_data, indent=2, ensure_ascii=False))

    zip_size_bytes = os.path.getsize(patch_zip_path)
    zip_size_mb = zip_size_bytes / (1024 * 1024)
    sha256_hash = calculate_sha256(patch_zip_path)

    print(f"\n✅ Đã tạo gói bản vá: {patch_zip_path}")
    print(f"   • Số lượng file: {total_files}")
    print(f"   • Dung lượng giải nén: {total_uncompressed_bytes / (1024 * 1024):.2f} MB")
    print(f"   • Dung lượng file nén: {zip_size_mb:.2f} MB ({zip_size_bytes:,} bytes)")
    print(f"   • SHA256: {sha256_hash[:16]}...")

    # 2. Tạo file version.json cho máy chủ Web / GitHub Releases
    server_version_data = {
        "version": version,
        "release_date": datetime.date.today().strftime("%Y-%m-%d"),
        "changelog": changelog,
        "update_type": "patch",
        "download_url": f"{download_base_url.rstrip('/')}/{patch_zip_name}",
        "file_size": f"{zip_size_mb:.1f} MB",
        "sha256": sha256_hash,
    }

    server_json_path = os.path.join(output_dir, "version.json")
    with open(server_json_path, "w", encoding="utf-8") as f:
        json.dump(server_version_data, f, indent=2, ensure_ascii=False)

    print(f"✅ Đã tạo file Server version: {server_json_path}")

    # 3. Tạo file install_patch.bat đi kèm cho khách hàng nạp Offline 1-Click
    bat_content = f"""@echo off
chcp 65001 >nul
echo =======================================================
echo    CNC NEXORA GCS - CẬP NHẬT BẢN VÁ v{version}
echo =======================================================
echo.
echo 1. Đang dừng tiến trình GCS nếu đang chạy...
taskkill /f /im GCS_ROV.exe >nul 2>&1
timeout /t 1 /nobreak >nul

set "TARGET_DIR=%LOCALAPPDATA%\\Programs\\CNC NExora GCS\\patches"
if not exist "%LOCALAPPDATA%\\Programs\\CNC NExora GCS" (
    set "TARGET_DIR=%~dp0patches"
)
mkdir "%TARGET_DIR%" 2>nul

echo 2. Đang giải nén bản vá vào thư mục hệ thống...
tar -xf "%~dp0{patch_zip_name}" -C "%TARGET_DIR%"

echo.
echo =======================================================
echo ✅ ĐÃ CẬP NHẬT HOÀN TẤT LÊN PHIÊN BẢN v{version}!
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
    bat_path = os.path.join(output_dir, "install_patch.bat")
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)

    print(f"✅ Đã tạo script cài đặt Offline 1-Click: {bat_path}")
    print(f"\n🎉 HOÀN TẤT! Bạn chỉ cần gửi file '{patch_zip_name}' (hoặc kèm file 'install_patch.bat') cho khách hàng!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tạo bản vá Delta Patch siêu nhẹ cho CNC NExora GCS")
    parser.add_argument("--version", type=str, default="1.0.1", help="Phiên bản bản vá (ví dụ: 1.0.1)")
    parser.add_argument(
        "--changelog",
        type=str,
        default="- Tối ưu luồng video RTSP thời gian thực Zero-Latency.\n- Nâng cấp độ phân giải 1280x720 HD.\n- Cải thiện trợ lý ảo Nexos.",
        help="Nội dung nhật ký thay đổi"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=os.path.join(PROJECT_ROOT, "Output", "patches"),
        help="Thư mục xuất file patch"
    )
    parser.add_argument(
        "--url",
        type=str,
        default="https://raw.githubusercontent.com/cncnexora/gcs-rov/main/patches",
        help="URL gốc tải patch trên máy chủ"
    )

    args = parser.parse_args()
    create_patch(
        version=args.version,
        changelog=args.changelog,
        output_dir=args.output_dir,
        download_base_url=args.url
    )
