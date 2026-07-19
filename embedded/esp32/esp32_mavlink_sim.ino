/**
 * esp32_mavlink_sim.ino
 * =====================
 * ESP32 DevKit V1 — Gia lap ROV gui MAVLink len GCS
 * 
 * CHON CHE DO TRUYEN:
 *   #define MODE_WIFI   → ESP32 gui UDP truc tiep den GCS (khong can Pi)
 *   #define MODE_UART   → ESP32 gui qua UART den Pi bridge
 * 
 * DU LIEU GIA LAP (khong can cam bien):
 *   - HEARTBEAT    1 Hz
 *   - ATTITUDE     50 Hz  (roll/pitch/yaw dao dong sin)
 *   - SYS_STATUS   2 Hz   (pin giam dan theo thoi gian)
 *   - SCALED_PRESSURE 10 Hz (ap suat tinh tu do sau gia)
 *   - LOCAL_POS_NED   10 Hz (ROV di chuyen theo quy dao vong tron)
 *   - VFR_HUD         10 Hz
 *   - NAMED_VALUE_FLOAT 5 Hz (TEMP, LEAK)
 * 
 * NHAN LENH TU GCS:
 *   - MANUAL_CONTROL → Nhap nháy LED_BUILTIN
 *   - ARM/DISARM     → LED sang/tat
 * 
 * CAP NHAT WIFI:
 *   Doi WIFI_SSID, WIFI_PASS, GCS_IP cho phu hop mang cua ban
 * 
 * WIRING UART (Mode B):
 *   ESP32 TX (GPIO1)  → Pi RX  (/dev/ttyUSB0)
 *   ESP32 RX (GPIO3)  → Pi TX
 *   ESP32 GND         → Pi GND
 *   Baud: 115200
 * 
 * THU VIEN CAN:
 *   Board: esp32 by Espressif (Arduino IDE Board Manager)
 *   Khong can thu vien ngoai (MAVLink tu xay dung thu cong)
 */

// ═══════════════════════════════════════════════
// CHON CHE DO TRUYEN — Chinh o day
// ═══════════════════════════════════════════════
#define MODE_WIFI      // Dung WiFi (khong can Pi, test nhanh)
// #define MODE_UART   // Dung UART → Pi bridge (comment dong tren di)

// ═══════════════════════════════════════════════
// CAU HINH WIFI (chi can khi MODE_WIFI)
// ═══════════════════════════════════════════════
#ifdef MODE_WIFI
  #include <WiFi.h>
  #include <WiFiUDP.h>

  const char* WIFI_SSID = "YOUR_WIFI_SSID";   // <-- doi o day
  const char* WIFI_PASS = "YOUR_WIFI_PASS";   // <-- doi o day
  const char* GCS_IP    = "192.168.1.100";    // <-- IP may tinh chay GCS
  const int   GCS_PORT  = 14550;

  WiFiUDP udp;
  // Buffer nhan UDP tu GCS (lenh dieu khien)
  uint8_t udp_rx_buf[512];
#endif

// ═══════════════════════════════════════════════
// CAU HINH UART (chi can khi MODE_UART)
// ═══════════════════════════════════════════════
#ifdef MODE_UART
  #define UART_BAUD 115200
  // Su dung Serial (USB/UART0) de truyen MAVLink den Pi
  // ESP32 DevKit: TX=GPIO1, RX=GPIO3
#endif

// ═══════════════════════════════════════════════
// HANG SO MAVLink
// ═══════════════════════════════════════════════
#define MAV_SYS_ID    1     // ROV System ID
#define MAV_COMP_ID   1     // Autopilot component
#define MAV_STX_V1    0xFE  // MAVLink V1 start byte

// MAVLink Message IDs
#define MSG_HEARTBEAT         0
#define MSG_SYS_STATUS        1
#define MSG_SCALED_PRESSURE   29
#define MSG_ATTITUDE          30
#define MSG_LOCAL_POS_NED     32
#define MSG_VFR_HUD           74
#define MSG_MANUAL_CONTROL    69
#define MSG_COMMAND_LONG      76
#define MSG_COMMAND_ACK       77
#define MSG_NAMED_VALUE_FLOAT 251

// CRC_EXTRA cho tung loai message
const uint8_t CRC_EXTRA[] = {
  [0]   = 50,    // HEARTBEAT
  [1]   = 124,   // SYS_STATUS
  [29]  = 115,   // SCALED_PRESSURE
  [30]  = 39,    // ATTITUDE
  [32]  = 185,   // LOCAL_POSITION_NED
  [69]  = 243,   // MANUAL_CONTROL
  [74]  = 20,    // VFR_HUD
  [76]  = 152,   // COMMAND_LONG
  [77]  = 143,   // COMMAND_ACK
  [251] = 170,   // NAMED_VALUE_FLOAT
};

// ═══════════════════════════════════════════════
// TRANG THAI CHUNG
// ═══════════════════════════════════════════════
static uint8_t  mav_seq   = 0;
static bool     is_armed  = false;
static int16_t  cmd_x     = 0;
static int16_t  cmd_y     = 0;
static uint16_t cmd_z     = 500;
static int16_t  cmd_r     = 0;

#define LED_PIN  2   // LED_BUILTIN cua DevKit V1

// ═══════════════════════════════════════════════
// CRC X25
// ═══════════════════════════════════════════════
static void crc_acc(uint8_t d, uint16_t* crc) {
  uint8_t tmp = d ^ (uint8_t)(*crc & 0xFF);
  tmp ^= (tmp << 4);
  *crc = (*crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4);
}

static uint16_t crc_calc(uint8_t* data, uint8_t len, uint8_t extra) {
  uint16_t crc = 0xFFFF;
  for (int i = 0; i < len; i++) crc_acc(data[i], &crc);
  crc_acc(extra, &crc);
  return crc;
}

// ═══════════════════════════════════════════════
// GUI GOI MAVLink V1
// ═══════════════════════════════════════════════
static void mav_send(uint8_t msg_id, uint8_t* payload, uint8_t plen) {
  uint8_t header[6];
  header[0] = MAV_STX_V1;
  header[1] = plen;
  header[2] = mav_seq++;
  header[3] = MAV_SYS_ID;
  header[4] = MAV_COMP_ID;
  header[5] = msg_id;

  // Tinh CRC: tu byte 1 (LEN) den het header + payload + crc_extra
  uint16_t crc = 0xFFFF;
  for (int i = 1; i < 6; i++) crc_acc(header[i], &crc);
  for (int i = 0; i < plen; i++) crc_acc(payload[i], &crc);
  uint8_t ce = (msg_id < 252) ? CRC_EXTRA[msg_id] : 0;
  crc_acc(ce, &crc);

  uint8_t crc_lo = crc & 0xFF;
  uint8_t crc_hi = (crc >> 8) & 0xFF;

#ifdef MODE_WIFI
  udp.beginPacket(GCS_IP, GCS_PORT);
  udp.write(header, 6);
  udp.write(payload, plen);
  udp.write(crc_lo);
  udp.write(crc_hi);
  udp.endPacket();
#endif

#ifdef MODE_UART
  Serial.write(header, 6);
  Serial.write(payload, plen);
  Serial.write(crc_lo);
  Serial.write(crc_hi);
#endif
}

// ═══════════════════════════════════════════════
// TIEN ICH PACK FLOAT / UINT / INT VBAO BUFFER
// ═══════════════════════════════════════════════
static inline void pack_u32(uint8_t* buf, uint32_t v) {
  buf[0]=v; buf[1]=v>>8; buf[2]=v>>16; buf[3]=v>>24;
}
static inline void pack_i16(uint8_t* buf, int16_t v) {
  buf[0]=v; buf[1]=v>>8;
}
static inline void pack_u16(uint8_t* buf, uint16_t v) {
  buf[0]=v; buf[1]=v>>8;
}
static inline void pack_f32(uint8_t* buf, float v) {
  uint32_t bits; memcpy(&bits, &v, 4);
  pack_u32(buf, bits);
}

static inline int16_t unpack_i16(uint8_t* buf) {
  return (int16_t)(buf[0] | (buf[1]<<8));
}
static inline uint16_t unpack_u16(uint8_t* buf) {
  return (uint16_t)(buf[0] | (buf[1]<<8));
}
static inline uint32_t unpack_u32(uint8_t* buf) {
  return (uint32_t)(buf[0]|(buf[1]<<8)|(buf[2]<<16)|(buf[3]<<24));
}

// ═══════════════════════════════════════════════
// CAC HAM SINH DU LIEU GIA VA GUI MAVLink
// ═══════════════════════════════════════════════

// MSG #0 HEARTBEAT
void send_heartbeat() {
  uint8_t payload[9] = {};
  pack_u32(payload+0, 19);          // custom_mode=19 (MANUAL)
  payload[4] = 12;                   // type=MAV_TYPE_SUBMARINE
  payload[5] = 3;                    // autopilot=ARDUPILOT
  payload[6] = is_armed ? 0x89 : 0x01; // base_mode: ARMED or not
  payload[7] = 4;                    // system_status=ACTIVE
  payload[8] = 3;                    // mavlink_version
  mav_send(MSG_HEARTBEAT, payload, 9);
}

// MSG #1 SYS_STATUS — pin giam dan theo thoi gian
void send_sys_status() {
  float t_sec = millis() / 1000.0f;
  float volt  = 16.8f - (t_sec / 7200.0f) * 4.0f;  // 16.8V → 12.8V trong 2h
  volt  = max(12.0f, volt);
  float curr  = is_armed ? (5.0f + 2.0f * fabsf(sinf(t_sec * 0.5f))) : 0.5f;
  int   pct   = (int)((volt - 12.0f) / (16.8f - 12.0f) * 100.0f);
  pct = constrain(pct, 0, 100);

  uint8_t payload[31] = {};
  pack_u32(payload+0,  0);                      // sensors_present
  pack_u32(payload+4,  0);                      // sensors_enabled
  pack_u32(payload+8,  0);                      // sensors_health
  pack_u16(payload+12, 200);                    // load 20%
  pack_u16(payload+14, (uint16_t)(volt*1000));  // voltage_battery mV
  pack_i16(payload+16, (int16_t)(curr*100));    // current_battery cA
  pack_u16(payload+18, 0);                      // drop_rate_comm
  // errors x4 = 0
  payload[30] = (uint8_t)pct;                   // battery_remaining %
  mav_send(MSG_SYS_STATUS, payload, 31);
}

// MSG #29 SCALED_PRESSURE — tu do sau gia
void send_scaled_pressure(float depth_m) {
  float t_sec   = millis() / 1000.0f;
  float temp_c  = 25.0f - depth_m * 0.2f + 0.05f * sinf(t_sec * 0.1f);
  float press   = 1013.25f + depth_m * 98.0665f
                  + 0.02f * ((float)random(-100,100)/100.0f);  // noise nhỏ

  uint8_t payload[14] = {};
  pack_u32(payload+0, millis());
  pack_f32(payload+4, press);
  pack_f32(payload+8, 0.0f);                      // press_diff
  pack_i16(payload+12, (int16_t)(temp_c * 100)); // temperature cdegC
  mav_send(MSG_SCALED_PRESSURE, payload, 14);
}

// MSG #30 ATTITUDE — dao dong sin gia lap IMU
void send_attitude() {
  float t = millis() / 1000.0f;
  float roll  = 0.15f  * sinf(t * 0.5f)  + 0.003f * ((float)random(-100,100)/100.0f);
  float pitch = 0.10f  * sinf(t * 0.3f + 1.0f) + 0.003f * ((float)random(-100,100)/100.0f);
  float yaw   = fmod(t * 0.15f, 2.0f * PI);

  uint8_t payload[28] = {};
  pack_u32(payload+0,  millis());
  pack_f32(payload+4,  roll);
  pack_f32(payload+8,  pitch);
  pack_f32(payload+12, yaw);
  pack_f32(payload+16, 0.005f * sinf(t));  // rollspeed
  pack_f32(payload+20, 0.003f * cosf(t));  // pitchspeed
  pack_f32(payload+24, 0.15f);             // yawspeed
  mav_send(MSG_ATTITUDE, payload, 28);
}

// MSG #32 LOCAL_POSITION_NED — vong tron ban kinh 5m
void send_local_position_ned(float* pos_x, float* pos_y, float* pos_z) {
  float t = millis() / 1000.0f;
  float R = 5.0f;      // ban kinh vong tron (m)
  float omega = 0.1f;  // toc do goc (rad/s)

  *pos_x = R * cosf(omega * t);
  *pos_y = R * sinf(omega * t);
  *pos_z = 2.5f + 2.0f * sinf(0.05f * t);  // do sau 0.5-4.5m

  float vx = -R * omega * sinf(omega * t);
  float vy =  R * omega * cosf(omega * t);
  float vz =  0.1f * cosf(0.05f * t);

  uint8_t payload[28] = {};
  pack_u32(payload+0,  millis());
  pack_f32(payload+4,  *pos_x);
  pack_f32(payload+8,  *pos_y);
  pack_f32(payload+12, *pos_z);
  pack_f32(payload+16, vx);
  pack_f32(payload+20, vy);
  pack_f32(payload+24, vz);
  mav_send(MSG_LOCAL_POS_NED, payload, 28);
}

// MSG #74 VFR_HUD
void send_vfr_hud(float depth_m, float yaw_rad, float speed_ms) {
  int16_t  hdg      = (int16_t)(fmod(yaw_rad * 57.2958f + 360.0f, 360.0f));
  uint16_t throttle = is_armed ? (uint16_t)(abs(cmd_x)/10) : 0;

  uint8_t payload[20] = {};
  pack_f32(payload+0,  speed_ms);
  pack_f32(payload+4,  speed_ms);
  pack_f32(payload+8,  -depth_m);   // alt = negative depth
  pack_f32(payload+12, 0.0f);       // climb
  pack_i16(payload+16, hdg);
  pack_u16(payload+18, throttle);
  mav_send(MSG_VFR_HUD, payload, 20);
}

// MSG #251 NAMED_VALUE_FLOAT
void send_named_float(const char* name, float value) {
  uint8_t payload[18] = {};
  pack_u32(payload+0, millis());
  pack_f32(payload+4, value);
  // name: 10 bytes, null-padded
  memset(payload+8, 0, 10);
  strncpy((char*)(payload+8), name, 10);
  mav_send(MSG_NAMED_VALUE_FLOAT, payload, 18);
}

// MSG #77 COMMAND_ACK
void send_cmd_ack(uint16_t cmd, uint8_t result) {
  uint8_t payload[3] = {};
  pack_u16(payload+0, cmd);
  payload[2] = result;
  mav_send(MSG_COMMAND_ACK, payload, 3);
}

// ═══════════════════════════════════════════════
// PARSE GOI NHAN TU GCS
// ═══════════════════════════════════════════════
// Buffer nhan MAVLink byte-by-byte
static uint8_t rx_buf[280];
static int     rx_len = 0;
static enum { WAIT_STX, WAIT_LEN, WAIT_PAYLOAD } rx_state = WAIT_STX;
static uint8_t rx_plen = 0;

void process_rx_byte(uint8_t b) {
  switch(rx_state) {
    case WAIT_STX:
      if (b == MAV_STX_V1) { rx_buf[0]=b; rx_len=1; rx_state=WAIT_LEN; }
      break;
    case WAIT_LEN:
      rx_buf[rx_len++] = b;
      rx_plen = b;
      rx_state = WAIT_PAYLOAD;
      break;
    case WAIT_PAYLOAD:
      rx_buf[rx_len++] = b;
      // Total frame: STX(1)+LEN(1)+SEQ(1)+SYS(1)+COMP(1)+MSGID(1)+PAYLOAD(plen)+CRC(2)
      if (rx_len >= (6 + rx_plen + 2)) {
        parse_frame(rx_buf, rx_len);
        rx_state = WAIT_STX;
      }
      break;
  }
}

void parse_frame(uint8_t* frame, int len) {
  if (len < 8) return;
  uint8_t msg_id  = frame[5];
  uint8_t* payload = frame + 6;

  if (msg_id == MSG_MANUAL_CONTROL) {
    // x, y, z, r, buttons (LE), target
    cmd_x = unpack_i16(payload+0);
    cmd_y = unpack_i16(payload+2);
    cmd_z = unpack_u16(payload+4);
    cmd_r = unpack_i16(payload+6);
    // Nháy LED khi nhan duoc lenh dieu khien
    digitalWrite(LED_PIN, !digitalRead(LED_PIN));

  } else if (msg_id == MSG_COMMAND_LONG) {
    uint16_t cmd = unpack_u16(payload+24);  // command ở byte 24-25 (float x6 = 24 bytes)
    float p1;
    memcpy(&p1, payload, 4);

    if (cmd == 400) {  // ARM/DISARM
      is_armed = (p1 == 1.0f);
      digitalWrite(LED_PIN, is_armed ? HIGH : LOW);
      Serial.printf("[ESP32] %s!\n", is_armed ? "ARMED" : "DISARMED");
      send_cmd_ack(400, 0);
    } else if (cmd == 176) {  // SET_MODE
      send_cmd_ack(176, 0);
    } else {
      send_cmd_ack(cmd, 0);
    }
  }
}

// ═══════════════════════════════════════════════
// SETUP & LOOP
// ═══════════════════════════════════════════════
void setup() {
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

#ifdef MODE_UART
  Serial.begin(UART_BAUD);
  Serial.println("[ESP32] MAVLink UART mode — 115200 baud");
#endif

#ifdef MODE_WIFI
  // Debug tren Serial (cung la USB, nhung chi truoc khi gui MAVLink)
  // MAVLink gui qua UDP nen khong xung dot voi Serial debug
  Serial.begin(115200);
  Serial.printf("[ESP32] Connecting WiFi: %s\n", WIFI_SSID);

  WiFi.begin(WIFI_SSID, WIFI_PASS);
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[ESP32] WiFi OK! IP: %s\n", WiFi.localIP().toString().c_str());
    Serial.printf("[ESP32] Sending MAVLink to %s:%d\n", GCS_IP, GCS_PORT);
    udp.begin(14551);  // listen port cho lenh tu GCS
    // Nháy LED 3 lan bao ket noi thanh cong
    for (int i=0; i<3; i++) {
      digitalWrite(LED_PIN, HIGH); delay(100);
      digitalWrite(LED_PIN, LOW);  delay(100);
    }
  } else {
    Serial.println("\n[ESP32] WiFi FAILED! Kiem tra SSID/PASS");
    // Nhay LED nhanh bao loi
    while(1) { digitalWrite(LED_PIN,HIGH); delay(50); digitalWrite(LED_PIN,LOW); delay(50); }
  }
#endif
}

// Timer
unsigned long t_hb   = 0;  // heartbeat    1Hz  = 1000ms
unsigned long t_att  = 0;  // attitude     50Hz = 20ms
unsigned long t_press= 0;  // pressure     10Hz = 100ms
unsigned long t_pos  = 0;  // position     10Hz = 100ms
unsigned long t_sys  = 0;  // sys_status   2Hz  = 500ms
unsigned long t_sens = 0;  // sensors      5Hz  = 200ms

float pos_x=0, pos_y=0, pos_z=0;

void loop() {
  unsigned long now = millis();

  // ─── NHAN LENH TU GCS ───
#ifdef MODE_WIFI
  int pkt = udp.parsePacket();
  if (pkt > 0) {
    int n = udp.read(udp_rx_buf, sizeof(udp_rx_buf));
    for (int i=0; i<n; i++) process_rx_byte(udp_rx_buf[i]);
  }
#endif
#ifdef MODE_UART
  while (Serial.available()) process_rx_byte(Serial.read());
#endif

  // ─── GUI TELEMETRY ───

  // 1 Hz — HEARTBEAT
  if (now - t_hb >= 1000) {
    send_heartbeat();
    t_hb = now;
    Serial.printf("[ESP32] HB | Armed:%d | Depth:%.1fm | Cmd:(%d,%d,%d,%d)\n",
                  is_armed, pos_z, cmd_x, cmd_y, cmd_z, cmd_r);
  }

  // 50 Hz — ATTITUDE
  if (now - t_att >= 20) {
    send_attitude();
    t_att = now;
  }

  // 10 Hz — PRESSURE + POSITION + VFR_HUD
  if (now - t_press >= 100) {
    send_local_position_ned(&pos_x, &pos_y, &pos_z);
    send_scaled_pressure(pos_z);
    float t_s = millis()/1000.0f;
    float yaw = fmod(t_s * 0.15f, 2*PI);
    float spd = 0.5f * (abs(cmd_x) + abs(cmd_y)) / 1000.0f;
    send_vfr_hud(pos_z, yaw, spd);
    t_press = now;
  }

  // 2 Hz — SYS_STATUS
  if (now - t_sys >= 500) {
    send_sys_status();
    t_sys = now;
  }

  // 5 Hz — CAM BIEN NGOAI VI
  if (now - t_sens >= 200) {
    float t_s = millis()/1000.0f;
    float water_temp = 25.0f - pos_z * 0.2f + 0.1f * sinf(t_s * 0.05f);
    send_named_float("TEMP", water_temp);
    send_named_float("LEAK", 0.0f);  // 0 = khong ro nuoc
    t_sens = now;
  }
}
