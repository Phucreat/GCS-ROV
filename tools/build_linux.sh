#!/usr/bin/env bash
# =====================================================================
# CNC NExora GCS - Automated Linux Packaging Pipeline
# =====================================================================
# Script này chạy trên Ubuntu / Debian để đóng gói phần mềm thành
# gói chạy độc lập (Standalone Tar.gz & AppImage).
# =====================================================================
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "======================================================================"
echo "🐧 BẮT ĐẦU ĐÓNG GÓI CNC NEXORA GCS TRÊN HỆ ĐIỀU HÀNH LINUX"
echo "======================================================================"

# 1. Kiểm tra môi trường ảo
if [ ! -d "env" ]; then
    echo "📦 Đang tạo môi trường ảo Python (env)..."
    python3 -m venv env
fi

source env/bin/activate

echo "📦 Đang cập nhật thư viện phụ thuộc..."
pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

# 2. Tạo thư mục Output
OUTPUT_DIR="$PROJECT_ROOT/Output"
mkdir -p "$OUTPUT_DIR"

# 3. Biên dịch bằng PyInstaller (Lưu ý: trên Linux dùng dấu : để phân cách)
echo ""
echo "🚀 [1/2] Đang biên dịch Standalone Linux Binary (PyInstaller)..."
pyinstaller --noconfirm --windowed --name=GCS_ROV \
    --icon=GUI/img/iconapp.ico \
    --add-data "GUI:GUI" \
    --add-data "AI:AI" \
    --add-data "assets:assets" \
    --add-data "core:core" \
    --add-data "database:database" \
    --add-data "network:network" \
    --add-data "utils:utils" \
    --add-data "3DC.obj:." \
    --add-data "3DC.mtl:." \
    --add-data "6DC.obj:." \
    --add-data "6DC.mtl:." \
    --add-data "yolov8n.pt:." \
    --add-data "yolov8s.pt:." \
    --add-data "LICENSE.txt:." \
    main.py

# 4. Đóng gói thành Tar.gz
echo ""
echo "📦 [2/2] Đang đóng gói bản nén phân phối Linux..."
TAR_FILE="$OUTPUT_DIR/CNC_NExora_GCS_v1.1.0_Linux_x86_64.tar.gz"
tar -czvf "$TAR_FILE" -C dist GCS_ROV

echo ""
echo "======================================================================"
echo "🎉 ĐÓNG GÓI LINUX THÀNH CÔNG RỰC RỠ!"
echo "======================================================================"
echo "📁 Tệp cài đặt xuất bản: $TAR_FILE"
echo "👉 Cách dùng trên Linux:"
echo "   1. Giải nén: tar -xzvf CNC_NExora_GCS_v1.1.0_Linux_x86_64.tar.gz"
echo "   2. Mở thư mục GCS_ROV và chạy: ./GCS_ROV"
echo "======================================================================"
