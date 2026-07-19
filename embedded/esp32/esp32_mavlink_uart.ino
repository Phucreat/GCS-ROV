/**
 * esp32_mavlink_uart.ino
 * =======================
 * ESP32 DevKit V1 — Gửi MAVLink V1 qua UART đến Pi (BlueOS)
 * 
 * KIẾN TRÚC BlueOS:
 *   [ESP32] ──UART 115200──► [mavlink-router BlueOS] ──UDP──► [GCS]
 *              Không cần code bridge trên Pi!
 *              mavlink-router tự chuyển tiếp với latency ~50µs
 * 
 * ĐẤU DÂY (chọn 1 trong 2 cách):
 * 
 *   Cách A — USB cable (đơn giản nhất, dùng để test):
 *     ESP32 USB ──USB──► Pi USB port
 *     Pi nhận tại: /dev/ttyUSB0
 * 
 *   Cách B — GPIO UART (cho sản phẩm cuối):
 *     ESP32 GPIO1(TX) ──► Pi GPIO15/Pin10 (RX)
 *     ESP32 GPIO3(RX) ◄── Pi GPIO14/Pin8  (TX)
 *     ESP32 GND       ─── Pi GND (Pin 6/9/14/25)
 *     Pi nhận tại: /dev/ttyAMA0
 *     ⚠️ Mức điện áp: Pi GPIO = 3.3V, ESP32 GPIO = 3.3V → OK
 *        KHÔNG kết nối với 5V!
 * 
 * DỮ LIỆU GIẢ SINH RA:
 *   HEARTBEAT        1 Hz   — ROV còn sống
 *   SYS_STATUS       2 Hz   — Pin giảm dần (16.8V→12V mô phỏng 2h)
 *   SCALED_PRESSURE 10 Hz   — Áp suất từ độ sâu giả
 *   ATTITUDE        50 Hz   — Roll/Pitch/Yaw dao động sin
 *   LOCAL_POS_NED   10 Hz   — ROV đi vòng tròn R=5m
 *   VFR_HUD         10 Hz   — Heading, depth, speed
 *   NAMED_VALUE     5 Hz    — TEMP nước, LEAK sensor
 * 
 * NHẬN LỆNH TỪ GCS (qua mavlink-router):
 *   MANUAL_CONTROL  → LED nháy + log Serial
 *   ARM/DISARM      → LED sáng/tắt + log
 * 
 * KHÔNG CẦN THƯ VIỆN NGOÀI — MAVLink tự xây dựng thủ công
 */

#include <Arduino.h>
#include <math.h>

// ═══════════════════════════════════════════════
// CẤU HÌNH
// ═══════════════════════════════════════════════
#define UART_BAUD    115200       // Baud rate UART đến Pi
#define MAV_SYS_ID   1            // System ID của ROV
#define MAV_COMP_ID  1            // Component: Autopilot
#define LED_PIN      2            // LED_BUILTIN ESP32 DevKit V1

// MAVLink V1 Start byte
#define MAV_STX   0xFE

// Message IDs
#define MSG_HEARTBEAT         0
#define MSG_SYS_STATUS        1
#define MSG_SCALED_PRESSURE  29
#define MSG_ATTITUDE         30
#define MSG_LOCAL_POS_NED    32
#define MSG_VFR_HUD          74
#define MSG_COMMAND_LONG     76
#define MSG_COMMAND_ACK      77
#define MSG_NAMED_VALUE_FLOAT 251

// CRC_EXTRA (đặc trưng mỗi message ID trong MAVLink)
static const uint8_t CRC_EXTRA_TBL[] = {
  /* 0  */ 50,  // HEARTBEAT
  /* 1  */ 124, // SYS_STATUS
  /* 29 */ 115, // SCALED_PRESSURE
  /* 30 */ 39,  // ATTITUDE
  /* 32 */ 185, // LOCAL_POSITION_NED
  /* 69 */ 243, // MANUAL_CONTROL
  /* 74 */ 20,  // VFR_HUD
  /* 76 */ 152, // COMMAND_LONG
  /* 77 */ 143, // COMMAND_ACK
  /* 251*/ 170, // NAMED_VALUE_FLOAT
};

static uint8_t crc_extra_for(uint8_t id) {
  switch(id) {
    case 0:   return 50;
    case 1:   return 124;
    case 29:  return 115;
    case 30:  return 39;
    case 32:  return 185;
    case 69:  return 243;
    case 74:  return 20;
    case 76:  return 152;
    case 77:  return 143;
    case 251: return 170;
    default:  return 0;
  }
}

// ═══════════════════════════════════════════════
// TRẠNG THÁI
// ═══════════════════════════════════════════════
static uint8_t  mav_seq   = 0;
static bool     is_armed  = false;
static int16_t  cmd_x     = 0;
static int16_t  cmd_y     = 0;
static uint16_t cmd_z     = 500;
static int16_t  cmd_r     = 0;
static uint16_t cmd_buttons = 0;

// ═══════════════════════════════════════════════
// CRC X25 (MAVLink checksum)
// ═══════════════════════════════════════════════
static void crc_acc(uint8_t d, uint16_t* crc) {
  uint8_t tmp = d ^ (*crc & 0xFF);
  tmp ^= (tmp << 4);
  *crc = (*crc >> 8) ^ ((uint16_t)tmp << 8) ^ ((uint16_t)tmp << 3) ^ (tmp >> 4);
}

// ═══════════════════════════════════════════════
// GỬI PACKET MAVLink V1 QUA UART
// ═══════════════════════════════════════════════
static void mav_send(uint8_t msg_id, uint8_t* payload, uint8_t plen) {
  uint8_t hdr[6] = { MAV_STX, plen, mav_seq++, MAV_SYS_ID, MAV_COMP_ID, msg_id };

  // Tính CRC từ byte LEN (index 1) đến hết payload, thêm CRC_EXTRA
  uint16_t crc = 0xFFFF;
  for (int i = 1; i < 6; i++)    crc_acc(hdr[i], &crc);
  for (int i = 0; i < plen; i++) crc_acc(payload[i], &crc);
  crc_acc(crc_extra_for(msg_id), &crc);

  Serial.write(hdr, 6);
  Serial.write(payload, plen);
  Serial.write((uint8_t)(crc & 0xFF));
  Serial.write((uint8_t)(crc >> 8));
}

// ═══════════════════════════════════════════════
// TIỆN ÍCH PACK DỮ LIỆU (Little-Endian)
// ═══════════════════════════════════════════════
static void pu32(uint8_t* b, uint32_t v) { b[0]=v; b[1]=v>>8; b[2]=v>>16; b[3]=v>>24; }
static void pi16(uint8_t* b, int16_t  v) { b[0]=v; b[1]=v>>8; }
static void pu16(uint8_t* b, uint16_t v) { b[0]=v; b[1]=v>>8; }
static void pf32(uint8_t* b, float    v) { uint32_t r; memcpy(&r,&v,4); pu32(b,r); }

// UNPACK nhận từ GCS
static int16_t  ui16s(uint8_t* b) { return (int16_t)(b[0]|(b[1]<<8)); }
static uint16_t ui16u(uint8_t* b) { return (uint16_t)(b[0]|(b[1]<<8)); }
static float    uf32 (uint8_t* b) { float v; memcpy(&v,b,4); return v; }

// ═══════════════════════════════════════════════
// SINH DỮ LIỆU GIẢ — MÔ PHỎNG VẬT LÝ
// ═══════════════════════════════════════════════

/**
 * MSG #0 — HEARTBEAT (9 bytes)
 * Payload: custom_mode(u32), type(u8), autopilot(u8),
 *          base_mode(u8), system_status(u8), mavlink_version(u8)
 */
void send_heartbeat() {
  uint8_t p[9] = {};
  pu32(p+0, 19);                          // custom_mode=19 (MANUAL)
  p[4] = 12;                              // MAV_TYPE_SUBMARINE
  p[5] = 3;                               // MAV_AUTOPILOT_ARDUPILOTMEGA
  p[6] = is_armed ? 0x89 : 0x01;         // base_mode: ARMED flag = bit7
  p[7] = 4;                               // MAV_STATE_ACTIVE
  p[8] = 3;                               // mavlink_version
  mav_send(MSG_HEARTBEAT, p, 9);
}

/**
 * MSG #1 — SYS_STATUS (31 bytes)
 * Pin Li-Ion 4S mô phỏng giảm dần 16.8V → 12.8V trong 2h
 */
void send_sys_status() {
  float t  = millis() / 1000.0f;
  float v  = 16.8f - (t / 7200.0f) * 4.0f;
  v = max(12.0f, v);
  float i  = is_armed ? (5.0f + 2.0f * fabsf(sinf(t * 0.5f))) : 0.5f;
  int   pct = (int)((v - 12.0f) / 4.8f * 100.0f);
  pct = constrain(pct, 0, 100);

  uint8_t p[31] = {};
  pu32(p+0,  0);                          // sensors_present (bỏ trống)
  pu32(p+4,  0);                          // sensors_enabled
  pu32(p+8,  0);                          // sensors_health
  pu16(p+12, 200);                        // load 20%
  pu16(p+14, (uint16_t)(v * 1000));       // voltage_battery mV
  pi16(p+16, (int16_t)(i * 100));         // current_battery cA
  // p[18..29] = errors, drop_rate → giữ 0
  p[30] = (uint8_t)pct;                   // battery_remaining %
  mav_send(MSG_SYS_STATUS, p, 31);
}

/**
 * MSG #29 — SCALED_PRESSURE (14 bytes)
 * Tính từ độ sâu giả, thêm noise nhỏ
 * press_abs = P_atm + ρ·g·depth (đơn vị hPa)
 */
void send_scaled_pressure(float depth_m) {
  float t  = millis() / 1000.0f;
  float tc = 25.0f - depth_m * 0.2f;
  // 1 m nước biển ≈ 0.098066 bar = 98.066 hPa
  float pa = 1013.25f + depth_m * 98.0665f
           + 0.02f * (sinf(t * 13.7f));  // noise HF nhỏ

  uint8_t p[14] = {};
  pu32(p+0, (uint32_t)millis());
  pf32(p+4, pa);
  pf32(p+8, 0.0f);                        // press_diff = 0
  pi16(p+12, (int16_t)(tc * 100));        // temperature cdegC
  mav_send(MSG_SCALED_PRESSURE, p, 14);
}

/**
 * MSG #30 — ATTITUDE (28 bytes)
 * Roll/Pitch dao động sin, Yaw quay liên tục
 * + noise nhỏ mô phỏng IMU thực tế
 */
void send_attitude() {
  float t = millis() / 1000.0f;
  // Tư thế cơ bản
  float roll  = 0.15f * sinf(t * 0.50f);
  float pitch = 0.10f * sinf(t * 0.30f + 1.0f);
  float yaw   = fmodf(t * 0.15f, 2.0f * PI);
  // Noise IMU (Gaussian xấp xỉ bằng sin tần số cao)
  float nr = 0.003f * sinf(t * 97.3f);
  float np = 0.003f * sinf(t * 113.7f);
  // Tốc độ góc (đạo hàm + noise)
  float p = 0.15f * 0.50f * cosf(t * 0.50f) + 0.005f * sinf(t * 73.1f);
  float q = 0.10f * 0.30f * cosf(t * 0.30f) + 0.003f * sinf(t * 89.3f);
  float r = 0.15f + 0.002f * sinf(t * 61.7f);

  uint8_t buf[28] = {};
  pu32(buf+0,  (uint32_t)millis());
  pf32(buf+4,  roll + nr);
  pf32(buf+8,  pitch + np);
  pf32(buf+12, yaw);
  pf32(buf+16, p);
  pf32(buf+20, q);
  pf32(buf+24, r);
  mav_send(MSG_ATTITUDE, buf, 28);
}

/**
 * MSG #32 — LOCAL_POSITION_NED (28 bytes)
 * ROV đi vòng tròn R=5m, chìm dần 0.5–4.5m
 */
float pos_x = 0, pos_y = 0, pos_z = 0;

void send_local_position_ned() {
  float t  = millis() / 1000.0f;
  float R  = 5.0f;     // bán kính vòng (m)
  float om = 0.10f;    // tốc độ góc (rad/s) → chu kỳ ~63s

  pos_x = R * cosf(om * t);
  pos_y = R * sinf(om * t);
  pos_z = 2.5f + 2.0f * sinf(0.05f * t);  // 0.5–4.5m

  float vx = -R * om * sinf(om * t);
  float vy =  R * om * cosf(om * t);
  float vz =  0.1f * cosf(0.05f * t);

  // Noise SLAM nhỏ
  float nx = 0.01f * sinf(t * 53.3f);
  float ny = 0.01f * sinf(t * 67.1f);

  uint8_t p[28] = {};
  pu32(p+0,  (uint32_t)millis());
  pf32(p+4,  pos_x + nx);
  pf32(p+8,  pos_y + ny);
  pf32(p+12, pos_z);
  pf32(p+16, vx);
  pf32(p+20, vy);
  pf32(p+24, vz);
  mav_send(MSG_LOCAL_POS_NED, p, 28);
}

/**
 * MSG #74 — VFR_HUD (20 bytes)
 */
void send_vfr_hud() {
  float t    = millis() / 1000.0f;
  float yaw  = fmodf(t * 0.15f, 2.0f * PI);
  float speed = 5.0f * 0.10f;            // v = R·ω
  int16_t  hdg = (int16_t)(fmodf(yaw * 57.2958f + 360.0f, 360.0f));
  uint16_t thr = is_armed ? 30 : 0;

  uint8_t p[20] = {};
  pf32(p+0,  speed);
  pf32(p+4,  speed);
  pf32(p+8,  -pos_z);    // alt = -depth (m)
  pf32(p+12, 0.0f);      // climb
  pi16(p+16, hdg);
  pu16(p+18, thr);
  mav_send(MSG_VFR_HUD, p, 20);
}

/**
 * MSG #251 — NAMED_VALUE_FLOAT (18 bytes)
 * Gửi cảm biến ngoại vi theo tên
 */
void send_named(const char* name, float value) {
  uint8_t p[18] = {};
  pu32(p+0, (uint32_t)millis());
  pf32(p+4, value);
  memset(p+8, 0, 10);
  strncpy((char*)(p+8), name, 10);
  mav_send(MSG_NAMED_VALUE_FLOAT, p, 18);
}

/**
 * MSG #77 — COMMAND_ACK (3 bytes)
 */
void send_cmd_ack(uint16_t cmd, uint8_t result) {
  uint8_t p[3] = {};
  pu16(p+0, cmd);
  p[2] = result;
  mav_send(MSG_COMMAND_ACK, p, 3);
}

// ═══════════════════════════════════════════════
// NHẬN VÀ PARSE MAVLink TỪ Pi (lệnh GCS)
// ═══════════════════════════════════════════════
/*
 * mavlink-router của BlueOS tự động forward lệnh từ GCS
 * xuống UART → ESP32 nhận qua Serial.read()
 * 
 * Frame MAVLink V1:
 *   [0xFE][LEN][SEQ][SYS][COMP][MSGID][PAYLOAD...][CRC_LO][CRC_HI]
 */
static uint8_t rx_buf[280];
static uint8_t rx_idx = 0;
static uint8_t rx_plen = 0;

typedef enum { ST_IDLE, ST_HDR, ST_PAYLOAD } RxState;
static RxState rx_state = ST_IDLE;

static void parse_msg(uint8_t msg_id, uint8_t* payload) {
  if (msg_id == 69) {  // MANUAL_CONTROL
    // Payload V1: x(i16), y(i16), z(u16), r(i16), buttons(u16), target(u8)
    cmd_x       = ui16s(payload+0);
    cmd_y       = ui16s(payload+2);
    cmd_z       = ui16u(payload+4);
    cmd_r       = ui16s(payload+6);
    cmd_buttons = ui16u(payload+8);
    // Nháy LED báo nhận lệnh
    digitalWrite(LED_PIN, !digitalRead(LED_PIN));

  } else if (msg_id == MSG_COMMAND_LONG) {
    // Payload: param1..7 (7×float = 28 bytes), command(u16), target_sys(u8),
    //          target_comp(u8), confirmation(u8) → total 33 bytes
    uint16_t cmd = ui16u(payload + 28);
    float p1 = uf32(payload + 0);   // param1

    if (cmd == 400) {  // MAV_CMD_COMPONENT_ARM_DISARM
      is_armed = (p1 >= 1.0f);
      digitalWrite(LED_PIN, is_armed ? HIGH : LOW);
      send_cmd_ack(400, 0);   // 0 = MAV_RESULT_ACCEPTED

    } else if (cmd == 176) {  // MAV_CMD_DO_SET_MODE
      send_cmd_ack(176, 0);

    } else if (cmd == 20) {   // MAV_CMD_NAV_RETURN_TO_LAUNCH
      is_armed = false;
      digitalWrite(LED_PIN, LOW);
      send_cmd_ack(20, 0);

    } else {
      send_cmd_ack(cmd, 3);   // 3 = MAV_RESULT_TEMPORARILY_REJECTED
    }
  }
}

static void process_byte(uint8_t b) {
  switch (rx_state) {
    case ST_IDLE:
      if (b == MAV_STX) {
        rx_buf[0] = b;
        rx_idx    = 1;
        rx_state  = ST_HDR;
      }
      break;

    case ST_HDR:
      rx_buf[rx_idx++] = b;
      if (rx_idx == 6) {
        rx_plen  = rx_buf[1];
        rx_state = ST_PAYLOAD;
      }
      break;

    case ST_PAYLOAD:
      rx_buf[rx_idx++] = b;
      // Frame đầy: 6 header + plen payload + 2 CRC
      if (rx_idx >= (6 + rx_plen + 2)) {
        uint8_t msg_id = rx_buf[5];
        parse_msg(msg_id, rx_buf + 6);
        rx_state = ST_IDLE;
      }
      break;
  }
}

// ═══════════════════════════════════════════════
// SETUP & LOOP
// ═══════════════════════════════════════════════
void setup() {
  // Serial = UART0 (USB hoặc GPIO1/GPIO3) → dùng để giao tiếp MAVLink với Pi
  Serial.begin(UART_BAUD);

  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  // Nháy LED 2 lần: sẵn sàng
  for (int i = 0; i < 2; i++) {
    digitalWrite(LED_PIN, HIGH); delay(200);
    digitalWrite(LED_PIN, LOW);  delay(200);
  }

  // Log ra Serial2 nếu muốn debug (cần dây nối thêm)
  // Serial2.begin(115200);  // GPIO16(RX2), GPIO17(TX2)
  // Serial2.println("[ESP32] MAVLink UART ready");
}

unsigned long t_hb   = 0;
unsigned long t_att  = 0;
unsigned long t_pos  = 0;
unsigned long t_sys  = 0;
unsigned long t_sens = 0;

void loop() {
  unsigned long now = millis();

  // ── NHẬN LỆNH TỪ Pi (mavlink-router forward từ GCS) ──
  while (Serial.available()) {
    process_byte((uint8_t)Serial.read());
  }

  // ── GỬI TELEMETRY ──

  // 1 Hz — HEARTBEAT (bắt buộc)
  if (now - t_hb >= 1000) {
    send_heartbeat();
    t_hb = now;
  }

  // 50 Hz — ATTITUDE (quan trọng nhất, cần mượt)
  if (now - t_att >= 20) {
    send_attitude();
    t_att = now;
  }

  // 10 Hz — Áp suất + Vị trí + HUD
  if (now - t_pos >= 100) {
    send_local_position_ned();
    send_scaled_pressure(pos_z);
    send_vfr_hud();
    t_pos = now;
  }

  // 2 Hz — Pin
  if (now - t_sys >= 500) {
    send_sys_status();
    t_sys = now;
  }

  // 5 Hz — Cảm biến ngoại vi
  if (now - t_sens >= 200) {
    float t_s = millis() / 1000.0f;
    float water_temp = 25.0f - pos_z * 0.2f + 0.1f * sinf(t_s * 0.05f);
    send_named("TEMP", water_temp);
    send_named("LEAK", 0.0f);  // 0 = không rò nước
    t_sens = now;
  }
}
