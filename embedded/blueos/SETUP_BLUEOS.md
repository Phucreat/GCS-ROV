# HƯỚNG DẪN CÀI ĐẶT BlueOS + mavlink-router
## Kiến trúc đúng: ESP32 → mavlink-router → GCS

---

## 1. KIẾN TRÚC TỔNG QUAN

```
┌──────────────────────────────────────────────────────────────────┐
│                     Raspberry Pi 5 (BlueOS)                      │
│                                                                  │
│  /dev/ttyUSB0 ──► [mavlink-router] ──UDP:14550──► GCS Windows   │
│  (UART từ ESP32)        │          ◄──UDP:14550── GCS commands   │
│                         │                                        │
│                         ├──UDP:14551──► SLAM Docker             │
│                         └──UDP:14552──► Companion scripts       │
│                         └──TCP:5760───► MAVProxy/Debug          │
└──────────────────────────────────────────────────────────────────┘

Tại sao dùng mavlink-router thay Python bridge?
  ✅ Latency ~50µs (C++ native) vs ~5ms (Python)
  ✅ Zero-copy forwarding, không parse lại packet
  ✅ Đã tích hợp sẵn trong BlueOS, không cần cài thêm
  ✅ Tự động reconnect nếu GCS ngắt kết nối
  ✅ Hỗ trợ nhiều GCS cùng lúc (broadcast mode)
```

---

## 2. CÀI ĐẶT BlueOS LÊN Pi 5

### Tải image BlueOS:
```
https://github.com/bluerobotics/BlueOS/releases/latest
```
Tải file: `BlueOS-raspberry-pi-x.x.x.zip`

### Flash vào thẻ SD/USB:
```bash
# Dùng Raspberry Pi Imager (khuyến nghị)
# Hoặc Balena Etcher
```

### Kết nối mạng:
- Cắm Pi vào router/switch LAN
- Hoặc dùng tether adapter (BlueRobotics FXTI)
- Truy cập: `http://blueos.local` hoặc `http://192.168.2.2`

---

## 3. CẤU HÌNH mavlink-router QUA WEB UI

### Bước 1: Mở BlueOS Web UI
```
http://blueos.local
Hoặc: http://192.168.2.2
```

### Bước 2: MAVLink Endpoints
```
Menu → MAVLink Endpoints
```

### Bước 3: Thêm Serial Endpoint (ESP32)
```
Click "+ Add Endpoint"
Type     : Serial
Device   : /dev/ttyUSB0  (USB cable)
           hoặc /dev/ttyAMA0 (GPIO UART)
Baud     : 115200
```

### Bước 4: Thêm UDP Endpoint (GCS)
```
Click "+ Add Endpoint"
Type    : UDP
Mode    : Client (Pi chủ động gửi đến GCS)
IP      : 192.168.2.1   ← IP máy tính GCS (xem ipconfig)
Port    : 14550
```

---

## 4. CẤU HÌNH BẰNG FILE (thay thế Web UI)

Nếu muốn cài đặt thủ công qua SSH:

```bash
# SSH vào Pi
ssh pi@blueos.local  # password: raspberry

# Copy file config
sudo cp mavlink-router.conf /etc/mavlink-router/main.conf

# Khởi động lại service
sudo systemctl restart mavlink-router

# Xem log
sudo journalctl -u mavlink-router -f
```

---

## 5. BẬT UART GPIO (nếu dùng Cách B - GPIO)

### Trên BlueOS terminal hoặc SSH:
```bash
# BlueOS dùng Raspberry Pi OS dưới nền
sudo raspi-config
# → Interface Options
# → Serial Port
# → Login shell: NO
# → Hardware enabled: YES
# → Reboot
```

### Kiểm tra UART:
```bash
ls -la /dev/ttyAMA*   # → /dev/ttyAMA0 hoặc /dev/ttyAMA10
ls -la /dev/ttyUSB*   # → /dev/ttyUSB0 (USB cable)
```

---

## 6. ĐẤU DÂY ESP32 ↔ Pi 5

### Cách A — USB (Đơn giản, dùng để test):
```
ESP32 USB → Pi USB-A port
Pi nhận tại: /dev/ttyUSB0
KHÔNG cần driver thêm
```

### Cách B — GPIO UART (Cho sản phẩm):
```
ESP32 DevKit V1         Raspberry Pi 5
───────────────         ──────────────
GPIO1 (TX)    ────────► Pin 10 (GPIO15/RXD0)
GPIO3 (RX)    ◄──────── Pin 8  (GPIO14/TXD0)
GND           ────────── Pin 6  (GND)

⚠️ Điện áp: Cả 2 đều 3.3V logic → OK, không cần level shifter
⚠️ KHÔNG nối 5V/3.3V nguồn giữa 2 board!
```

### Sơ đồ chân Pi 5 (GPIO Header):
```
 3V3  [1][2]  5V
GPIO2 [3][4]  5V
GPIO3 [5][6]  GND  ←── Nối GND ESP32 vào đây
GPIO4 [7][8]  GPIO14(TXD)  ←── Nối RX ESP32
 GND  [9][10] GPIO15(RXD)  ←── Nối TX ESP32
```

---

## 7. KIỂM TRA HOẠT ĐỘNG

### Bước 1: Xem log mavlink-router trên Pi
```bash
ssh pi@blueos.local
sudo journalctl -u mavlink-router -f

# Output mong đợi:
# [info] Forwarding 1 message from endpoint 'ESP32' to 'GCS'
# [info] New connection from GCS (192.168.2.1:14550)
```

### Bước 2: Dùng MAVProxy debug (từ PC)
```bash
pip install MAVProxy
mavproxy.py --master=udpin:0.0.0.0:14550 --console

# Kết quả mong đợi:
# APM: ArduSub V4.x
# HEARTBEAT {type : 12, autopilot : 3, ...}
# ATTITUDE {roll : 0.12, pitch : -0.05, yaw : 1.23}
```

### Bước 3: Bật GCS và kiểm tra
```
GCS Settings → Connection: udp:0.0.0.0:14550 → Connect
→ Header hiện "CONNECTED" màu xanh
→ Mô hình 3D bắt đầu xoay theo dữ liệu ESP32
→ Bảng telemetry hiện roll/pitch/yaw/depth
```

---

## 8. LUỒNG ĐẦY ĐỦ KHI TEST

```
[ESP32 DevKit V1]
 ├── Tự sinh dữ liệu giả (không cần cảm biến)
 ├── Gửi MAVLink qua UART 115200
 └── LED nháy theo trạng thái ARM/command

     ↓ UART (USB cable hoặc GPIO)

[Raspberry Pi 5 - BlueOS]
 └── mavlink-router (C++, ~50µs)
      ├── Nhận từ /dev/ttyUSB0
      └── Forward đến 192.168.2.1:14550

     ↓ UDP qua LAN/WiFi

[Windows PC - GCS]
 ├── Hiển thị dữ liệu real-time
 ├── Bàn phím WASD → MANUAL_CONTROL → xuống ESP32
 └── ARM/DISARM → LED ESP32 sáng/tắt

Latency tổng: ~1-2ms (UART) + ~50µs (router) + ~1ms (LAN) ≈ 2-3ms
```

---

## 9. NÂNG CẤP LÊN PIXHAWK STM32F7

Khi có phần cứng thật, **KHÔNG cần thay đổi gì ở GCS**:
```
Bây giờ : ESP32 (giả lập) → UART → mavlink-router → GCS
Sau này  : Pixhawk STM32F7 (thật) → UART → mavlink-router → GCS
                                                ↑
                                    Chỉ đổi serial port trong config
```

Lý do: Pixhawk cũng giao tiếp MAVLink qua UART 115200 → giao diện giống hệt.
