#!/usr/bin/env bash
# =====================================================================
# CNC NExora GCS - Automated macOS Packaging Pipeline
# =====================================================================
# Script này chạy trên máy Mac (Apple Silicon M1/M2/M3/M4 hoặc Intel)
# để đóng gói ứng dụng thành file .app và đĩa cài đặt .dmg
# =====================================================================
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "======================================================================"
echo "🍎 BẮT ĐẦU ĐÓNG GÓI CNC NEXORA GCS TRÊN HỆ ĐIỀU HÀNH MACOS"
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

# 3. Biên dịch bằng PyInstaller (Tạo bundle .app trên macOS)
echo ""
echo "🚀 [1/2] Đang biên dịch macOS Application Bundle (PyInstaller)..."
pyinstaller --noconfirm --windowed --name="CNC_NExora_GCS" \
    --collect-all OpenGL \
    --collect-all pyqtgraph \
    --collect-all pyvista \
    --collect-all pyvistaqt \
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

# 4. Đóng gói đĩa cài đặt Apple DMG (Dùng tiện ích hdiutil có sẵn trên Mac)
echo ""
echo "💿 [2/2] Đang tạo đĩa cài đặt Apple Disk Image (.dmg)..."
DMG_FILE="$OUTPUT_DIR/CNC_NExora_GCS_v1.1.0_macOS.dmg"
rm -f "$DMG_FILE"

hdiutil create -volname "CNC NExora GCS" \
    -srcfolder "dist/CNC_NExora_GCS.app" \
    -ov -format UDZO \
    "$DMG_FILE"

# Nén thêm bản Zip dự phòng
ZIP_FILE="$OUTPUT_DIR/CNC_NExora_GCS_v1.1.0_macOS.zip"
cd dist && zip -rq "$ZIP_FILE" "CNC_NExora_GCS.app" && cd "$PROJECT_ROOT"

echo ""
echo "======================================================================"
echo "🎉 ĐÓNG GÓI MACOS THÀNH CÔNG RỰC RỠ!"
echo "======================================================================"
echo "💿 Tệp cài đặt DMG : $DMG_FILE"
echo "📦 Tệp nén Zip App : $ZIP_FILE"
echo "👉 Cách dùng trên macOS:"
echo "   Khách mở file .dmg và kéo 'CNC_NExora_GCS' vào thư mục Applications!"
echo "======================================================================"
