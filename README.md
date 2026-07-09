# GCS ROV Control System

## Cấu trúc dự án (đã refactor)

```
GCS_ROV/
├── main.py                          # Entry point chính — tích hợp vào guirov.py
├── requirements.txt
│
├── GUI/
│   ├── guirov.py                    # [KHÔNG SỬA] Layout gốc từ Qt Designer
│   ├── GUIROVV1.ui                  # Qt Designer source
│   ├── style.qss                    # Stylesheet
│   ├── icon.py                      # Qt Resource (icons)
│   ├── input_handler.py             # Keyboard / Gamepad handler
│   └── widgets/                     # [MỚI] Custom widgets nhúng vào guirov.py
│       ├── __init__.py
│       ├── gl_3d_widget.py          # 3D OpenGL (PyQtGraph) — thay opw_motion
│       ├── slam_radar_widget.py     # 2D SLAM Radar / Minimap — thay frm_simulate_view_bottom
│       └── power_widget.py         # Power System chart — thay ogl_powersys
│
├── core/
│   ├── physics_engine.py            # [MỚI] PyBullet DIRECT wrapper
│   ├── mock_transceiver.py          # Mock MAVLink cho offline test
│   ├── models/                      # [MỚI] Model vật lý từng phiên bản ROV
│   │   ├── __init__.py
│   │   ├── base_rov.py              # Abstract base class (thông số vật lý)
│   │   ├── rov_6thruster.py         # 6DC — BlueROV2 Heavy style
│   │   └── rov_3thruster.py         # 3DC — wedge configuration
│   └── (dynamics.py, visualization.py... — cũ, có thể bỏ qua)
│
└── network/
    ├── __init__.py
    ├── mavlink_worker.py            # [MỚI] MAVLink QThread đầy đủ
    ├── slam_udp_receiver.py         # [MỚI] SLAM UDP Point Cloud receiver
    └── video_receiver.py            # Video stream (H.264)
```

## Chạy ứng dụng

```bash
# Offline (mô phỏng Mock)
python main.py --mock

# Kết nối ROV qua UDP
python main.py --connection udp:0.0.0.0:14550

# Kết nối với file CAD model
python main.py --connection udp:192.168.2.1:14550 --cad assets/rov_model.stl
```

## Kiến trúc Module

### `core/models/` — Model ROV (Tách biệt rõ ràng)
- **BaseROVModel** (abstract): Định nghĩa interface + thông số vật lý
- **ROV6ThrusterModel**: Kế thừa BaseROVModel, override thông số 6 thruster
- **ROV3ThrusterModel**: Kế thừa BaseROVModel, override thông số 3 thruster
- **Thêm model mới**: Tạo file `rov_<tên>.py`, kế thừa BaseROVModel, đăng ký trong `main.py`

### `core/physics_engine.py` — Vật lý
- PyBullet DIRECT (headless, không cửa sổ)
- Hỗ trợ `set_external_pose()`: bypass vật lý khi có dữ liệu MAVLink/SLAM
- Tính: buoyancy, drag tuyến tính + bậc 2, lực thruster qua TAM matrix

### `GUI/widgets/` — Giao diện tùy chỉnh
- **GLROVWidget**: 3D OpenGL viewer (pyqtgraph.opengl), nhúng thay `opw_motion`
  - Load STL/OBJ CAD file
  - Mesh thủ công nếu không có CAD
  - Hiển thị trajectory, SLAM point cloud, FOV cone
- **SLAMRadarWidget**: 2D SLAM minimap (QPainter), nhúng vào `frm_simulate_view_bottom`
  - Polar grid, điểm SLAM màu theo khoảng cách
  - Vòng tròn la bàn, depth bar
- **PowerWidget**: Power system chart (QPainter), nhúng thay `ogl_powersys`
  - Battery gauge, current, power
  - Thruster load bar chart
  - Voltage history chart

### `network/` — Giao tiếp
- **MAVLinkWorker** (QThread): Nhận/gửi tất cả message MAVLink, emit signal về GUI
- **SLAMUDPReceiver** (QThread): Nhận point cloud SLAM qua UDP port 5010

## Điều khiển bàn phím (khi focus cửa sổ)

| Phím | Chức năng |
|------|-----------|
| W/S  | Tiến / Lùi (Surge) |
| A/D  | Xoay trái / phải (Yaw) |
| Q/E  | Sang ngang trái / phải (Sway) |
| R/F  | Lên / Xuống (Heave) |
| Space| Emergency Stop |

## Thêm model ROV mới

```python
# core/models/rov_custom.py
from .base_rov import BaseROVModel

class ROVCustomModel(BaseROVModel):
    DISPLAY_NAME = "Custom ROV"
    MASS = 9.0
    # ... override các thông số khác

    def _build_thrusters(self):
        return [
            {"pos": [...], "dir": [...]},
            # ...
        ]

    def get_visual_config(self):
        return {"chassis": {...}, ...}
```

```python
# main.py — đăng ký model
ROV_MODELS = {
    "3DC": ROV3ThrusterModel,
    "6DC": ROV6ThrusterModel,
    "CUSTOM": ROVCustomModel,  # Thêm dòng này
}
```

Sau đó thêm item vào `cb_mission` trong Qt Designer.
