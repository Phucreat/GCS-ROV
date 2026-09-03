"""
build_commercial_release.py - Automated Commercial Release Builder
==================================================================
Tự động đóng gói toàn bộ ứng dụng CNC NExora GCS thành 1 file cài đặt .exe duy nhất:
Output/Setup_CNC_NExora_GCS_v1.0.exe
"""

import sys
import os
import time
import shutil
import hashlib
import subprocess

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
ISCC_PATHS = [
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Inno Setup 6", "ISCC.exe"),
    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    r"C:\Program Files\Inno Setup 6\ISCC.exe",
]

def find_iscc():
    for p in ISCC_PATHS:
        if os.path.exists(p):
            return p
    # Check PATH
    try:
        res = subprocess.run(["where", "ISCC.exe"], capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip().splitlines()[0]
    except Exception:
        pass
    return None

def format_size(bytes_val):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_val < 1024.0:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.2f} TB"

def get_file_sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest().upper()

def main():
    start_time = time.time()
    print("\n" + "="*70)
    print("🚀 CNC NEXORA GCS - COMMERCIAL RELEASE PACKAGING PIPELINE")
    print("="*70)
    print(f"📁 Thư mục dự án : {PROJECT_ROOT}")
    print(f"⏱️ Thời gian bắt đầu: {time.ctime()}")

    # 1. Check ISCC compiler
    iscc_exe = find_iscc()
    if not iscc_exe:
        print("\n❌ LỖI: Không tìm thấy Inno Setup Compiler (ISCC.exe)!")
        print("Đang tiến hành cài đặt Inno Setup qua winget...")
        subprocess.run(["winget", "install", "--id", "JRSoftware.InnoSetup", "--silent", "--accept-package-agreements", "--accept-source-agreements"])
        iscc_exe = find_iscc()
        if not iscc_exe:
            print("❌ Vẫn không tìm thấy ISCC.exe. Vui lòng kiểm tra lại Inno Setup.")
            sys.exit(1)

    print(f"✅ Đã tìm thấy Inno Setup Compiler: {iscc_exe}")

    # 2. Verify critical assets
    required_assets = [
        "main.py", "GCS_ROV.spec", "installer.iss", "LICENSE.txt",
        "3DC.obj", "3DC.mtl", "6DC.obj", "6DC.mtl", "yolov8n.pt",
        os.path.join("GUI", "img", "iconapp.ico")
    ]
    for a in required_assets:
        full_p = os.path.join(PROJECT_ROOT, a)
        if not os.path.exists(full_p):
            print(f"❌ THIẾU TỆP BẮT BUỘC: {a}")
            sys.exit(1)
    print("✅ Đã kiểm tra đầy đủ các tệp tài nguyên, 3D CAD và License.")

    # 3. Clean Output directory
    print("\n🧹 [BƯỚC 1/3] Đang chuẩn bị thư mục xuất bản Output...")
    output_dir = os.path.join(PROJECT_ROOT, "Output")
    os.makedirs(output_dir, exist_ok=True)

    # 4. PyInstaller Build
    print("\n📦 [BƯỚC 2/3] Đang biên dịch Standalone Python Binary (PyInstaller)...")
    spec_file = os.path.join(PROJECT_ROOT, "GCS_ROV.spec")
    pyinstaller_cmd = [
        sys.executable, "-m", "PyInstaller",
        spec_file,
        "--noconfirm"
    ]
    
    t_pyinst = time.time()
    res = subprocess.run(pyinstaller_cmd, cwd=PROJECT_ROOT)
    if res.returncode != 0:
        print(f"\n❌ LỖI: PyInstaller biên dịch thất bại với mã lỗi {res.returncode}!")
        sys.exit(res.returncode)
    
    dur_pyinst = time.time() - t_pyinst
    print(f"✅ Biên dịch PyInstaller hoàn tất trong {dur_pyinst:.1f}s.")

    dist_exe = os.path.join(PROJECT_ROOT, "dist", "GCS_ROV", "GCS_ROV.exe")
    if not os.path.exists(dist_exe):
        print(f"❌ Không tìm thấy tệp nhị phân {dist_exe}!")
        sys.exit(1)

    # 5. Inno Setup Packaging
    print("\n💿 [BƯỚC 3/3] Đang đóng gói Bộ Cài Đặt Thương Mại (Inno Setup LZMA2 Ultra)...")
    iss_file = os.path.join(PROJECT_ROOT, "installer.iss")
    t_iscc = time.time()
    res_iscc = subprocess.run([iscc_exe, iss_file], cwd=PROJECT_ROOT)
    if res_iscc.returncode != 0:
        print(f"\n❌ LỖI: Inno Setup đóng gói thất bại với mã lỗi {res_iscc.returncode}!")
        sys.exit(res_iscc.returncode)
    dur_iscc = time.time() - t_iscc
    print(f"✅ Inno Setup hoàn tất đóng gói trong {dur_iscc:.1f}s.")

    # 6. Summary & Checksum
    final_installer = os.path.join(output_dir, "Setup_CNC_NExora_GCS_v1.0.exe")
    if os.path.exists(final_installer):
        fsize = os.path.getsize(final_installer)
        fhash = get_file_sha256(final_installer)
        total_time = time.time() - start_time

        print("\n" + "="*70)
        print("🎉 ĐÓNG GÓI BỘ CÀI ĐẶT THƯƠNG MẠI THÀNH CÔNG RỰC RỠ!")
        print("="*70)
        print(f"📦 Tệp cài đặt duy nhất : {final_installer}")
        print(f"📊 Dung lượng tệp       : {format_size(fsize)} ({fsize:,} bytes)")
        print(f"🔒 Checksum (SHA-256)   : {fhash}")
        print(f"⏱️ Tổng thời gian xử lý  : {total_time:.1f} giây")
        print("="*70)
        print("\n👉 Bạn có thể gửi trực tiếp file 'Setup_CNC_NExora_GCS_v1.0.exe' cho khách hàng.")
        print("👉 Khách hàng chỉ cần bấm đúp chuột để cài đặt và sử dụng ngay lập tức 100% độc lập!\n")
    else:
        print(f"❌ Không tìm thấy tệp cài đặt tại: {final_installer}")

if __name__ == "__main__":
    main()