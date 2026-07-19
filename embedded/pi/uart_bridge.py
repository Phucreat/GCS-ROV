"""
uart_bridge.py - Pi UART <-> UDP MAVLink Bridge
================================================
Chay tren Raspberry Pi, dung khi ESP32 ket noi qua UART.

Chuc nang:
  1. Doc MAVLink tu ESP32 qua UART (/dev/ttyUSB0)
  2. Chuyen tiep len GCS qua UDP
  3. Nhan lenh tu GCS UDP → chuyen tiep xuong ESP32 UART
  4. In thong ke packets moi 5 giay

Ket noi phan cung:
  ESP32 TX (GPIO1) → Pi RX (UART)
  ESP32 RX (GPIO3) → Pi TX (UART)
  ESP32 GND        → Pi GND

  Neu dung USB cable: pi nhan ra /dev/ttyUSB0 tu dong

Cach chay:
  pip install pymavlink pyserial
  python3 uart_bridge.py --serial /dev/ttyUSB0 --gcs 192.168.2.1
  
  Hay tu dong tim serial port:
  python3 uart_bridge.py --auto
"""
import os
import sys
import time
import threading
import argparse

os.environ['MAVLINK20'] = '1'
from pymavlink import mavutil


# ═══════════════════════════════════════════════
# THONG KE
# ═══════════════════════════════════════════════
class Stats:
    def __init__(self):
        self.rx_from_esp  = 0   # packets tu ESP32
        self.tx_to_gcs    = 0   # packets den GCS
        self.rx_from_gcs  = 0   # packets tu GCS
        self.tx_to_esp    = 0   # packets den ESP32
        self.errors       = 0

stats = Stats()


# ═══════════════════════════════════════════════
# TIM CONG SERIAL TU DONG
# ═══════════════════════════════════════════════
def find_serial_port():
    """Tim tu dong cong USB serial cua ESP32."""
    import glob
    candidates = (
        glob.glob('/dev/ttyUSB*') +
        glob.glob('/dev/ttyACM*') +
        glob.glob('/dev/ttyAMA*')
    )
    if not candidates:
        raise RuntimeError("Khong tim thay cong serial! Cam ESP32 vao Pi truoc.")
    print(f"[Bridge] Tim thay serial ports: {candidates}")
    port = candidates[0]
    print(f"[Bridge] Su dung: {port}")
    return port


# ═══════════════════════════════════════════════
# THREAD 1: ESP32 UART → GCS UDP
# ═══════════════════════════════════════════════
def thread_esp32_to_gcs(serial_conn, gcs_out):
    """
    Doc MAVLink tu ESP32 qua UART, chuyen tiep len GCS qua UDP.
    Chay lien tuc den khi ket thuc chuong trinh.
    """
    print("[Bridge] Thread ESP32→GCS started")
    while True:
        try:
            msg = serial_conn.recv_match(blocking=True, timeout=1.0)
            if msg is None:
                continue

            t = msg.get_type()
            stats.rx_from_esp += 1

            # Chuyen tiep toan bo message den GCS
            # pymavlink tu dong dong goi lai thanh bytes
            buf = msg.get_msgbuf()
            if buf:
                gcs_out.write(buf)
                stats.tx_to_gcs += 1

        except Exception as e:
            stats.errors += 1
            if 'timeout' not in str(e).lower():
                print(f"[Bridge] ESP32→GCS error: {e}")
            time.sleep(0.01)


# ═══════════════════════════════════════════════
# THREAD 2: GCS UDP → ESP32 UART
# ═══════════════════════════════════════════════
def thread_gcs_to_esp32(gcs_in, serial_conn):
    """
    Nhan lenh tu GCS qua UDP, chuyen xuong ESP32 qua UART.
    Chi forward cac lenh dieu khien: MANUAL_CONTROL, COMMAND_LONG, HEARTBEAT.
    """
    FORWARD_TYPES = {
        'MANUAL_CONTROL', 'COMMAND_LONG', 'HEARTBEAT',
        'SET_ATTITUDE_TARGET', 'PARAM_SET',
    }
    print("[Bridge] Thread GCS→ESP32 started")
    while True:
        try:
            msg = gcs_in.recv_match(blocking=True, timeout=1.0)
            if msg is None:
                continue

            t = msg.get_type()
            stats.rx_from_gcs += 1

            if t in FORWARD_TYPES:
                buf = msg.get_msgbuf()
                if buf:
                    serial_conn.write(buf)
                    stats.tx_to_esp += 1

        except Exception as e:
            stats.errors += 1
            if 'timeout' not in str(e).lower():
                print(f"[Bridge] GCS→ESP32 error: {e}")
            time.sleep(0.01)


# ═══════════════════════════════════════════════
# THREAD THONG KE
# ═══════════════════════════════════════════════
def thread_stats():
    while True:
        time.sleep(5)
        print(
            f"[Bridge] Stats: "
            f"ESP32→GCS={stats.rx_from_esp}/{stats.tx_to_gcs} | "
            f"GCS→ESP32={stats.rx_from_gcs}/{stats.tx_to_esp} | "
            f"Errors={stats.errors}"
        )


# ═══════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description='Pi UART↔UDP MAVLink Bridge (ESP32 ↔ GCS)'
    )
    parser.add_argument('--serial', default=None,
                        help='Cong serial ESP32 (VD: /dev/ttyUSB0)')
    parser.add_argument('--baud',   default=115200, type=int,
                        help='Baud rate UART (default: 115200)')
    parser.add_argument('--gcs',    default='192.168.2.1',
                        help='IP may tinh GCS (default: 192.168.2.1)')
    parser.add_argument('--gcs-port', default=14550, type=int,
                        help='GCS MAVLink UDP port (default: 14550)')
    parser.add_argument('--listen-port', default=14551, type=int,
                        help='Port Pi lang nghe lenh tu GCS (default: 14551)')
    parser.add_argument('--auto', action='store_true',
                        help='Tu dong tim cong serial')
    args = parser.parse_args()

    # Xac dinh cong serial
    serial_port = args.serial
    if args.auto or serial_port is None:
        serial_port = find_serial_port()

    print(f"[Bridge] === Pi UART Bridge ===")
    print(f"[Bridge] Serial : {serial_port} @ {args.baud} baud")
    print(f"[Bridge] GCS out: {args.gcs}:{args.gcs_port}")
    print(f"[Bridge] GCS in : 0.0.0.0:{args.listen_port}")

    # --- Ket noi Serial (ESP32) ---
    print(f"[Bridge] Dang ket noi Serial: {serial_port}...")
    try:
        serial_conn = mavutil.mavlink_connection(
            serial_port,
            baud      = args.baud,
            source_system    = 255,  # GCS proxy
            source_component = 190,
        )
        print(f"[Bridge] Serial OK")
    except Exception as e:
        print(f"[Bridge] Loi mo serial: {e}")
        sys.exit(1)

    # --- Ket noi GCS (output: gui len) ---
    gcs_out = mavutil.mavlink_connection(
        f"udpout:{args.gcs}:{args.gcs_port}",
        source_system    = 1,   # giong ESP32
        source_component = 1,
    )
    print(f"[Bridge] GCS output socket OK")

    # --- Ket noi GCS (input: nhan lenh) ---
    gcs_in = mavutil.mavlink_connection(
        f"udpin:0.0.0.0:{args.listen_port}",
        source_system    = 255,
        source_component = 190,
    )
    print(f"[Bridge] GCS input socket OK")

    # Khoi chay 3 thread
    t1 = threading.Thread(target=thread_esp32_to_gcs,
                          args=(serial_conn, gcs_out), daemon=True)
    t2 = threading.Thread(target=thread_gcs_to_esp32,
                          args=(gcs_in, serial_conn), daemon=True)
    t3 = threading.Thread(target=thread_stats, daemon=True)

    t1.start()
    t2.start()
    t3.start()

    print("[Bridge] Running! Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n[Bridge] Stopped. Final stats:")
        print(f"  ESP32→GCS: {stats.rx_from_esp} recv / {stats.tx_to_gcs} sent")
        print(f"  GCS→ESP32: {stats.rx_from_gcs} recv / {stats.tx_to_esp} sent")


if __name__ == '__main__':
    main()
