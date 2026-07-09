"""
mock_transceiver.py - Mock MAVLink Transceiver for Offline Testing
==================================================================
Mô phỏng gói tin MAVLink khi không có ROV thật.
Được MAVLinkWorker sử dụng tự động khi pymavlink không tìm thấy kết nối.

Dữ liệu giả lập:
  - ATTITUDE  : sin/cos dao động để mô phỏng chuyển động
  - LOCAL_POSITION_NED : chuyển động hình xoắn ốc
  - VFR_HUD   : độ sâu tăng dần
  - SYS_STATUS: pin giảm dần
  - NAMED_VALUE_FLOAT: nhiệt độ và pH ngẫu nhiên
"""
import math
import time
import random


class _MockMsg:
    """Đối tượng giả message MAVLink."""
    def __init__(self, msg_type: str, **kwargs):
        self._type = msg_type
        for k, v in kwargs.items():
            setattr(self, k, v)

    def get_type(self) -> str:
        return self._type


class MockTransceiver:
    """
    Giả lập đối tượng kết nối MAVLink để test offline.
    """

    def __init__(self):
        self._t0       = time.time()
        self._volt     = 16.8
        self._msg_idx  = 0
        self._sensors  = [
            ("TEMP_WATER", 28.5),
            ("PH_LEVEL",   7.2),
        ]

    def get_messages(self) -> list:
        """Trả về danh sách message giả mỗi lần gọi."""
        t = time.time() - self._t0
        msgs = []

        # HEARTBEAT mỗi 1 giây
        if int(t) != int(t - 0.01):
            msgs.append(_MockMsg(
                'HEARTBEAT',
                custom_mode=19,       # MANUAL
                system_status=4,      # ACTIVE
                type=1, autopilot=3, base_mode=0, mavlink_version=3
            ))

        # ATTITUDE 50 Hz
        roll  = 0.15 * math.sin(t * 0.8)
        pitch = 0.10 * math.sin(t * 0.6 + 1.0)
        yaw   = t * 0.2 % (2 * math.pi)
        msgs.append(_MockMsg('ATTITUDE',
            roll=roll, pitch=pitch, yaw=yaw,
            rollspeed=0.0, pitchspeed=0.0, yawspeed=0.05,
            time_boot_ms=int(t * 1000)
        ))

        # LOCAL_POSITION_NED: xoắn ốc đi xuống
        r = 2.0 * (1 - math.exp(-t * 0.1))
        x = r * math.cos(t * 0.3)
        y = r * math.sin(t * 0.3)
        z = -min(t * 0.05, 10.0)       # xuống dần, tối đa 10m
        msgs.append(_MockMsg('LOCAL_POSITION_NED',
            x=x, y=y, z=z,
            vx=0.1*math.cos(t), vy=0.1*math.sin(t), vz=-0.02,
            time_boot_ms=int(t * 1000)
        ))

        # VFR_HUD
        depth = abs(z)
        heading = math.degrees(yaw) % 360
        msgs.append(_MockMsg('VFR_HUD',
            alt=-depth, heading=heading, throttle=30.0,
            airspeed=0.0, groundspeed=0.1, climb=-0.02
        ))

        # SYS_STATUS: pin giảm dần ~1% mỗi 30 giây
        self._volt = max(14.0, 16.8 - t * 0.003)
        remain = min(100, max(0, int((self._volt - 14.0) / 2.8 * 100)))
        msgs.append(_MockMsg('SYS_STATUS',
            voltage_battery=int(self._volt * 1000),
            current_battery=int(82),    # 8.2 A
            battery_remaining=remain,
            onboard_control_sensors_present=0,
            onboard_control_sensors_enabled=0,
            onboard_control_sensors_health=0,
            load=30, drop_rate_comm=0, errors_comm=0
        ))

        # NAMED_VALUE_FLOAT mỗi 5 giây
        if int(t) % 5 == 0 and self._msg_idx != int(t):
            self._msg_idx = int(t)
            name, base = random.choice(self._sensors)
            val = base + random.gauss(0, 0.05)
            msgs.append(_MockMsg('NAMED_VALUE_FLOAT',
                name=name, value=val,
                time_boot_ms=int(t * 1000)
            ))

        # VISION_POSITION_ESTIMATE: thêm nhiễu nhỏ
        msgs.append(_MockMsg('VISION_POSITION_ESTIMATE',
            x=x + random.gauss(0, 0.01),
            y=y + random.gauss(0, 0.01),
            z=z + random.gauss(0, 0.005),
            roll=roll, pitch=pitch, yaw=yaw,
            usec=int(t * 1e6)
        ))

        return msgs

    # Stub methods để tránh lỗi khi code gọi nhầm
    def recv_match(self, blocking=False):
        msgs = self.get_messages()
        return msgs[0] if msgs else None

    @property
    def target_system(self):
        return 1

    @property
    def target_component(self):
        return 1

    class _mav_stub:
        def manual_control_send(self, *a): pass
        def heartbeat_send(self, *a): pass
        def command_long_send(self, *a): pass
        def set_attitude_target_send(self, *a): pass

    mav = _mav_stub()