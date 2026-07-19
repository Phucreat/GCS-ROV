# HƯỚNG DẪN TEST TRUYỀN THÔNG GCS ↔ Pi ↔ ESP32
## ESP32 DevKit V1 + Raspberry Pi 5 + GCS Windows

---

## SƠ ĐỒ KẾT NỐI

```
┌─────────────────────────────────────────────────────────────┐
│  SƠ ĐỒ A — Test nhanh (không cần Pi)                        │
│                                                             │
│  [ESP32 DevKit V1]                    [PC chạy GCS]        │
│   WiFi UDP ──────────────────────────► Port 14550          │
│   (kết nối cùng WiFi)                                       │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  SƠ ĐỒ B — Test đầy đủ chuỗi                               │
│                                                             │
│  [ESP32] ──UART──► [Raspberry Pi 5] ──UDP──► [PC GCS]      │
│  TX→RX             uart_bridge.py            Port 14550     │
│  RX→TX             Port 14551 (lắng nghe)                   │
│  GND→GND                                                    │
└─────────────────────────────────────────────────────────────┘
```

---

## PHẦN 1 — CÀI ĐẶT ESP32

### Bước 1: Cài Arduino IDE
1. Tải [Arduino IDE 2.x](https://www.arduino.cc/en/software)
2. Mở **File → Preferences → Additional board URLs**, thêm:
   ```
   https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
   ```
3. Mở **Tools → Board Manager**, tìm `esp32`, cài **esp32 by Espressif Systems**

### Bước 2: Nạp code ESP32

1. Mở file `esp32_mavlink_sim.ino`
2. Chọn đúng board và port:
   ```
   Tools → Board → esp32 → ESP32 Dev Module
   Tools → Port  → COMx (Windows) hoặc /dev/ttyUSB0 (Linux)
   ```
3. **Chỉnh sửa 3 dòng này trong code:**
   ```cpp
   // Nếu dùng WiFi (Sơ đồ A):
   const char* WIFI_SSID = "TEN_WIFI_CUA_BAN";
   const char* WIFI_PASS = "MAT_KHAU_WIFI";
   const char* GCS_IP    = "192.168.1.xxx";  // IP máy tính GCS (xem ipconfig)
   
   // Nếu dùng UART (Sơ đồ B):
   // Đổi dòng đầu file từ:
   #define MODE_WIFI
   // thành:
   #define MODE_UART
   ```
4. Nhấn **Upload** (Ctrl+U)
5. Mở **Serial Monitor** (115200 baud) — xem log kết nối

### LED status:
| LED | Trạng thái |
|-----|-----------|
| Nháy 3 lần chậm | WiFi kết nối OK |
| Nháy nhanh liên tục | WiFi lỗi |
| Sáng liên tục | ARMED |
| Tắt | DISARMED |
| Nháy khi nhận lệnh | Nhận MANUAL_CONTROL |

---

## PHẦN 2 — SƠ ĐỒ A: WiFi Direct (Không cần Pi)

### Yêu cầu:
- ESP32 và PC cùng mạng WiFi
- GCS đang chạy trên PC

### Thực hiện:
1. Nạp code với `#define MODE_WIFI`
2. Đặt đúng SSID/PASS/IP vào code
3. Tìm IP PC bằng: `ipconfig` (Windows) → `IPv4 Address`
4. Khởi động GCS trên PC (kết nối `udp:0.0.0.0:14550`)
5. Bật ESP32 → xem Serial Monitor
6. GCS sẽ tự nhận dữ liệu sau 2-3 giây

### Kiểm tra trong GCS:
- ✅ Header hiện **CONNECTED** (xanh)
- ✅ Roll/Pitch/Yaw dao động sin
- ✅ Độ sâu dao động 0.5-4.5m
- ✅ Quỹ đạo 3D vẽ vòng tròn bán kính 5m
- ✅ Bảng Telemetry cập nhật TEMP, LEAK

---

## PHẦN 3 — SƠ ĐỒ B: UART → Pi → GCS

### Đấu dây ESP32 ↔ Pi

```
ESP32 DevKit V1           Raspberry Pi 5
──────────────────        ────────────────
GPIO1  (TX)     ────────► GPIO15 (RX, pin 10)
GPIO3  (RX)     ◄──────── GPIO14 (TX, pin 8)
GND             ────────── GND (pin 6/9/14/25...)

HOẶC dùng cáp USB:
ESP32 USB       ────────► Pi USB port
                          → tự nhận /dev/ttyUSB0
```

> ⚠️ **QUAN TRỌNG:** KHÔNG nối 3.3V/5V giữa 2 board — chỉ cần GND chung

### Bật UART Pi (nếu dùng GPIO):
```bash
# Trên Pi, mở raspi-config
sudo raspi-config
# → Interface Options → Serial Port
# → "Would you like a login shell...?" → NO
# → "Would you like serial port hardware enabled?" → YES
# Khởi động lại: sudo reboot
```

### Cài Pi bridge:
```bash
pip3 install pymavlink pyserial

# Chạy bridge (tự tìm port):
python3 uart_bridge.py --auto --gcs 192.168.2.1

# Hoặc chỉ định cụ thể:
python3 uart_bridge.py --serial /dev/ttyUSB0 --baud 115200 --gcs 192.168.2.1
```

### Cài GCS kết nối đúng port:
- GCS settings: Connection = `udp:0.0.0.0:14550`
- Bridge gửi từ Pi → GCS port 14550
- Bridge lắng nghe lệnh tại port 14551

---

## PHẦN 4 — KIỂM TRA VÀ DEBUG

### Kiểm tra nhanh trên PC (không cần ESP32 thật):
```bash
# Thay bằng simulator Python (test GCS trước)
cd D:\python\GCS_ROV
env\Scripts\python.exe embedded\simulator\rov_simulator.py --gcs 127.0.0.1
```

### Dùng MAVProxy để debug MAVLink:
```bash
pip install MAVProxy

# Monitor packets từ ESP32 WiFi:
mavproxy.py --master=udpin:0.0.0.0:14550 --out=udpout:127.0.0.1:14551

# Monitor packets từ Pi UART:
mavproxy.py --master=/dev/ttyUSB0,115200
```

### Wireshark filter (xem UDP MAVLink):
```
udp.port == 14550 && data[0] == 0xfe
```

---

## PHẦN 5 — LUỒNG DỮ LIỆU CHI TIẾT

```
ESP32 tự sinh dữ liệu ngẫu nhiên mỗi vòng lặp:
                                                     
  float t = millis()/1000.0f;                        
  roll  = 0.15 * sin(t * 0.5)     → ±8.6°           
  pitch = 0.10 * sin(t * 0.3)     → ±5.7°           
  yaw   = t * 0.15 mod 2π         → quay liên tục   
  depth = 2.5 + 2.0*sin(t * 0.1) → 0.5–4.5m        
  x,y   = R*cos/sin(ωt)           → vòng tròn R=5m  
  volt  = 16.8 - t/3600 * 2       → pin giảm dần    
                                                     
  Gửi MAVLink với tần suất:                          
  HEARTBEAT        1 Hz   ─────────────────────────► GCS
  ATTITUDE        50 Hz   → cập nhật mô hình 3D mượt
  SCALED_PRESSURE 10 Hz   → hiện độ sâu chính xác   
  LOCAL_POS_NED   10 Hz   → vẽ quỹ đạo 3D           
  SYS_STATUS       2 Hz   → pin                     
  NAMED_FLOAT      5 Hz   → TEMP, LEAK              
```

---

## PHẦN 6 — LỖI THƯỜNG GẶP

| Lỗi | Nguyên nhân | Giải pháp |
|-----|------------|-----------|
| GCS không nhận data | IP GCS sai | `ipconfig` lấy IPv4 thật |
| Serial port không mở | Driver USB | Cài CP2102 driver |
| WiFi kết nối fail | Sai SSID/PASS | Kiểm tra trong code |
| CRC error | Baud rate sai | Đảm bảo 115200 cả 2 đầu |
| Bridge lỗi import | pymavlink chưa cài | `pip3 install pymavlink` |

---

## PHẦN 7 — BƯỚC TIẾP THEO (Khi có phần cứng thật)

```
Hiện tại:  ESP32 → dữ liệu giả → Pi → GCS  ✅ Test OK

Tương lai khi có STM32F7 + cảm biến:
  STM32F7 → UART → Pi → GCS
  (STM32 chạy ArduSub, Pi chạy BlueOS + bridge)
  → Chỉ cần đổi serial port, KHÔNG đổi code GCS

Tương lai khi có ROV thật:
  ArduSub (STM32) → MAVLink → BlueOS (Pi) → WiFi/Ethernet → GCS
  → Đây chính là kiến trúc BlueROV2 thực tế
```
