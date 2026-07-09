import sys
import time
import socket
import json
import math
import random
import numpy as np

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QGridLayout, QVBoxLayout, QHBoxLayout, 
    QLabel, QSlider, QPushButton, QFileDialog, QGroupBox, QCheckBox, QProgressBar,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget
)
from PyQt6.QtCore import QTimer, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QRadialGradient, QPolygon, QPixmap

# Try to import pymavlink
try:
    from pymavlink import mavutil
    MAVLINK_AVAILABLE = True
except ImportError:
    MAVLINK_AVAILABLE = False

from dynamics import ROVDynamics
from visualization import GLROVWidget, SLAMRadarWidget

# Custom Video Stream Mock Widget
class VideoFeedWidget(QWidget):
    """
    Renders a live video stream mockup with telemetry HUD overlays,
    simulating an underwater camera feed.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_animation)
        self.timer.start(50) # 20 FPS overlay update
        self.t = 0.0
        
    def update_animation(self):
        self.t += 0.05
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw background (Deep oceanic blue with minor lighting grid)
        width, height = self.width(), self.height()
        bg_grad = QRadialGradient(width/2, height/2, width/2)
        bg_grad.setColorAt(0.0, QColor("#122a48"))
        bg_grad.setColorAt(1.0, QColor("#040810"))
        painter.fillRect(self.rect(), bg_grad)
        
        # Draw dynamic sonar scanning line / waves (representing underwater environment)
        painter.setPen(QPen(QColor(0, 229, 255, 30), 2))
        wave_y = int(height/2 + 40 * math.sin(self.t))
        painter.drawLine(0, wave_y, width, wave_y)
        
        # Draw static HUD frame overlays
        # Center Reticle
        painter.setPen(QPen(QColor(0, 229, 255, 100), 1))
        painter.drawEllipse(width//2 - 20, height//2 - 20, 40, 40)
        painter.drawLine(width//2 - 30, height//2, width//2 + 30, height//2)
        painter.drawLine(width//2, height//2 - 30, width//2, height//2 + 30)
        
        # Corner brackets
        margin = 15
        blen = 20
        painter.setPen(QPen(QColor(0, 229, 255, 120), 2))
        # Top-Left
        painter.drawLine(margin, margin, margin + blen, margin)
        painter.drawLine(margin, margin, margin, margin + blen)
        # Top-Right
        painter.drawLine(width - margin, margin, width - margin - blen, margin)
        painter.drawLine(width - margin, margin, width - margin, margin + blen)
        # Bottom-Left
        painter.drawLine(margin, height - margin, margin + blen, height - margin)
        painter.drawLine(margin, height - margin, margin, height - margin - blen)
        # Bottom-Right
        painter.drawLine(width - margin, height - margin, width - margin - blen, height - margin)
        painter.drawLine(width - margin, height - margin, width - margin, height - margin - blen)
        
        # Telemetry text overlays
        painter.setPen(QColor(0, 229, 255, 200))
        painter.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        painter.drawText(25, 30, "CAMERA: FRONT HD")
        painter.drawText(25, 45, "FORMAT: H.264 / RTSP")
        painter.drawText(25, 60, "RESOLUTION: 4K UHD")
        painter.drawText(25, 75, f"FPS: {29 + random.randint(0,1)}")
        
        # Red Record Indicator
        painter.setPen(Qt.PenStyle.NoPen)
        if int(self.t * 2) % 2 == 0:
            painter.setBrush(QBrush(QColor("#ff3333")))
        else:
            painter.setBrush(QBrush(QColor("#661111")))
        painter.drawEllipse(width - 90, 20, 10, 10)
        
        painter.setPen(QColor(255, 50, 50, 200))
        painter.drawText(width - 75, 30, "REC")
        
        # Water temperature / depth overlay bottom-right
        painter.setPen(QColor(0, 229, 255, 200))
        painter.drawText(width - 150, height - 45, f"SYS LOAD: {40.0 + 5.0*math.sin(self.t):.1f}%")
        painter.drawText(width - 150, height - 30, "STREAM STATUS: OK")


# Thread to listen for Visual SLAM Point Clouds on UDP Port 5010
class SLAMReceiverThread(QThread):
    points_received = pyqtSignal(list)

    def run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(('0.0.0.0', 5010))
            print("UDP SLAM point cloud receiver thread listening on port 5010")
        except Exception as e:
            print(f"Error binding UDP SLAM port 5010: {e}")
            sock.close()
            return

        while not self.isInterruptionRequested():
            try:
                sock.settimeout(0.5)
                data, addr = sock.recvfrom(65535)
                points = json.loads(data.decode('utf-8'))
                if isinstance(points, list):
                    self.points_received.emit(points)
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Error parsing UDP SLAM data: {e}")
        sock.close()


# Thread to listen for MAVLink Telemetry on UDP Port 14550
class MAVLinkReceiverThread(QThread):
    telemetry_received = pyqtSignal(dict)

    def run(self):
        # We also listen on 14550 for mock JSON UDP packets if MAVLink is offline
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(('0.0.0.0', 14550))
            print("UDP Telemetry receiver listening on port 14550")
        except Exception as e:
            print(f"Error binding UDP Telemetry port 14550: {e}")
            sock.close()
            return
            
        mav_conn = None
        if MAVLINK_AVAILABLE:
            try:
                mav_conn = mavutil.mavlink_connection('udpin:0.0.0.0:14550')
                print("MAVLink link established on udpin:0.0.0.0:14550")
            except Exception as e:
                print(f"Could not bind native MAVLink connection: {e}")
                mav_conn = None

        while not self.isInterruptionRequested():
            # 1. Parse Native MAVLink Packets
            if MAVLINK_AVAILABLE and mav_conn is not None:
                try:
                    msg = mav_conn.recv_match(blocking=False)
                    if msg is not None:
                        msg_type = msg.get_type()
                        data = {"msg_type": msg_type}
                        
                        if msg_type == 'ATTITUDE':
                            # Radians to degrees
                            data["roll"] = math.degrees(msg.roll)
                            data["pitch"] = math.degrees(msg.pitch)
                            data["yaw"] = math.degrees(msg.yaw)
                            self.telemetry_received.emit(data)
                        elif msg_type == 'VFR_HUD':
                            data["depth"] = msg.alt  # negative value
                            data["heading"] = msg.heading
                            data["throttle"] = msg.throttle
                            self.telemetry_received.emit(data)
                        elif msg_type == 'SYS_STATUS':
                            # Millivolts -> Volts
                            data["voltage_battery"] = msg.voltage_battery / 1000.0
                            # 10 * Milliamps -> Amps
                            data["current_battery"] = msg.current_battery / 100.0
                            self.telemetry_received.emit(data)
                        elif msg_type == 'LOCAL_POSITION_NED':
                            data["x"] = msg.x
                            data["y"] = msg.y
                            data["z"] = msg.z
                            data["vx"] = msg.vx
                            data["vy"] = msg.vy
                            data["vz"] = msg.vz
                            self.telemetry_received.emit(data)
                        elif msg_type == 'VISION_POSITION_ESTIMATE':
                            data["x_slam"] = msg.x
                            data["y_slam"] = msg.y
                            data["z_slam"] = msg.z
                            self.telemetry_received.emit(data)
                        elif msg_type == 'NAMED_VALUE_FLOAT':
                            # Extract sensor name and value
                            name = msg.name
                            # Convert bytes to string
                            if isinstance(name, bytes):
                                name = name.decode('utf-8', errors='ignore')
                            data["name"] = name.strip('\x00')
                            data["value"] = msg.value
                            self.telemetry_received.emit(data)
                            
                    time.sleep(0.001)
                except Exception as e:
                    print(f"MAVLink parsing error: {e}")
                    
            # 2. Parse Fallback JSON Telemetry packets
            else:
                try:
                    sock.settimeout(0.5)
                    data, addr = sock.recvfrom(65535)
                    parsed = json.loads(data.decode('utf-8'))
                    if parsed.get("msg_type") == "TELEMETRY":
                        self.telemetry_received.emit({
                            "msg_type": "OFFLINE_TELEMETRY",
                            "x": parsed["x"],
                            "y": parsed["y"],
                            "z": parsed["z"],
                            "roll": parsed["roll"],
                            "pitch": parsed["pitch"],
                            "yaw": parsed["yaw"],
                            "voltage_battery": parsed["battery_mv"] / 1000.0,
                            "current_battery": parsed["battery_ma"] / 1000.0,
                            "temp_water": parsed["water_temp"],
                            "ph_level": parsed["ph_level"]
                        })
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"JSON telemetry parsing error: {e}")
                    
        sock.close()


class ROVGCSWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ABYSSAL EXPLORER 9000 - ROV CONTROL SYSTEM")
        self.resize(1600, 950)
        
        # Operation State Variables
        self.selected_model = "6-thruster"
        self.connection_active = True
        self.control_mode = "MANUAL" # MANUAL vs AUTO / SLAM
        self.armed_status = False
        self.headlights_active = True
        
        # Setup physics solver (used in local Simulation mode)
        self.dynamics = ROVDynamics(version=self.selected_model)
        self.is_simulation_mode = True # Default to local simulation
        
        # Live GCS state
        self.rov_pos = np.array([0.0, 0.0, 0.0])
        self.rov_quat = np.array([0.0, 0.0, 0.0, 1.0])
        self.rov_yaw = 0.0
        self.rov_pitch = 0.0
        self.rov_roll = 0.0
        self.battery_v = 14.8
        self.battery_a = 2.4
        self.temp_water = 22.4
        self.ph_level = 7.6
        self.salinity = 34.2
        self.last_telemetry_time = time.time()
        
        self.init_ui()
        
        # 60 FPS update timer for local simulation and GUI polling
        self.physics_substeps = 4
        self.dt_physics = 1.0 / (60.0 * self.physics_substeps)
        self.frame_timer = QTimer(self)
        self.frame_timer.timeout.connect(self.frame_update)
        self.frame_timer.start(16) # ~60 Hz
        
        # Start communication receiver threads
        self.slam_thread = SLAMReceiverThread(self)
        self.slam_thread.points_received.connect(self.on_slam_points_received)
        self.slam_thread.start()
        
        self.telemetry_thread = MAVLinkReceiverThread(self)
        self.telemetry_thread.telemetry_received.connect(self.on_telemetry_received)
        self.telemetry_thread.start()
        
        # Keyboard steering setup
        self.keys_pressed = {}
        
    def init_ui(self):
        # Premium Dark-themed Futuristic Stylesheet
        self.setStyleSheet("""
            QMainWindow {
                background-color: #060b13;
            }
            QWidget {
                background-color: #060b13;
                color: #8c9ba5;
                font-family: 'Segoe UI', 'Consolas', monospace;
            }
            QGroupBox {
                border: 2px solid #142840;
                border-radius: 6px;
                background-color: #0b1422;
                margin-top: 1.2em;
                font-weight: bold;
                color: #00e5ff;
                font-size: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 4px;
            }
            QLabel {
                font-size: 12px;
            }
            QPushButton {
                background-color: #0c1a2d;
                color: #00e5ff;
                border: 1px solid #00a8cc;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #00a8cc;
                color: #060b13;
            }
            QPushButton:pressed {
                background-color: #00e5ff;
            }
            QComboBox {
                border: 1px solid #142840;
                border-radius: 3px;
                background-color: #080f18;
                color: #00e5ff;
                padding: 4px;
            }
            QSlider::groove:horizontal {
                border: 1px solid #142840;
                height: 4px;
                background: #091321;
            }
            QSlider::handle:horizontal {
                background: #00e5ff;
                border: 1px solid #00a8cc;
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QProgressBar {
                border: 1px solid #142840;
                background-color: #091321;
                text-align: center;
                color: #ffffff;
                font-size: 10px;
                height: 12px;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background-color: #00e5ff;
            }
            QTableWidget {
                background-color: #080f18;
                border: 1px solid #142840;
                gridline-color: #142840;
                color: #8c9ba5;
            }
            QHeaderView::section {
                background-color: #0c1a2d;
                color: #00e5ff;
                padding: 4px;
                border: 1px solid #142840;
                font-weight: bold;
            }
        """)

        # Main Layout Structure
        outer_layout = QVBoxLayout()
        outer_layout.setContentsMargins(10, 10, 10, 10)
        outer_layout.setSpacing(10)

        # ----------------------------------------------------
        # 1. HEADER ROW
        # ----------------------------------------------------
        header_widget = QWidget()
        header_widget.setStyleSheet("background-color: #0b1422; border: 1px solid #142840; border-radius: 6px;")
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(15, 8, 15, 8)
        
        # Logo and Title
        title_layout = QVBoxLayout()
        main_title = QLabel("ABYSSAL EXPLORER 9000")
        main_title.setStyleSheet("color: #00e5ff; font-size: 18px; font-weight: bold; border: none; background: transparent;")
        sub_title = QLabel("ROV GROUND CONTROL SYSTEM | v2.4-PRO")
        sub_title.setStyleSheet("color: #8c9ba5; font-size: 10px; border: none; background: transparent;")
        title_layout.addWidget(main_title)
        title_layout.addWidget(sub_title)
        header_layout.addLayout(title_layout)
        
        header_layout.addStretch()

        # Model Selection Combo Box
        model_lbl = QLabel("ROV MODEL:")
        model_lbl.setStyleSheet("color: #00a8cc; font-weight: bold; border: none; background: transparent;")
        self.model_combo = QComboBox()
        self.model_combo.addItems(["6-thruster (Vectored)", "3-thruster (Wedge)"])
        self.model_combo.currentIndexChanged.connect(self.on_model_changed)
        header_layout.addWidget(model_lbl)
        header_layout.addWidget(self.model_combo)
        
        header_layout.addSpacing(15)

        # Connect Status Box
        status_lbl = QLabel("STATUS:")
        status_lbl.setStyleSheet("color: #00a8cc; font-weight: bold; border: none; background: transparent;")
        self.status_val = QLabel("ACTIVE")
        self.status_val.setStyleSheet("color: #00ff66; font-weight: bold; border: none; background: transparent;")
        header_layout.addWidget(status_lbl)
        header_layout.addWidget(self.status_val)

        header_layout.addSpacing(15)

        # Mode Box
        mode_lbl = QLabel("ROV MODE:")
        mode_lbl.setStyleSheet("color: #00a8cc; font-weight: bold; border: none; background: transparent;")
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["MANUAL", "AUTO / SLAM"])
        self.mode_combo.currentIndexChanged.connect(self.on_mode_changed)
        header_layout.addWidget(mode_lbl)
        header_layout.addWidget(self.mode_combo)

        header_layout.addSpacing(15)

        # Connection strength bar
        conn_lbl = QLabel("CONNECTIVITY:")
        conn_lbl.setStyleSheet("color: #00a8cc; font-weight: bold; border: none; background: transparent;")
        self.conn_progress = QProgressBar()
        self.conn_progress.setFixedWidth(80)
        self.conn_progress.setValue(100)
        self.conn_progress.setStyleSheet("""
            QProgressBar { border: 1px solid #142840; height: 12px; background-color: #091321; }
            QProgressBar::chunk { background-color: #00ff66; }
        """)
        header_layout.addWidget(conn_lbl)
        header_layout.addWidget(self.conn_progress)
        
        header_layout.addSpacing(15)

        # Team / Author label
        team_lbl = QLabel("TEAM: OCEANIC RESEARCH UNIT")
        team_lbl.setStyleSheet("color: #8c9ba5; font-size: 11px; font-weight: bold; border: none; background: transparent;")
        header_layout.addWidget(team_lbl)
        
        header_layout.addSpacing(15)

        # UTC Time / Clock
        self.clock_lbl = QLabel("00:00:00 UTC")
        self.clock_lbl.setStyleSheet("color: #00e5ff; font-size: 13px; font-weight: bold; font-family: 'Consolas'; border: none; background: transparent;")
        header_layout.addWidget(self.clock_lbl)
        
        # Setting Button
        self.btn_settings = QPushButton("⚙")
        self.btn_settings.setFixedWidth(30)
        self.btn_settings.clicked.connect(self.open_settings_dialog)
        header_layout.addWidget(self.btn_settings)

        outer_layout.addWidget(header_widget)

        # ----------------------------------------------------
        # 2. THREE-PANEL CORE LAYOUT
        # ----------------------------------------------------
        core_layout = QHBoxLayout()
        core_layout.setSpacing(10)

        # ------------------- LEFT ROW: Video & 3D Viewer -------------------
        left_layout = QVBoxLayout()
        left_layout.setSpacing(10)

        # Live Video Feed Box
        video_group = QGroupBox("01 LIVE CAMERA FEED")
        video_vbox = QVBoxLayout(video_group)
        video_vbox.setContentsMargins(6, 12, 6, 6)
        self.video_widget = VideoFeedWidget()
        video_vbox.addWidget(self.video_widget, stretch=1)
        left_layout.addWidget(video_group, stretch=1)

        # 3D Viewport Box
        motion_group = QGroupBox("02 3D MOTION & POSITION")
        motion_vbox = QVBoxLayout(motion_group)
        motion_vbox.setContentsMargins(6, 12, 6, 6)
        
        self.gl_widget = GLROVWidget(version=self.selected_model)
        motion_vbox.addWidget(self.gl_widget, stretch=1)
        
        # Live HUD Pose metrics below 3D window
        hud_metrics_widget = QWidget()
        hud_metrics_widget.setStyleSheet("background-color: #080f18; border-top: 1px solid #142840; border-radius: 4px;")
        hud_metrics_layout = QHBoxLayout(hud_metrics_widget)
        hud_metrics_layout.setContentsMargins(8, 8, 8, 8)
        
        # Position Readout
        pos_vbox = QVBoxLayout()
        pos_title = QLabel("POSITION")
        pos_title.setStyleSheet("color: #00a8cc; font-weight: bold; font-size: 10px;")
        self.lbl_pos_val = QLabel("X: 0.0M\nY: 0.0M\nZ: 0.0M")
        self.lbl_pos_val.setStyleSheet("color: #ffffff; font-family: 'Consolas'; font-size: 11px;")
        pos_vbox.addWidget(pos_title)
        pos_vbox.addWidget(self.lbl_pos_val)
        hud_metrics_layout.addLayout(pos_vbox)
        
        # Velocity Readout
        vel_vbox = QVBoxLayout()
        vel_title = QLabel("VELOCITY")
        vel_title.setStyleSheet("color: #00a8cc; font-weight: bold; font-size: 10px;")
        self.lbl_vel_val = QLabel("X: 0.0 M/S\nY: 0.0 M/S\nZ: 0.0 M/S")
        self.lbl_vel_val.setStyleSheet("color: #ffffff; font-family: 'Consolas'; font-size: 11px;")
        vel_vbox.addWidget(vel_title)
        vel_vbox.addWidget(self.lbl_vel_val)
        hud_metrics_layout.addLayout(vel_vbox)

        # Angles (Roll, Pitch, Yaw)
        ang_vbox = QVBoxLayout()
        ang_title = QLabel("ATTITUDE")
        ang_title.setStyleSheet("color: #00a8cc; font-weight: bold; font-size: 10px;")
        self.lbl_ang_val = QLabel("HEADING: 000.0°\nPITCH: +00.0°\nROLL: +00.0°")
        self.lbl_ang_val.setStyleSheet("color: #00e5ff; font-family: 'Consolas'; font-size: 11px;")
        ang_vbox.addWidget(ang_title)
        ang_vbox.addWidget(self.lbl_ang_val)
        hud_metrics_layout.addLayout(ang_vbox)

        motion_vbox.addWidget(hud_metrics_widget)
        left_layout.addWidget(motion_group, stretch=1)
        core_layout.addLayout(left_layout, stretch=2)

        # ------------------- MIDDLE ROW: Radar & Power -------------------
        middle_layout = QVBoxLayout()
        middle_layout.setSpacing(10)

        # Compass & SLAM Minimap Radar
        radar_group = QGroupBox("03 SLAM RADAR / COMPASS MAP")
        radar_vbox = QVBoxLayout(radar_group)
        radar_vbox.setContentsMargins(6, 12, 6, 6)
        
        self.radar_widget = SLAMRadarWidget()
        radar_vbox.addWidget(self.radar_widget, stretch=1)
        middle_layout.addWidget(radar_group, stretch=1)

        # Power System Panel
        power_group = QGroupBox("04 POWER SYSTEMS & LOAD")
        power_grid = QGridLayout(power_group)
        power_grid.setSpacing(8)
        
        # Bat percentage
        power_grid.addWidget(QLabel("MAIN BATTERY:"), 0, 0)
        self.bar_bat = QProgressBar()
        self.bar_bat.setRange(0, 100)
        self.bar_bat.setValue(85)
        self.bar_bat.setStyleSheet("QProgressBar::chunk { background-color: #00ff66; }")
        power_grid.addWidget(self.bar_bat, 0, 1)

        # Bat metrics
        self.lbl_bat_metrics = QLabel("VOLTAGE: 14.8V | CURRENT: 2.5A")
        self.lbl_bat_metrics.setStyleSheet("color: #ffffff; font-family: 'Consolas';")
        power_grid.addWidget(self.lbl_bat_metrics, 1, 0, 1, 2)
        
        # System load progress
        power_grid.addWidget(QLabel("THRUSTER LOAD:"), 2, 0)
        self.bar_load = QProgressBar()
        self.bar_load.setRange(0, 100)
        self.bar_load.setValue(35)
        power_grid.addWidget(self.bar_load, 2, 1)
        
        # Mode Status button actions
        self.btn_arm = QPushButton("ARM ENGINES")
        self.btn_arm.clicked.connect(self.toggle_arm_engines)
        self.btn_arm.setStyleSheet("QPushButton { background-color: #2b0c0c; color: #ff3333; border: 1px solid #ff3333; }")
        power_grid.addWidget(self.btn_arm, 3, 0)

        self.btn_light = QPushButton("LIGHTS ON")
        self.btn_light.clicked.connect(self.toggle_lights)
        power_grid.addWidget(self.btn_light, 3, 1)

        middle_layout.addWidget(power_group)
        core_layout.addLayout(middle_layout, stretch=1)

        # ------------------- RIGHT ROW: Telemetry Table & Manual Controls -------------------
        right_layout = QVBoxLayout()
        right_layout.setSpacing(10)

        # Telemetry Table
        telemetry_group = QGroupBox("05 TELEMETRY DATA")
        telemetry_vbox = QVBoxLayout(telemetry_group)
        telemetry_vbox.setContentsMargins(6, 12, 6, 6)
        
        self.telemetry_table = QTableWidget()
        self.telemetry_table.setColumnCount(3)
        self.telemetry_table.setHorizontalHeaderLabels(["PARAMETER", "VALUE", "STATUS"])
        self.telemetry_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.telemetry_table.verticalHeader().setVisible(False)
        
        # Initial parameters
        self.telemetry_items = [
            ["DEPTH", "-15.0 M", "NOMINAL", "#00ff66"],
            ["WATER TEMP", "22.4 °C", "NOMINAL", "#00ff66"],
            ["SALINITY", "34.2 PSU", "NOMINAL", "#00ff66"],
            ["PRESSURE", "1.5 BAR", "NOMINAL", "#00ff66"],
            ["VOLTAGE", "14.8 V", "NOMINAL", "#00ff66"],
            ["CURRENT", "2.5 A", "NOMINAL", "#00ff66"]
        ]
        
        self.telemetry_table.setRowCount(len(self.telemetry_items))
        for row, item in enumerate(self.telemetry_items):
            self.telemetry_table.setItem(row, 0, QTableWidgetItem(item[0]))
            self.telemetry_table.setItem(row, 1, QTableWidgetItem(item[1]))
            
            status_item = QTableWidgetItem(item[2])
            status_item.setForeground(QColor(item[3]))
            self.telemetry_table.setItem(row, 2, status_item)
            
        telemetry_vbox.addWidget(self.telemetry_table)
        right_layout.addWidget(telemetry_group, stretch=1)

        # Manual Thrusters sliders
        manual_group = QGroupBox("06 MANUAL THRUSTER INPUTS")
        manual_grid = QGridLayout(manual_group)
        manual_grid.setSpacing(6)
        
        self.thruster_bars = []
        for i in range(6):
            lbl = QLabel(f"THR {i+1}:")
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            manual_grid.addWidget(lbl, i, 0)
            manual_grid.addWidget(bar, i, 1)
            self.thruster_bars.append(bar)
            
        right_layout.addWidget(manual_group)

        # System Mode selector (Simulation vs Live MAVLink)
        mode_select_group = QGroupBox("SIMULATION VS LIVE CONNECT")
        mode_select_layout = QHBoxLayout(mode_select_group)
        
        self.chk_sim_mode = QCheckBox("GCS Sim Mode")
        self.chk_sim_mode.setChecked(True)
        self.chk_sim_mode.stateChanged.connect(self.on_sim_mode_toggled)
        mode_select_layout.addWidget(self.chk_sim_mode)
        
        btn_reset = QPushButton("Reset Pos")
        btn_reset.clicked.connect(self.reset_sim)
        mode_select_layout.addWidget(btn_reset)
        
        btn_import = QPushButton("Import CAD")
        btn_import.clicked.connect(self.import_cad)
        mode_select_layout.addWidget(btn_import)
        
        right_layout.addWidget(mode_select_group)

        core_layout.addLayout(right_layout, stretch=1)
        outer_layout.addLayout(core_layout, stretch=1)

        # Set Central Widget
        central_widget = QWidget()
        central_widget.setLayout(outer_layout)
        self.setCentralWidget(central_widget)

    # ----------------------------------------------------
    # EVENT HANDLERS
    # ----------------------------------------------------
    def on_sim_mode_toggled(self, state):
        self.is_simulation_mode = (state == 2)
        if self.is_simulation_mode:
            self.dynamics.reset()
            self.gl_widget.path_points.clear()
            self.status_val.setText("ACTIVE (SIM)")
            self.status_val.setStyleSheet("color: #00ff66; font-weight: bold;")
        else:
            self.status_val.setText("LISTENING")
            self.status_val.setStyleSheet("color: #00e5ff; font-weight: bold;")

    def on_model_changed(self, index):
        self.selected_model = "6-thruster" if index == 0 else "3-thruster"
        # Switch model in simulation and visualizer
        self.dynamics.change_configuration(self.selected_model)
        self.gl_widget.change_configuration(self.selected_model)
        self.gl_widget.path_points.clear()
        
        # Show/Hide thruster bar controls for 3-thruster configuration
        for i in range(6):
            self.thruster_bars[i].setValue(0)
            if self.selected_model == "3-thruster" and i >= 3:
                self.thruster_bars[i].setEnabled(False)
            else:
                self.thruster_bars[i].setEnabled(True)

    def on_mode_changed(self, index):
        self.control_mode = "MANUAL" if index == 0 else "AUTO / SLAM"

    def toggle_arm_engines(self):
        self.armed_status = not self.armed_status
        if self.armed_status:
            self.btn_arm.setText("DISARM ENGINES")
            self.btn_arm.setStyleSheet("QPushButton { background-color: #0c2b1a; color: #00ff66; border: 1px solid #00ff66; }")
            # If MAVLink connection is available, send Command
            self.send_mavlink_arm(1)
        else:
            self.btn_arm.setText("ARM ENGINES")
            self.btn_arm.setStyleSheet("QPushButton { background-color: #2b0c0c; color: #ff3333; border: 1px solid #ff3333; }")
            self.send_mavlink_arm(0)

    def toggle_lights(self):
        self.headlights_active = not self.headlights_active
        self.gl_widget.toggle_headlights(self.headlights_active)
        if self.headlights_active:
            self.btn_light.setText("LIGHTS ON")
        else:
            self.btn_light.setText("LIGHTS OFF")

    def reset_sim(self):
        self.dynamics.reset()
        self.gl_widget.path_points.clear()
        self.radar_widget.update_state([0,0,0], 0, 0, 0)
        self.radar_widget.update_points([])

    def import_cad(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Import 3D CAD Model", "", "3D CAD Files (*.stl *.obj)"
        )
        if filepath:
            success = self.gl_widget.import_cad_model(filepath)
            if success:
                print(f"CAD Model imported: {filepath}")
            else:
                QtWidgets.QMessageBox.warning(
                    self, "Import Error", "Failed to load the selected CAD model. Verify the file format."
                )

    def open_settings_dialog(self):
        QtWidgets.QMessageBox.information(
            self, "Settings Configuration",
            "GCS Settings Panel:\n\n"
            "- Controller Binds: keyboard (W/S/A/D/arrows)\n"
            "- Blackbox Logging Target: logs/blackbox_<date>.log\n"
            "- Mavlink Connection: UDP Port 14550\n"
            "- Visual SLAM Node listener: UDP Port 5010"
        )

    # ----------------------------------------------------
    # DATA COMMUNICATIONS CALLBACKS
    # ----------------------------------------------------
    def on_slam_points_received(self, points):
        """Called when UDP Port 5010 delivers a SLAM Point Cloud."""
        # 1. Update 3D Visualizer point cloud
        self.gl_widget.update_slam_points(points)
        # 2. Update 2D Radar map point cloud
        self.radar_widget.update_points(points)

    def on_telemetry_received(self, data):
        """Called when receiving MAVLink or mock JSON telemetry."""
        # Bypasses local physics if in live telemetry mode
        if self.is_simulation_mode:
            return # Ignore external telemetry in local simulation mode
            
        self.last_telemetry_time = time.time()
        msg_type = data.get("msg_type")
        
        # Override GCS state attributes based on received message
        if msg_type in ["ATTITUDE", "OFFLINE_TELEMETRY"]:
            self.rov_roll = data["roll"]
            self.rov_pitch = data["pitch"]
            self.rov_yaw = data["yaw"]
            
        if msg_type in ["LOCAL_POSITION_NED", "OFFLINE_TELEMETRY"]:
            self.rov_pos = np.array([data["x"], data["y"], data["z"]])
            
        if msg_type in ["SYS_STATUS", "OFFLINE_TELEMETRY"]:
            self.battery_v = data["voltage_battery"]
            self.battery_a = data["current_battery"]
            
        if msg_type in ["NAMED_VALUE_FLOAT", "OFFLINE_TELEMETRY"]:
            if msg_type == "NAMED_VALUE_FLOAT":
                name = data["name"]
                val = data["value"]
                if name == "TEMP_WATER":
                    self.temp_water = val
                elif name == "PH_LEVEL":
                    self.ph_level = val
            else:
                self.temp_water = data["temp_water"]
                self.ph_level = data["ph_level"]
                
        # Trigger redraw of visuals using updated metrics
        q_roll = math.radians(self.rov_roll)
        q_pitch = math.radians(self.rov_pitch)
        q_yaw = math.radians(self.rov_yaw)
        
        # Convert Euler to Quaternion [x,y,z,w]
        c1 = math.cos(q_roll/2)
        s1 = math.sin(q_roll/2)
        c2 = math.cos(q_pitch/2)
        s2 = math.sin(q_pitch/2)
        c3 = math.cos(q_yaw/2)
        s3 = math.sin(q_yaw/2)
        
        self.rov_quat = np.array([
            s1*c2*c3 - c1*s2*s3,
            c1*s2*c3 + s1*c2*s3,
            c1*c2*s3 - s1*s2*c3,
            c1*c2*c3 + s1*s2*s3
        ])
        
        self.gl_widget.update_pose(self.rov_pos, self.rov_quat)
        self.radar_widget.update_state(self.rov_pos, self.rov_roll, self.rov_pitch, self.rov_yaw)
        
        # Send keyboard control down to port 14550 if MAVLink is connected and we are in Live Telemetry
        self.send_mavlink_manual_control()

    # ----------------------------------------------------
    # KEYBOARD STEERING LOGIC
    # ----------------------------------------------------
    def keyPressEvent(self, event):
        self.keys_pressed[event.key()] = True
        super().keyPressEvent(event)
        
    def keyReleaseEvent(self, event):
        if event.key() in self.keys_pressed:
            del self.keys_pressed[event.key()]
        super().keyReleaseEvent(event)

    def get_keyboard_control_inputs(self):
        """Translates keyboard events to 6-DOF controls (-1.0 to 1.0)."""
        surge = 0.0
        sway = 0.0
        heave = 0.0
        roll = 0.0
        pitch = 0.0
        yaw = 0.0
        
        # surge (W/S)
        if Qt.Key.Key_W in self.keys_pressed:
            surge = 1.0
        elif Qt.Key.Key_S in self.keys_pressed:
            surge = -1.0
            
        # sway (A/D)
        if Qt.Key.Key_A in self.keys_pressed:
            sway = -1.0
        elif Qt.Key.Key_D in self.keys_pressed:
            sway = 1.0
            
        # heave (Up/Down Arrow)
        if Qt.Key.Key_Up in self.keys_pressed:
            heave = 1.0
        elif Qt.Key.Key_Down in self.keys_pressed:
            heave = -1.0
            
        # yaw (Left/Right Arrow)
        if Qt.Key.Key_Left in self.keys_pressed:
            yaw = -1.0
        elif Qt.Key.Key_Right in self.keys_pressed:
            yaw = 1.0
            
        return surge, sway, heave, roll, pitch, yaw

    # ----------------------------------------------------
    # MAVLINK COMMAND SENDERS
    # ----------------------------------------------------
    def send_mavlink_arm(self, arm_cmd):
        """Sends MAVLink COMMAND_LONG component arm command (Command 400)."""
        if MAVLINK_AVAILABLE and not self.is_simulation_mode:
            try:
                # Target port 14550 or establish connection
                master = mavutil.mavlink_connection('udpout:127.0.0.1:14550', source_system=255)
                master.mav.command_long_send(
                    1, 1, # target system, target component
                    mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                    0, arm_cmd, 0, 0, 0, 0, 0, 0
                )
                print(f"MAVLink sent Component Arm/Disarm: {arm_cmd}")
            except Exception as e:
                print(f"Error sending MAVLink arm command: {e}")

    def send_mavlink_manual_control(self):
        """Sends MAVLink MANUAL_CONTROL (Message ID 69)."""
        if MAVLINK_AVAILABLE and not self.is_simulation_mode:
            try:
                surge, sway, heave, _, _, yaw = self.get_keyboard_control_inputs()
                
                # Scale -1.0..1.0 to -1000..1000
                x = int(surge * 1000)
                y = int(sway * 1000)
                z = int(heave * 1000)
                r = int(yaw * 1000)
                
                buttons = 0
                if self.headlights_active:
                    buttons |= (1 << 0) # bit 0 for lights on GCS
                    
                master = mavutil.mavlink_connection('udpout:127.0.0.1:14550', source_system=255)
                master.mav.manual_control_send(
                    1, # Target system
                    x, y, z, r, buttons
                )
            except Exception as e:
                pass

    # ----------------------------------------------------
    # MAIN SIMULATION LOOP (60 Hz)
    # ----------------------------------------------------
    def frame_update(self):
        # 1. Update Clock Date/Time
        utc_time = QtCore.QDateTime.currentDateTimeUtc().toString("hh:mm:ss")
        utc_date = QtCore.QDateTime.currentDateTimeUtc().toString("yyyy-MM-dd")
        self.clock_lbl.setText(f"{utc_time} UTC\n{utc_date}")
        
        # 2. Connection Strength Watchdog
        if not self.is_simulation_mode:
            time_since_telem = time.time() - self.last_telemetry_time
            if time_since_telem > 3.0:
                self.conn_progress.setValue(0)
                self.status_val.setText("DISCONNECTED")
                self.status_val.setStyleSheet("color: #ff3333; font-weight: bold;")
            elif time_since_telem > 1.0:
                self.conn_progress.setValue(35)
                self.status_val.setText("WEAK LINK")
                self.status_val.setStyleSheet("color: #ffcc00; font-weight: bold;")
            else:
                self.conn_progress.setValue(100)
                self.status_val.setText("ACTIVE (MAV)")
                self.status_val.setStyleSheet("color: #00ff66; font-weight: bold;")

        # 3. Step Local Physics if GCS is running in offline simulation mode
        if self.is_simulation_mode:
            # Read keyboard inputs
            surge, sway, heave, roll, pitch, yaw = self.get_keyboard_control_inputs()
            
            # Apply to simulation
            self.dynamics.set_control_input(surge, sway, heave, roll, pitch, yaw)
            
            # Substep physics
            state = None
            for _ in range(self.physics_substeps):
                state = self.dynamics.step(self.dt_physics)
                
            if state is not None:
                # Update GCS state attributes from simulation
                self.rov_pos = state["position"]
                self.rov_quat = state["orientation_quat"]
                self.rov_roll = state["roll"]
                self.rov_pitch = state["pitch"]
                self.rov_yaw = state["heading"]
                
                # Render 3D and Radar update
                self.gl_widget.update_pose(self.rov_pos, self.rov_quat)
                self.radar_widget.update_state(self.rov_pos, self.rov_roll, self.rov_pitch, self.rov_yaw)
                
                # Update UI telemetry bars
                thruster_vals = state["thruster_outputs"]
                for idx, val in enumerate(thruster_vals):
                    if idx < len(self.thruster_bars):
                        self.thruster_bars[idx].setValue(val)
                # Compute total thruster load
                self.bar_load.setValue(int(np.mean(thruster_vals)))
                
                # Update dynamic sensors (voltage draining, pH fluctuations)
                self.battery_v = max(11.0, self.battery_v - 0.0001 - 0.001 * (np.mean(thruster_vals)/100))
                self.battery_a = 1.2 + 0.12 * np.mean(thruster_vals)
                self.temp_water += random.uniform(-0.02, 0.02)
                self.ph_level += random.uniform(-0.005, 0.005)

        # 4. Refresh Dashboard Panels & Telemetry labels
        self.lbl_pos_val.setText(f"X: {self.rov_pos[0]:.2f} M\nY: {self.rov_pos[1]:.2f} M\nZ: {self.rov_pos[2]:.2f} M")
        
        # Calculate velocity vector
        if self.is_simulation_mode:
            vel = self.dynamics.step(0.0)["linear_velocity"] # read current speed
        else:
            vel = [0.0, 0.0, 0.0] # live telemetry Ned speeds
            
        self.lbl_vel_val.setText(f"X: {vel[0]:.1f} M/S\nY: {vel[1]:.1f} M/S\nZ: {vel[2]:.1f} M/S")
        self.lbl_ang_val.setText(f"HEADING: {self.rov_yaw:05.1f}°\nPITCH: {self.rov_pitch:+.1f}°\nROLL: {self.rov_roll:+.1f}°")
        
        self.lbl_bat_metrics.setText(f"VOLTAGE: {self.battery_v:.2f}V | CURRENT: {self.battery_a:.1f}A")
        self.bar_bat.setValue(int((self.battery_v - 11.0) / (14.8 - 11.0) * 100))

        # Update Telemetry Table Row Values
        metrics_mapping = [
            ("DEPTH", f"{self.rov_pos[2]:.1f} M"),
            ("WATER TEMP", f"{self.temp_water:.2f} °C"),
            ("SALINITY", f"{self.salinity:.1f} PSU"),
            ("PRESSURE", f"{abs(self.rov_pos[2]) * 0.1 + 1.013:.2f} BAR"),
            ("VOLTAGE", f"{self.battery_v:.2f} V"),
            ("CURRENT", f"{self.battery_a:.1f} A")
        ]
        
        for idx, (param_name, val_str) in enumerate(metrics_mapping):
            self.telemetry_table.setItem(idx, 0, QTableWidgetItem(param_name))
            self.telemetry_table.setItem(idx, 1, QTableWidgetItem(val_str))
            
            # Flag warnings on battery or deep pressure
            status = "NOMINAL"
            color_str = "#00ff66"
            if param_name == "VOLTAGE" and self.battery_v < 11.8:
                status = "LOW VOLT ALERT"
                color_str = "#ff3333"
            elif param_name == "DEPTH" and abs(self.rov_pos[2]) > 30.0:
                status = "DEEP OPERATION"
                color_str = "#ffcc00"
                
            status_item = QTableWidgetItem(status)
            status_item.setForeground(QColor(color_str))
            self.telemetry_table.setItem(idx, 2, status_item)

    def closeEvent(self, event):
        # Stop receiver threads
        self.slam_thread.terminate()
        self.telemetry_thread.terminate()
        self.dynamics.close()
        event.accept()

def main():
    app = QApplication(sys.argv)
    window = ROVGCSWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
