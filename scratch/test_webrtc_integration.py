import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PyQt6 import QtCore
try:
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
except Exception:
    pass

from GUI.widgets.webrtc_player_widget import WebRTCPlayerWidget
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

def run_tests():
    print("==================================================")
    print("STARTING WEBRTC + AI PIPELINE INTEGRATION AUDIT")
    print("==================================================")

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    # 1. Test WebRTCPlayerWidget instantiation
    print("[Test 1] Testing WebRTCPlayerWidget initialization...")
    widget = WebRTCPlayerWidget(webrtc_url="http://192.168.2.2:8889/cam")
    assert widget is not None, "Failed to instantiate WebRTCPlayerWidget"
    assert widget._webrtc_url == "http://192.168.2.2:8889/cam"
    print(" -> PASSED: WebRTCPlayerWidget successfully initialized.")

    # 2. Test Detection JSON Serialization
    print("[Test 2] Testing set_detections normalization and handling...")
    from GUI.widgets.ai_vision_processor import Detection
    d1 = Detection(class_name="diver", confidence=0.92, x1=100, y1=80, x2=300, y2=240, track_id=1)
    d1._frame_w = 640
    d1._frame_h = 480
    d2 = Detection(class_name="pipe", confidence=0.88, x1=50, y1=200, x2=550, y2=320, track_id=2)
    d2._frame_w = 640
    d2._frame_h = 480

    widget.set_detections([d1, d2])
    assert len(widget._detections) == 2, "Expected 2 normalized detections"
    assert widget._detections[0]["class_name"] == "diver"
    assert round(widget._detections[0]["x1"], 2) == round(100 / 640, 2)
    print(" -> PASSED: Detection normalized coordinates and formatting valid.")

    # 3. Test Telemetry Updates
    print("[Test 3] Testing update_telemetry...")
    widget.update_telemetry(
        roll=5.2, pitch=-2.1, yaw=145.0, depth=12.4, heading=145.0,
        voltage=15.8, current=4.2, pct=85.0, mode="ALT_HOLD", armed=True
    )
    assert widget._telemetry["depth"] == 12.4
    assert widget._telemetry["heading"] == 145.0
    assert widget._telemetry["mode"] == "ALT_HOLD"
    assert widget._telemetry["armed"] is True
    print(" -> PASSED: Telemetry state cached and ready for HUD render.")

    # 4. Test Background AI RTSP Worker Initialization
    print("[Test 4] Testing VideoReceiver RTSP worker initialization for AI (12 FPS)...")
    from network.video_receiver import VideoReceiver, VideoSource
    rx = VideoReceiver(
        source_type=VideoSource.RTSP,
        url_or_index="rtsp://192.168.2.2:8555/cam",
        target_fps=12,
        target_w=640,
        target_h=480
    )
    assert rx._target_fps == 12
    assert rx._target_w == 640
    assert rx._target_h == 480
    assert rx._url_or_index == "rtsp://192.168.2.2:8555/cam"
    print(" -> PASSED: Background VideoReceiver configured for AI stream at 12 FPS.")

    # 5. Test Settings Dialog
    print("[Test 5] Testing SettingsDialog video sources and URLs...")
    from GUI.widgets.settings_dialog import SettingsDialog
    dummy_settings = {
        "video_source": "webrtc",
        "webrtc_url": "http://192.168.2.2:8889/cam",
        "rtsp_url": "rtsp://192.168.2.2:8555/cam",
        "udp_video_port": 5620,
        "webcam_index": 0,
        "video_fps": 30,
        "video_resolution": "1280x720",
        "ar_hud_enabled": True,
        "ai_detection_enabled": False,
    }
    dlg = SettingsDialog(dummy_settings)
    assert dlg.cb_vid_source.count() == 5
    assert dlg.cb_vid_source.currentIndex() == 0  # WebRTC
    assert dlg.ed_webrtc_url.text() == "http://192.168.2.2:8889/cam"
    assert dlg.ed_rtsp_url.text() == "rtsp://192.168.2.2:8555/cam"
    print(" -> PASSED: SettingsDialog correctly configures WebRTC & RTSP options.")

    print("\n==================================================")
    print("ALL INTEGRATION TESTS COMPLETED SUCCESSFULLY (5/5)")
    print("==================================================")

if __name__ == "__main__":
    run_tests()
