#!/usr/bin/env bash
# =====================================================================
# CNC NExora GCS - Script khởi chạy tự động cho Linux (Ubuntu/Debian/...)
# =====================================================================
set -e

cd "$(dirname "$0")"

echo "======================================================="
echo "   🚀 CNC NEXORA GCS - KHỞI CHẠY TRÊN HỆ ĐIỀU HÀNH LINUX"
echo "======================================================="

# Kiểm tra Python 3
if ! command -v python3 &> /dev/null; then
    echo "❌ Lỗi: Chưa cài đặt Python 3 trên máy!"
    echo "👉 Vui lòng chạy lệnh: sudo apt update && sudo apt install -y python3 python3-venv python3-pip"
    exit 1
fi

# Tạo môi trường ảo nếu chưa có
if [ ! -d "env" ]; then
    echo "📦 Lần đầu chạy: Đang khởi tạo môi trường ảo Python (env)..."
    python3 -m venv env
    source env/bin/activate
    echo "📦 Đang tải các thư viện cần thiết..."
    pip install --upgrade pip
    pip install -r requirements.txt
else
    source env/bin/activate
fi

# Khởi chạy phần mềm
echo "✅ Đang khởi động giao diện GCS ROV..."
python3 main.py "$@"
