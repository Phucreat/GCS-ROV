"""
test_main_launch.py - Launch verification for GCS ROV with WebRTC and AI
"""
import sys
import os
import subprocess
import time

python_exe = os.path.abspath("env/Scripts/python.exe")
main_py = os.path.abspath("main.py")

print("[Launch Test] Testing launch of main.py --mock for 5 seconds...")
proc = subprocess.Popen(
    [python_exe, main_py, "--mock"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    cwd=os.path.abspath(".")
)

time.sleep(5)
is_running = (proc.poll() is None)
if is_running:
    print(" -> SUCCESS: GCS ROV Main GUI successfully launched and is running normally!")
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except Exception:
        proc.kill()
    sys.exit(0)
else:
    stdout, stderr = proc.communicate()
    print(" -> FAILED: Process exited unexpectedly.")
    print("STDOUT:\n", stdout[:1000])
    print("STDERR:\n", stderr[:1000])
    sys.exit(1)
