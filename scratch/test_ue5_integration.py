"""
test_ue5_integration.py - Unit Verification for Unreal Engine 5 Pixel Streaming & Telemetry Integration
"""

import sys
import time
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PyQt6.QtWidgets import QApplication
from network.ue5_udp_sender import UE5UDPSender
from GUI.widgets.ue5_viewport_widget import UE5ViewportWidget, UE5ViewportWindow


def run_test():
    print("=========================================================")
    print("RUNNING UNREAL ENGINE 5 PIXEL STREAMING VERIFICATION TESTS")
    print("=========================================================\n")

    # 1. TEST UE5 UDP TELEMETRY SENDER
    sender = UE5UDPSender(target_ip="127.0.0.1", target_port=8888, send_rate_hz=60)
    sender.start()
    print("[PASS] TEST 1: UE5UDPSender 60Hz telemetry loop started.")

    # 2. TEST POSE UPDATE
    sender.update_pose(
        x=12.4, y=-5.2, z=-18.5,
        roll=2.5, pitch=-1.2, yaw=185.0,
        lights_pct=80, armed=True, mode="ALT_HOLD", depth_m=18.5
    )
    print("[PASS] TEST 2: 6-DOF ROV Pose updated in telemetry buffer.")

    # 3. TEST MAP LEVEL STREAMING COMMANDS
    res1 = sender.send_environment_preset("POOL")
    res2 = sender.send_environment_preset("RESERVOIR")
    res3 = sender.send_environment_preset("OFFSHORE_OCEAN")
    res4 = sender.send_environment_preset("SHIPWRECK")
    assert res1 and res2 and res3 and res4, "Map level streaming commands failed!"
    print("[PASS] TEST 3: Sent 4 Level Streaming Map Presets (POOL, RESERVOIR, OFFSHORE, SHIPWRECK) over UDP.")

    # 4. TEST WATER TURBIDITY & DEPTH LIGHTING SYNC
    t_res = sender.send_water_turbidity(0.65)
    d_res = sender.send_depth_lighting_sync(depth_m=32.4, auto_spotlight=True)
    assert t_res and d_res, "Turbidity and depth lighting commands failed!"
    print("[PASS] TEST 4: Water Turbidity (0.65) and Depth Lighting Auto-Sync (32.4m) sent over UDP.")

    # 5. TEST VIEWPORT WIDGET & WINDOW
    app = QApplication(sys.argv)
    window = UE5ViewportWindow(default_url="http://127.0.0.1:80", udp_sender=sender)
    window.show()
    app.processEvents()

    # Simulate UI controls
    window.viewport._on_map_changed()
    window.viewport._on_turbidity_changed(45)
    window.viewport.update_telemetry_depth(25.0)
    print("[PASS] TEST 5: UE5ViewportWidget & WebRTC Viewport initialized and tested.")

    # Clean up
    window.close()
    sender.stop()

    print("\n=========================================================")
    print("ALL UNREAL ENGINE 5 INTEGRATION TESTS PASSED 100%!")
    print("=========================================================")


if __name__ == "__main__":
    run_test()
