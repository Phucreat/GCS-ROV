"""
physics_engine.py - PyBullet Headless Physics Engine
=====================================================
Chạy PyBullet ở chế độ DIRECT (không có cửa sổ đồ họa).
Nhận model ROV (BaseROVModel) để lấy thông số vật lý.
Ở chế độ LIVE (kết nối ROV thật), vật lý bị bỏ qua và vị trí
được inject từ MAVLink (LOCAL_POSITION_NED + ATTITUDE).
"""
import math
import numpy as np
import pybullet as p

from core.models.base_rov import BaseROVModel


class PhysicsEngine:
    """
    Wrapper xung quanh PyBullet DIRECT mode.
    Tính toán động học cho mô phỏng offline.
    Có thể bị bypass bằng set_external_pose() khi nhận dữ liệu từ ROV thật.
    """

    def __init__(self, model: BaseROVModel):
        self.model = model
        self._client = p.connect(p.DIRECT)
        p.setGravity(0, 0, -9.81, physicsClientId=self._client)

        self._rov_id = self._create_body()
        self._thruster_inputs = np.zeros(model.num_thrusters())

        # Chế độ override vị trí từ dữ liệu ngoài (MAVLink / SLAM)
        self._use_external_pose = False
        self._ext_pos  = np.zeros(3)
        self._ext_quat = np.array([0.0, 0.0, 0.0, 1.0])

    # --------------------------------------------------------
    # KHỞI TẠO BODY PYBULLET
    # --------------------------------------------------------
    def _create_body(self) -> int:
        m = self.model
        col = p.createCollisionShape(
            p.GEOM_BOX,
            halfExtents=m.HALF_EXTENTS,
            physicsClientId=self._client
        )
        vis = p.createVisualShape(
            p.GEOM_BOX,
            halfExtents=m.HALF_EXTENTS,
            rgbaColor=[0.1, 0.15, 0.2, 0.0],   # trong suốt (chỉ để placeholder)
            physicsClientId=self._client
        )
        body = p.createMultiBody(
            baseMass=m.MASS,
            baseCollisionShapeIndex=col,
            baseVisualShapeIndex=vis,
            basePosition=[0.0, 0.0, 0.0],
            baseOrientation=[0.0, 0.0, 0.0, 1.0],
            physicsClientId=self._client
        )
        p.changeDynamics(
            body, -1,
            linearDamping=0.0,
            angularDamping=0.0,
            localInertiaDiagonal=m.get_inertia(),
            physicsClientId=self._client
        )
        return body

    # --------------------------------------------------------
    # GIAO DIỆN ĐIỀU KHIỂN
    # --------------------------------------------------------
    def set_control(self, surge=0., sway=0., heave=0.,
                    roll=0., pitch=0., yaw=0.):
        """Tính thruster inputs từ lệnh 6-DOF, cập nhật nội bộ."""
        self._thruster_inputs = self.model.compute_thruster_inputs(
            surge, sway, heave, roll, pitch, yaw
        )

    def set_external_pose(self, position: list, quat_xyzw: list):
        """
        Inject vị trí & tư thế từ dữ liệu ngoài (MAVLink / SLAM).
        Khi được gọi, physics sẽ không cập nhật vị trí,
        mà chỉ cập nhật cho đồng bộ.
        """
        self._ext_pos  = np.array(position)
        self._ext_quat = np.array(quat_xyzw)
        self._use_external_pose = True
        # Teleport body trong PyBullet để tránh tích lũy sai số
        p.resetBasePositionAndOrientation(
            self._rov_id, position, quat_xyzw,
            physicsClientId=self._client
        )

    def disable_external_pose(self):
        """Tắt chế độ override, trở về mô phỏng nội bộ."""
        self._use_external_pose = False

    def reset(self, pos=(0., 0., 0.), quat=(0., 0., 0., 1.)):
        """Đặt lại ROV về vị trí gốc."""
        p.resetBasePositionAndOrientation(
            self._rov_id, pos, quat,
            physicsClientId=self._client
        )
        p.resetBaseVelocity(
            self._rov_id, [0., 0., 0.], [0., 0., 0.],
            physicsClientId=self._client
        )
        self._thruster_inputs = np.zeros(self.model.num_thrusters())
        self._use_external_pose = False

    # --------------------------------------------------------
    # VÒNG LẶP MÔ PHỎNG
    # --------------------------------------------------------
    def step(self, dt: float = 1/240.0) -> dict:
        """
        Tiến một bước vật lý.
        
        Returns:
            dict với các key:
              position         : [x, y, z] (m)
              orientation_quat : [qx, qy, qz, qw]
              linear_velocity  : [vx, vy, vz] (m/s)
              angular_velocity : [wx, wy, wz] (rad/s)
              heading_deg      : float  (0-360°)
              pitch_deg        : float
              roll_deg         : float
              thruster_pct     : list of int (0-100) cho mỗi thruster
        """
        if not self._use_external_pose:
            self._apply_forces(dt)
            p.setTimeStep(dt, physicsClientId=self._client)
            p.stepSimulation(physicsClientId=self._client)

        # Lấy trạng thái sau bước tính
        if self._use_external_pose:
            pos  = self._ext_pos.tolist()
            quat = self._ext_quat.tolist()
        else:
            pos, quat = p.getBasePositionAndOrientation(
                self._rov_id, physicsClientId=self._client
            )

        lin_vel, ang_vel = p.getBaseVelocity(
            self._rov_id, physicsClientId=self._client
        )

        euler = p.getEulerFromQuaternion(quat)
        roll_deg  = math.degrees(euler[0])
        pitch_deg = math.degrees(euler[1])
        yaw_deg   = math.degrees(euler[2])
        heading   = yaw_deg % 360.0

        return {
            "position":          np.array(pos),
            "orientation_quat":  np.array(quat),
            "linear_velocity":   np.array(lin_vel),
            "angular_velocity":  np.array(ang_vel),
            "heading_deg":       heading,
            "pitch_deg":         pitch_deg,
            "roll_deg":          roll_deg,
            "thruster_pct":      (np.abs(self._thruster_inputs) * 100).astype(int).tolist(),
        }

    def _apply_forces(self, dt: float):
        """Áp dụng tất cả lực vật lý lên body trong PyBullet."""
        pos, quat = p.getBasePositionAndOrientation(
            self._rov_id, physicsClientId=self._client
        )
        lin_w, ang_w = p.getBaseVelocity(
            self._rov_id, physicsClientId=self._client
        )

        # Chuyển vận tốc từ World → Body frame để tính drag
        _, inv_q = p.invertTransform([0, 0, 0], quat)
        v_body, _ = p.multiplyTransforms([0, 0, 0], inv_q, lin_w, [0, 0, 0, 1])
        w_body, _ = p.multiplyTransforms([0, 0, 0], inv_q, ang_w, [0, 0, 0, 1])
        v_b = np.array(v_body)
        w_b = np.array(w_body)

        # 1. Lực nổi (Buoyancy) — tác dụng tại Center of Buoyancy
        g  = 9.81
        F_b = self.model.MASS * g * self.model.BUOYANCY_FACTOR
        cb_world, _ = p.multiplyTransforms(
            pos, quat, self.model.get_cb_offset(), [0, 0, 0, 1]
        )
        p.applyExternalForce(
            self._rov_id, -1,
            forceObj=[0, 0, F_b], posObj=cb_world,
            flags=p.WORLD_FRAME,
            physicsClientId=self._client
        )

        # 2. Cản nước tuyến tính + bậc 2 (Body frame)
        F_drag = -(self.model.DRAG_LINEAR * v_b
                   + self.model.DRAG_QUADRATIC * v_b * np.abs(v_b))
        T_drag = -(self.model.DRAG_ROT_LINEAR * w_b
                   + self.model.DRAG_ROT_QUAD * w_b * np.abs(w_b))
        p.applyExternalForce(
            self._rov_id, -1,
            forceObj=F_drag, posObj=[0, 0, 0],
            flags=p.LINK_FRAME,
            physicsClientId=self._client
        )
        p.applyExternalTorque(
            self._rov_id, -1,
            torqueObj=T_drag,
            flags=p.LINK_FRAME,
            physicsClientId=self._client
        )

        # 3. Lực thruster (Body frame, tại vị trí điểm đặt)
        for i, t in enumerate(self.model.thrusters):
            force = np.array(t["dir"]) * self._thruster_inputs[i] * self.model.MAX_THRUST
            p.applyExternalForce(
                self._rov_id, -1,
                forceObj=force, posObj=t["pos"],
                flags=p.LINK_FRAME,
                physicsClientId=self._client
            )

    # --------------------------------------------------------
    # QUẢN LÝ TÀI NGUYÊN
    # --------------------------------------------------------
    def close(self):
        """Ngắt kết nối PyBullet."""
        try:
            p.disconnect(physicsClientId=self._client)
        except Exception:
            pass
