"""
base_rov.py - Lớp Cơ Sở (Abstract Base Class) cho tất cả Model ROV
====================================================================
Định nghĩa interface chung và các thông số vật lý mặc định.
Mỗi phiên bản ROV phải kế thừa class này và override:
  - DISPLAY_NAME      : Tên hiển thị trên UI
  - MASS              : Khối lượng (kg)
  - HALF_EXTENTS      : Kích thước bounding box [L/2, W/2, H/2] (m)
  - CB_OFFSET         : Offset tâm nổi (Center of Buoyancy) theo Z (m)
  - BUOYANCY_FACTOR   : Hệ số nổi (>1 = nổi dương)
  - MAX_THRUST        : Lực đẩy tối đa mỗi thruster (N)
  - DRAG_LINEAR       : Vector cản nước tuyến tính [X, Y, Z]
  - DRAG_QUADRATIC    : Vector cản nước bậc 2 [X, Y, Z]
  - DRAG_ROT_LINEAR   : Vector cản xoay tuyến tính [Roll, Pitch, Yaw]
  - DRAG_ROT_QUAD     : Vector cản xoay bậc 2 [Roll, Pitch, Yaw]
  - _build_thrusters(): Trả về danh sách thruster config
"""
from abc import ABC, abstractmethod
import numpy as np


class BaseROVModel(ABC):
    """
    Lớp cơ sở trừu tượng cho tất cả cấu hình ROV.
    Chứa toàn bộ tham số vật lý và phương thức tính toán lực.
    """

    # ============================================================
    # --- THÔNG SỐ VẬT LÝ - CÁC LỚP CON PHẢI OVERRIDE ---
    # ============================================================
    DISPLAY_NAME    = "Base ROV"
    MASS            = 10.0          # kg
    HALF_EXTENTS    = [0.225, 0.17, 0.125]  # m
    CB_OFFSET_Z     = 0.08          # m (tâm nổi cao hơn tâm khối → ổn định)
    BUOYANCY_FACTOR = 1.02          # > 1.0 = nổi dương
    MAX_THRUST      = 30.0          # N / thruster

    # Cản nước tuyến tính theo trục [X(Surge), Y(Sway), Z(Heave)]
    DRAG_LINEAR     = np.array([25.0, 35.0, 45.0])
    DRAG_QUADRATIC  = np.array([35.0, 45.0, 55.0])

    # Cản xoay theo trục [Roll, Pitch, Yaw]
    DRAG_ROT_LINEAR = np.array([6.0, 8.0, 8.0])
    DRAG_ROT_QUAD   = np.array([10.0, 12.0, 12.0])

    # ============================================================
    # --- PHƯƠNG THỨC PHẢI IMPLEMENT ---
    # ============================================================
    @abstractmethod
    def _build_thrusters(self) -> list:
        """
        Trả về danh sách cấu hình thruster.
        Mỗi thruster là dict: {"pos": [x,y,z], "dir": [fx,fy,fz]}
        - pos: vị trí điểm đặt lực trong hệ tọa độ thân tàu (m)
        - dir: vector đơn vị hướng lực (đã normalize)
        Tọa độ thân tàu: X=Forward, Y=Left, Z=Up
        """
        pass

    @abstractmethod
    def get_visual_config(self) -> dict:
        """
        Trả về cấu hình vẽ 3D cho widget visualization.
        Sẽ được GLROVWidget dùng để dựng mô hình.
        """
        pass

    # ============================================================
    # --- PHƯƠNG THỨC CHUNG (KHÔNG CẦN OVERRIDE) ---
    # ============================================================
    def __init__(self):
        self.thrusters = self._build_thrusters()
        self._build_tam()

    def _build_tam(self):
        """Xây dựng Thrust Allocation Matrix (TAM) và pseudo-inverse của nó."""
        n = len(self.thrusters)
        self.TAM = np.zeros((6, n))
        for i, t in enumerate(self.thrusters):
            pos = np.array(t["pos"])
            d   = np.array(t["dir"])
            # 3 hàng đầu: đóng góp lực [Fx, Fy, Fz]
            self.TAM[0:3, i] = d
            # 3 hàng sau: đóng góp moment [Tx, Ty, Tz] = r × f
            self.TAM[3:6, i] = np.cross(pos, d)
        # Pseudo-inverse: ánh xạ tau_desired → u_thruster
        self.TAM_pinv = np.linalg.pinv(self.TAM)

    def compute_thruster_inputs(self, surge, sway, heave,
                                roll, pitch, yaw,
                                f_max=80.0, t_max=20.0) -> np.ndarray:
        """
        Tính toán đầu ra các thruster từ lệnh điều khiển 6-DOF.
        
        Args:
            surge, sway, heave, roll, pitch, yaw: giá trị [-1.0, 1.0]
            f_max: lực tuyến tính tối đa (N)
            t_max: moment xoay tối đa (N·m)
        Returns:
            numpy array (n_thrusters,) giá trị [-1.0, 1.0]
        """
        tau = np.array([
            surge * f_max,
            sway  * f_max,
            heave * f_max,
            roll  * t_max,
            pitch * t_max,
            yaw   * t_max,
        ])
        raw = self.TAM_pinv @ tau
        return np.clip(raw, -1.0, 1.0)

    def num_thrusters(self) -> int:
        return len(self.thrusters)

    def get_inertia(self) -> list:
        """Tính tensor quán tính gần đúng cho khối hộp."""
        m = self.MASS
        lx, ly, lz = [e * 2 for e in self.HALF_EXTENTS]
        ixx = (1/12) * m * (ly**2 + lz**2)
        iyy = (1/12) * m * (lx**2 + lz**2)
        izz = (1/12) * m * (lx**2 + ly**2)
        return [ixx, iyy, izz]

    def get_cb_offset(self) -> list:
        """Vị trí tâm nổi trong hệ tọa độ thân tàu."""
        return [0.0, 0.0, self.CB_OFFSET_Z]
