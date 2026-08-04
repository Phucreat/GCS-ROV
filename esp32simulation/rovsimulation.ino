/**
 * esp32_mavlink_v2_wifi_udp.ino
 * =======================
 * Trình giả lập ROV Hardware-in-the-Loop (HIL) trên ESP32.
 * Tích hợp mô hình động học (Kinematic Model) nhận lệnh điều khiển thật từ GCS.
 */

#include <Arduino.h>
#include <math.h>
#include <WiFi.h>
#include <WiFiUdp.h>

#define MAVLINK_USE_MESSAGE_INFO
// Dùng ngoặc kép "" để trỏ trực tiếp vào thư mục local
#include "mavlink/common/mavlink.h"

// ═══════════════════════════════════════════════
// CẤU HÌNH MẠNG WI-FI & UDP
// ═══════════════════════════════════════════════
const char* ssid     = "amrrobot";       // Thay bằng tên Wi-Fi của bạn
const char* password = "44668899";       // Thay bằng mật khẩu Wi-Fi

// IP & Cổng GCS (Tự động cập nhật IP của Laptop ngay khi nhận gói tin đầu tiên)
IPAddress targetIP(192, 168, 2, 10);    // IP mặc định fallback
uint16_t targetPort = 14550;             // Cổng GCS lắng nghe (14550)
const uint16_t localPort  = 14550;       // Cổng ESP32 lắng nghe lệnh

WiFiUDP udp;

// ═══════════════════════════════════════════════
// CẤU HÌNH ROV
// ═══════════════════════════════════════════════
#define MAV_SYS_ID   1            // System ID của ROV
#define MAV_COMP_ID  1            // Component: Autopilot
#define LED_PIN      2            // LED_BUILTIN ESP32 DevKit V1

// ═══════════════════════════════════════════════
// TRẠNG THÁI VÀ BIẾN MÔ PHỎNG VẬT LÝ ESP32
// ═══════════════════════════════════════════════
static bool     is_armed  = true; // Mặc định MỞ ARM cho mô hình giả lập
static int16_t  cmd_x     = 0;    // Tiến/Lùi (-1000 đến 1000)
static int16_t  cmd_y     = 0;    // Trái/Phải (-1000 đến 1000)
static int16_t  cmd_z     = 500;  // Lên/Xuống (Sửa int16_t tránh tràn số)
static int16_t  cmd_r     = 0;    // Xoay Yaw (-1000 đến 1000)
static uint16_t cmd_buttons = 0;

// Các biến động học (Hệ quy chiếu World / NED)
float pos_x = 0, pos_y = 0, pos_z = 0; // Vị trí (m)
float vel_x = 0, vel_y = 0, vel_z = 0; // Vận tốc tuyến tính (m/s)
float roll  = 0, pitch = 0, yaw   = 0; // Tư thế (Radian)
float yaw_rate = 0;                    // Vận tốc xoay (rad/s)

// Hệ số vật lý mô phỏng môi trường nước
const float MAX_ACCEL = 2.0f;       // Gia tốc tối đa (m/s^2)
const float MAX_YAW_ACCEL = 1.5f;   // Gia tốc xoay tối đa (rad/s^2)
const float WATER_DRAG = 2.5f;      // Lực cản tuyến tính của nước
const float ROT_DRAG = 3.0f;        // Lực cản xoay của nước
const float RESTORING_FORCE = 5.0f; // Lực tự cân bằng (do CB > CG)

// Biến lưu thời gian để điều phối tần số gửi (Hz)
unsigned long t_hb   = 0; 
unsigned long t_att  = 0; 
unsigned long t_pos  = 0; 
unsigned long t_sys  = 0; 
unsigned long t_sens = 0; 
unsigned long t_physics = 0; // Thời gian cập nhật vật lý

// ═══════════════════════════════════════════════
// HÀM TIỆN ÍCH ĐỂ GỬI GÓI TIN MAVLINK V2 QUA UDP
// ═══════════════════════════════════════════════
void send_mavlink_message(mavlink_message_t* msg) { 
  uint8_t buf[MAVLINK_MAX_PACKET_LEN]; 
  uint16_t len = mavlink_msg_to_send_buffer(buf, msg); 
  
  udp.beginPacket(targetIP, targetPort); 
  udp.write(buf, len); 
  udp.endPacket(); 
} 

// ═══════════════════════════════════════════════
// HÀM TÍNH TOÁN ĐỘNG HỌC THỜI GIAN THỰC (50Hz)
// ═══════════════════════════════════════════════
void update_physics(float dt) {
  // 1. Chuẩn hóa lệnh đầu vào từ GCS (-1.0 đến 1.0)
  float u_x = is_armed ? (cmd_x / 1000.0f) : 0.0f;
  float u_y = is_armed ? (cmd_y / 1000.0f) : 0.0f;
  float u_z = is_armed ? ((cmd_z - 500) / 500.0f) : 0.0f; // Z đi xuống là dương trong NED
  float u_r = is_armed ? (cmd_r / 1000.0f) : 0.0f;

  // 2. Cập nhật vận tốc (Có lực đẩy và lực cản của nước)
  // v = v + (Thrust - Drag * v) * dt
  vel_x += (u_x * MAX_ACCEL - WATER_DRAG * vel_x) * dt;
  vel_y += (u_y * MAX_ACCEL - WATER_DRAG * vel_y) * dt;
  vel_z += (u_z * MAX_ACCEL - WATER_DRAG * vel_z) * dt;
  yaw_rate += (u_r * MAX_YAW_ACCEL - ROT_DRAG * yaw_rate) * dt;

  // 3. Cập nhật vị trí (Chuyển đổi từ hệ Body sang hệ World NED dựa vào góc Yaw)
  pos_x += (vel_x * cosf(yaw) - vel_y * sinf(yaw)) * dt;
  pos_y += (vel_x * sinf(yaw) + vel_y * cosf(yaw)) * dt;
  pos_z += vel_z * dt;

  // Không cho tàu bay lên khỏi mặt nước (Z luôn >= 0)
  if (pos_z < 0) {
    pos_z = 0; 
    vel_z = 0;
  }

  // 4. Cập nhật Tư thế (Attitude)
  yaw += yaw_rate * dt;
  // Giữ Yaw trong khoảng 0 đến 2*PI
  if (yaw > 2.0f * PI) yaw -= 2.0f * PI;
  if (yaw < 0) yaw += 2.0f * PI;

  // ROV có trọng tâm thấp nên tự động lấy lại thăng bằng (Pendulum effect)
  float target_pitch = u_x * 0.2f; // Tiến tới thì chúi mũi nhẹ
  float target_roll  = u_y * 0.2f; // Đi ngang thì nghiêng lườn nhẹ
  
  pitch += (target_pitch - pitch) * RESTORING_FORCE * dt;
  roll  += (target_roll - roll) * RESTORING_FORCE * dt;
}

// ═══════════════════════════════════════════════
// CÁC HÀM GỬI TELEMETRY 
// ═══════════════════════════════════════════════
void send_heartbeat() { 
  mavlink_message_t msg; 
  uint8_t base_mode = is_armed ? MAV_MODE_FLAG_SAFETY_ARMED : 0; 
  
  mavlink_msg_heartbeat_pack(MAV_SYS_ID, MAV_COMP_ID, &msg, 
                             MAV_TYPE_SUBMARINE, 
                             MAV_AUTOPILOT_ARDUPILOTMEGA, 
                             base_mode, 
                             19, 
                             MAV_STATE_ACTIVE); 
  send_mavlink_message(&msg); 
} 

void send_sys_status() { 
  mavlink_message_t msg; 
  float t  = millis() / 1000.0f; 
  float v  = 16.8f - (t / 7200.0f) * 4.0f; // Giả lập hao pin dần theo thời gian
  v = max(12.0f, v); //[cite: 2]
  
  // Dòng điện (Ampe) tăng khi động cơ chạy
  float current_draw = is_armed ? (0.5f + (fabs(cmd_x) + fabs(cmd_y) + fabs(cmd_z - 500.0f)) / 1000.0f * 15.0f) : 0.5f; 

  int pct = (int)((v - 12.0f) / 4.8f * 100.0f); 
  pct = constrain(pct, 0, 100); 

  mavlink_msg_sys_status_pack(MAV_SYS_ID, MAV_COMP_ID, &msg, 
                              0, 0, 0, 
                              200, 
                              (uint16_t)(v * 1000), 
                              (int16_t)(current_draw * 100), 
                              (int8_t)pct, 
                              0, 0, 0, 0, 0, 0, 
                              0, 0, 0); 
  send_mavlink_message(&msg); 
} 

void send_scaled_pressure(float depth_m) { 
  mavlink_message_t msg; 
  float tc = 25.0f - depth_m * 0.2f; 
  float pa = 1013.25f + depth_m * 98.0665f; 

  mavlink_msg_scaled_pressure_pack(MAV_SYS_ID, MAV_COMP_ID, &msg, 
                                   (uint32_t)millis(), 
                                   pa, 
                                   0.0f, 
                                   (int16_t)(tc * 100), 
                                   0); 
  send_mavlink_message(&msg); 
} 

void send_attitude() { 
  mavlink_message_t msg; 
  mavlink_msg_attitude_pack(MAV_SYS_ID, MAV_COMP_ID, &msg, 
                            (uint32_t)millis(), 
                            roll, pitch, yaw,
                            0.0f, 0.0f, yaw_rate); 
  send_mavlink_message(&msg); 
} 

void send_local_position_ned() { 
  mavlink_message_t msg; 
  // Chuyển đổi vận tốc về hệ World NED
  float vx_ned = vel_x * cosf(yaw) - vel_y * sinf(yaw);
  float vy_ned = vel_x * sinf(yaw) + vel_y * cosf(yaw);

  mavlink_msg_local_position_ned_pack(MAV_SYS_ID, MAV_COMP_ID, &msg, 
                                      (uint32_t)millis(), 
                                      pos_x, pos_y, pos_z, 
                                      vx_ned, vy_ned, vel_z);
  send_mavlink_message(&msg); 
} 

void send_vfr_hud() { 
  mavlink_message_t msg; 
  float speed = sqrtf(vel_x * vel_x + vel_y * vel_y);
  int16_t hdg = (int16_t)(fmodf(yaw * 57.2958f + 360.0f, 360.0f));
  
  // Tính % Ga tổng hợp để hiển thị lên UI
  uint16_t thr = is_armed ? (uint16_t)(max(fabsf((float)cmd_x), fabsf((float)cmd_z - 500.0f)) / 10.0f) : 0;

  mavlink_msg_vfr_hud_pack(MAV_SYS_ID, MAV_COMP_ID, &msg, 
                           speed, speed, -pos_z, 0.0f, hdg, thr); 
  send_mavlink_message(&msg); 
} 

void send_named(const char* name, float value) { 
  mavlink_message_t msg; 
  char name_buf[10] = {0}; 
  strncpy(name_buf, name, 10); 
  
  mavlink_msg_named_value_float_pack(MAV_SYS_ID, MAV_COMP_ID, &msg, 
                                     (uint32_t)millis(), name_buf, value); 
  send_mavlink_message(&msg); 
} 

void send_cmd_ack(uint16_t cmd, uint8_t result) { 
  mavlink_message_t msg; 
  mavlink_msg_command_ack_pack(MAV_SYS_ID, MAV_COMP_ID, &msg, 
                               cmd, result, 0, 0, 0, 0); 
  send_mavlink_message(&msg); 
} 

// ═══════════════════════════════════════════════
// XỬ LÝ LỆNH NHẬN ĐƯỢC TỪ GCS
// ═══════════════════════════════════════════════
void handle_mavlink_message(mavlink_message_t* msg) { 
  switch (msg->msgid) { 
    case MAVLINK_MSG_ID_MANUAL_CONTROL: { 
      mavlink_manual_control_t manual; 
      mavlink_msg_manual_control_decode(msg, &manual); 
      cmd_x = manual.x; 
      cmd_y = manual.y; 
      cmd_z = manual.z; 
      cmd_r = manual.r; 
      cmd_buttons = manual.buttons; 
      digitalWrite(LED_PIN, !digitalRead(LED_PIN)); 
      break; 
    } 
    
    case MAVLINK_MSG_ID_COMMAND_LONG: { 
      mavlink_command_long_t cmd; 
      mavlink_msg_command_long_decode(msg, &cmd); 
      
      if (cmd.command == MAV_CMD_COMPONENT_ARM_DISARM) { 
        is_armed = (cmd.param1 >= 1.0f); 
        digitalWrite(LED_PIN, is_armed ? HIGH : LOW); 
        send_cmd_ack(MAV_CMD_COMPONENT_ARM_DISARM, MAV_RESULT_ACCEPTED); 
      } 
      else if (cmd.command == MAV_CMD_DO_SET_MODE) { 
        send_cmd_ack(MAV_CMD_DO_SET_MODE, MAV_RESULT_ACCEPTED); 
      } 
      else if (cmd.command == MAV_CMD_NAV_RETURN_TO_LAUNCH) { 
        is_armed = false; 
        digitalWrite(LED_PIN, LOW); 
        send_cmd_ack(MAV_CMD_NAV_RETURN_TO_LAUNCH, MAV_RESULT_ACCEPTED); 
      } 
      else { 
        send_cmd_ack(cmd.command, MAV_RESULT_TEMPORARILY_REJECTED); 
      } 
      break; 
    } 
  } 
} 

// ═══════════════════════════════════════════════
// SETUP & LOOP
// ═══════════════════════════════════════════════
void setup() { 
  Serial.begin(115200); 
  pinMode(LED_PIN, OUTPUT); 
  digitalWrite(LED_PIN, LOW); 

  // Kết nối Wi-Fi
  Serial.print("Connecting to Wi-Fi"); 
  WiFi.begin(ssid, password); 
  while (WiFi.status() != WL_CONNECTED) { 
    delay(500); 
    Serial.print("."); 
    digitalWrite(LED_PIN, !digitalRead(LED_PIN)); 
  } 
  
  Serial.println("\nWi-Fi Connected!"); 
  Serial.print("ESP32 IP Address: "); 
  Serial.println(WiFi.localIP()); 

  // Mở cổng UDP để lắng nghe
  udp.begin(localPort); 
  Serial.printf("Listening on UDP port %d\n", localPort); 
  
  digitalWrite(LED_PIN, HIGH); 
  delay(1000); 
  digitalWrite(LED_PIN, LOW); 
} 

void loop() { 
  unsigned long now = millis(); 

  // ── 1. ĐỌC VÀ GIẢI MÃ MAVLINK QUA UDP ──
  int packetSize = udp.parsePacket(); 
  if (packetSize) { 
    // Tự động cập nhật IP & Cổng của Laptop GCS ngay khi nhận được gói tin đầu tiên
    targetIP = udp.remoteIP();
    targetPort = udp.remotePort();

    mavlink_message_t msg;
    mavlink_status_t status; 
    
    while (udp.available()) { 
      uint8_t b = udp.read(); 
      if (mavlink_parse_char(MAVLINK_COMM_0, b, &msg, &status)) { 
        handle_mavlink_message(&msg); 
      } 
    } 
  } 

  // ── 1.5 CẬP NHẬT VẬT LÝ (50Hz = 20ms) ──
  if (now - t_physics >= 20) {
    float dt = (now - t_physics) / 1000.0f;
    update_physics(dt);
    t_physics = now;
  }

  // ── 2. GỬI TELEMETRY (Đúng tần suất) ──
  if (now - t_hb >= 1000) { 
    send_heartbeat(); 
    t_hb = now; 
  } 

  if (now - t_att >= 20) { 
    send_attitude();
    t_att = now;
  }

  if (now - t_pos >= 100) { 
    send_local_position_ned(); 
    send_scaled_pressure(pos_z); 
    send_vfr_hud(); 
    t_pos = now; 
  } 

  if (now - t_sys >= 500) { 
    send_sys_status(); 
    t_sys = now; 
  } 

  if (now - t_sens >= 200) { 
    float t_s = millis() / 1000.0f; 
    float water_temp = 25.0f - pos_z * 0.2f + 0.1f * sinf(t_s * 0.05f); 
    send_named("TEMP", water_temp); 
    send_named("LEAK", 0.0f); 
    t_sens = now; 
  } 
} 