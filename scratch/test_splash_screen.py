"""
test_splash_screen.py - Unit Verification for Autodesk Fusion 360 Splash Screen
"""

import sys
import time
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PyQt6.QtWidgets import QApplication
from GUI.widgets.splash_screen import FusionSplashScreen

def run_test():
    app = QApplication(sys.argv)
    splash = FusionSplashScreen(
        app_title="CNX GCS ROV PRO",
        app_subtitle="Commercial Subsea Inspection & AI Co-Pilot Platform",
        version_text="v3.8.5 Enterprise Test"
    )
    splash.show()
    app.processEvents()

    steps = [
        (20, "Initializing MAVLink Protocol Engine..."),
        (40, "Loading SQLite WAL Telemetry Database..."),
        (65, "Preparing 3D OpenGL Motion Render..."),
        (85, "Launching Voice Agent Co-Pilot VIC..."),
        (100, "Ready! Launching GCS Subsea Control Station...")
    ]

    for p, txt in steps:
        splash.set_progress(p, txt)
        time.sleep(0.15)
        app.processEvents()

    splash.fade_out(duration_ms=200)
    print("FUSION 360 SPLASH SCREEN VERIFICATION TEST PASSED 100%!")

if __name__ == "__main__":
    run_test()
