"""
tools/generate_license.py - Master License Key Generator Tool
=============================================================
Dành cho Nhà Phát Triển / Quản Trị Viên CNC NExora.
Dùng để tạo License Key cấp cho khách hàng khi bán phần mềm.

Cách dùng:
    python tools/generate_license.py --mid NEX-A84F-91C2-88E0 --customer "PetroVietnam Gas" --type PERPETUAL
    python tools/generate_license.py --mid ANY --customer "Demo Partner" --type TRIAL --days 30
"""

import sys
import os
import argparse

# Force UTF-8 stdout
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.licensing import generate_license_key, get_machine_fingerprint, verify_license_key

def main():
    parser = argparse.ArgumentParser(description="CNC NExora Commercial License Generator")
    parser.add_argument("--mid", type=str, default="", help="Machine ID của khách hàng (hoặc ANY cho Universal Key)")
    parser.add_argument("--customer", type=str, default="Valued Customer", help="Tên khách hàng / Tổ chức")
    parser.add_argument("--type", type=str, default="COMMERCIAL_PERPETUAL", choices=["COMMERCIAL_PERPETUAL", "ENTERPRISE", "TRIAL"], help="Loại bản quyền")
    parser.add_argument("--days", type=int, default=0, help="Số ngày sử dụng (0 = Vĩnh viễn)")
    parser.add_argument("--my-id", action="store_true", help="Xem Machine ID của máy hiện tại")

    args = parser.parse_args()

    if args.my_id:
        print("\n" + "="*50)
        print("💻 MACHINE ID HIỆN TẠI CỦA MÁY NÀY:")
        print(f"   >>> {get_machine_fingerprint()} <<<")
        print("="*50 + "\n")
        return

    mid = args.mid.strip()
    if not mid:
        mid = get_machine_fingerprint()
        print(f"[INFO] Không nhập --mid, sử dụng Machine ID máy hiện tại: {mid}")

    key = generate_license_key(
        machine_id=mid,
        customer_name=args.customer,
        license_type=args.type,
        duration_days=args.days
    )

    is_valid, payload, msg = verify_license_key(key, mid)

    print("\n" + "="*65)
    print("🔑 CNC NEXORA GCS - COMMERCIAL LICENSE KEY GENERATED")
    print("="*65)
    print(f"Khách hàng   : {args.customer}")
    print(f"Machine ID   : {mid}")
    print(f"Loại License : {args.type}")
    print(f"Thời hạn     : {'Vĩnh viễn (Perpetual)' if args.days == 0 else f'{args.days} ngày'}")
    print(f"Trạng thái   : {'HỢP LỆ' if is_valid else 'LỖI'}")
    print("-" * 65)
    print("LICENSE KEY:")
    print(f"\n   {key}\n")
    print("="*65 + "\n")

if __name__ == "__main__":
    main()