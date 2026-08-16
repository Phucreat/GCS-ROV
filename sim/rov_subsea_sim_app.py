"""
rov_subsea_sim_app.py - Standalone Subsea ROV 3D Digital Twin Simulator Executable Entry Point
=============================================================================================
Standalone 3D Subsea Simulation Engine. Receives 60Hz 6-DOF ROV telemetry and environment commands
over UDP port 8888 and renders a high-fidelity 3D Subsea Digital Twin simulation.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PyQt6 import QtCore, QtGui, QtWidgets
from GUI.widgets.gl_3d_widget import GLROVWidget


class StandaloneROVSimulatorWindow(QtWidgets.QMainWindow):
    """
    Standalone Commercial 3D Subsea ROV Simulator Window.
    """

    def __init__(self, udp_port: int = 8888) -> None:
        super().__init__()
        self.udp_port = udp_port

        self.setWindowTitle("🎮 ROV SUBSEA DIGITAL TWIN SIMULATOR ENGINE (COMMERCIAL STAGE)")
        self.resize(1280, 720)

        # Central 3D OpenGL Viewport
        self.gl_3d = GLROVWidget(parent=self)
        self.setCentralWidget(self.gl_3d)

        # Header Status Bar
        self.statusBar().showMessage(f"🟢 UDP 60Hz Subsea Telemetry Receiver listening on port {udp_port}")
        self.statusBar().setStyleSheet("background: #060B14; color: #00FF9D; font-weight: bold;")

        # UDP Receiver Thread
        self._running = True
        self._udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._udp_socket.bind(("0.0.0.0", udp_port))
        self._udp_socket.settimeout(0.2)

        self._recv_thread = threading.Thread(target=self._udp_loop, daemon=True)
        self._recv_thread.start()

    def _udp_loop(self) -> None:
        """Background thread listening for 60Hz UDP telemetry packets from GCS."""
        while self._running:
            try:
                data, _ = self._udp_socket.recvfrom(4096)
                if data:
                    packet = json.loads(data.decode("utf-8"))
                    cmd = packet.get("cmd", "")

                    if cmd == "POSE_UPDATE" or "x" in packet:
                        x = float(packet.get("x", 0.0))
                        y = float(packet.get("y", 0.0))
                        z = float(packet.get("z", 0.0))
                        roll = float(packet.get("roll", 0.0))
                        pitch = float(packet.get("pitch", 0.0))
                        yaw = float(packet.get("yaw", 0.0))
                        # Update 3D ROV position in OpenGL viewport
                        QtCore.QMetaDataMethod.invokeMethod
                        QtCore.QMetaObject.invokeMethod(
                            self.gl_3d,
                            "update_pose",
                            QtCore.Qt.ConnectionType.QueuedConnection,
                            QtCore.Q_ARG(float, x),
                            QtCore.Q_ARG(float, y),
                            QtCore.Q_ARG(float, z),
                            QtCore.Q_ARG(float, roll),
                            QtCore.Q_ARG(float, pitch),
                            QtCore.Q_ARG(float, yaw)
                        )
                    elif cmd == "CHANGE_MAP":
                        map_name = packet.get("map_preset", "OFFSHORE")
                        print(f"[StandaloneSim] Changed Map Level to: {map_name}")
                    elif cmd == "SET_TURBIDITY":
                        turb = packet.get("turbidity", 0.2)
                        print(f"[StandaloneSim] Changed Water Turbidity to: {turb}")
            except socket.timeout:
                continue
            except Exception as exc:
                continue

    def closeEvent(self, event) -> None:
        self._running = False
        try:
            self._udp_socket.close()
        except Exception:
            pass
        event.accept()


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("ROV Subsea Digital Twin Simulator Engine")
    win = StandaloneROVSimulatorWindow(udp_port=8888)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
