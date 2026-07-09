# ABYSSAL EXPLORER 9000 - ROV Ground Control Station (GCS) Simulation & Integration Module

This upgraded module provides a complete, high-fidelity 3D simulation and subsea telemetry dashboard for a Remotely Operated Vehicle (ROV). It is designed to act as a standalone application for testing and verification, while exposing reusable widgets that can be seamlessly imported and integrated into your custom main script and Qt Designer interface (`guirov.py`).

---

## 🚀 Key Features

1. **Dual ROV Configurations**:
   - **6-thruster (Vectored)**: Full 6-DOF controls (Surge, Sway, Heave, Yaw, Pitch, Roll) using 4 horizontal vectored thrusters at 45 degrees and 2 vertical thrusters.
   - **3-thruster (Wedge)**: Restricted degrees of freedom (Surge, Heave, Yaw) utilizing a triangular frame chassis, 2 horizontal thrusters, and 1 vertical thruster.
   - *Auto-recalculates physical parameters and the Thrust Allocation Matrix (TAM) in real time.*

2. **MAVLink Communication (Port 14550)**:
   - Receives standard ArduSub/Pixhawk telemetry: `ATTITUDE` (Roll/Pitch/Yaw), `VFR_HUD` (Depth & Heading), `SYS_STATUS` (Battery Voltage & Current), `LOCAL_POSITION_NED` (Position & Speed), and `NAMED_VALUE_FLOAT` (Custom sensors: `TEMP_WATER`, `PH_LEVEL`).
   - Transmits command messages: `HEARTBEAT` (1Hz survival message), `MANUAL_CONTROL` (scaled pilot commands), and `COMMAND_LONG` (Arm/Disarm).
   - *Intelligent Fallback*: If `pymavlink` is not installed on the system, the dashboard automatically runs an offline JSON-over-UDP parser on Port 14550 so testing continues seamlessly.

3. **High-Speed UDP SLAM Receiver (Port 5010)**:
   - Point clouds (boulders, pipelines, seabed features) bypass low-bandwidth MAVLink lines and are received over a dedicated high-speed UDP Socket.
   - Renders point clouds simultaneously in the **3D Viewport** and the **2D SLAM Radar map**.

4. **SLAM Radar Widget**:
   - concentric distance circles representing 1m, 2m, and 3m limits.
   - Dynamic central ROV icon rotated according to yaw/roll/pitch telemetry.
   - Transparent gradient sector representing the forward-facing camera Field of View (FOV).
   - Points colored dynamically by collision hazard: **Red** (Danger < 1m), **Yellow** (Warning < 2.5m), and **Green** (Safe).

5. **Keyboard & Joystick controls**:
   - Arm/Disarm safety lock toggles.
   - Steering binds: W/S (Surge), A/D (Sway), Up/Down Arrow (Heave), Left/Right Arrow (Yaw).

---

## 🛠️ File Architecture

- [dynamics.py](file:///C:/Users/user/.gemini/antigravity/scratch/rov_simulation/dynamics.py): Rigid-body physics simulator (buoyancy, drag, TAM solver) with support for 3-thruster and 6-thruster mechanical layouts.
- [visualization.py](file:///C:/Users/user/.gemini/antigravity/scratch/rov_simulation/visualization.py): Graphics library enclosing the OpenGL `GLROVWidget` (handles 3D rendering and CAD file parser) and the 2D `SLAMRadarWidget` (Polar Radar).
- [main_demo.py](file:///C:/Users/user/.gemini/antigravity/scratch/rov_simulation/main_demo.py): The main GCS dashboard integrating all widgets, threading logic, HUD controls, and layout styles.
- [mock_transceiver.py](file:///C:/Users/user/.gemini/antigravity/scratch/rov_simulation/mock_transceiver.py): A helper utility that broadcasts mock MAVLink telemetry and UDP SLAM point clouds to demonstrate GCS features.

---

## 💻 How to Run the Demonstration

1. **Install dependencies**:
   ```bash
   pip install PyQt6 pyqtgraph pybullet PyOpenGL numpy
   ```
   *(Optional: Install `pymavlink` for native binary packet testing)*
   ```bash
   pip install pymavlink
   ```

2. **Launch the GCS Dashboard**:
   ```bash
   python main_demo.py
   ```
   *By default, the dashboard starts in "GCS Sim Mode" (local physics loops). Uncheck this box to switch to listening for actual subsea telemetry.*

3. **Start the Mock Transceiver (Simulating a deployed ROV & SLAM sensor)**:
   In a separate terminal, run:
   ```bash
   python mock_transceiver.py
   ```
   You will immediately see:
   - The connection indicator in `main_demo.py` switch to "ACTIVE".
   - Telemetry gauges (Voltage, Current, Temp, pH) fluctuating.
   - Point clouds (obstacles representing boulders and a subsea pipeline) populate the 3D grid and the SLAM Radar Map.
   - The ROV rotate and move along its orbital trajectory path.

---

## 🔌 Integration Guide for your `guirov.py` (Qt Designer)

To embed these high-tech modules in your custom Qt Designer layout:

### Method A: Promotion in Qt Designer (Recommended)
1. In Qt Designer, drag a generic `QWidget` onto your layout where you want the 3D viewport or the SLAM Radar map (e.g., inside the `Vfrm_mission` or telemetry frame).
2. Right-click the widget and select **Promote to...**
3. Configure the promoter settings:
   - **Promoted class name**: `GLROVWidget` (for the 3D view) or `SLAMRadarWidget` (for the Radar).
   - **Header file**: `visualization`
4. In your Python `main.py` script, after calling `setupUi(self)`, you can interact with these widgets directly:
   ```python
   # Update 3D pose
   self.ui.my_promoted_gl_widget.update_pose(position, orientation_quat)
   
   # Update Radar
   self.ui.my_promoted_radar_widget.update_state(position, roll, pitch, yaw)
   self.ui.my_promoted_radar_widget.update_points(point_cloud_list)
   ```

### Method B: Programmatic Placement
If you prefer loading `guirov.py` dynamically or instantiating widgets in code:
```python
from PyQt6 import QtWidgets
from visualization import GLROVWidget, SLAMRadarWidget

class MyGCS(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        # Load your designed UI
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        
        # Instantiate widgets
        self.gl_widget = GLROVWidget(self, version="6-thruster")
        self.radar_widget = SLAMRadarWidget(self)
        
        # Insert them into the frames/layouts defined in Designer
        # e.g., if you have a frame named Vfrm_mission with a layout
        self.ui.Vfrm_mission.layout().addWidget(self.gl_widget)
        self.ui.Vfrm_radar.layout().addWidget(self.radar_widget)
```
This ensures maximum modularity. You can keep your layout in `guirov.py` untouched and inject these high-performance modules dynamically.
