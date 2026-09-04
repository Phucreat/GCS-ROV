import os, sys, base64, subprocess, shutil

PROJECT_ROOT = r"D:\python\GCS_ROV"
OUTPUT_PDF_ROOT = os.path.join(PROJECT_ROOT, "HUONG_DAN_SU_DUNG_CNC_NEXORA_GCS.pdf")
OUTPUT_PDF_DIST = os.path.join(PROJECT_ROOT, "Output", "HUONG_DAN_SU_DUNG_CNC_NEXORA_GCS.pdf")
HTML_TEMP_PATH = os.path.join(PROJECT_ROOT, "scratch", "user_guide.html")

os.makedirs(os.path.join(PROJECT_ROOT, "scratch"), exist_ok=True)
os.makedirs(os.path.join(PROJECT_ROOT, "Output"), exist_ok=True)

def img_to_base64(path, mime="image/png"):
    if os.path.exists(path):
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")
            return f"data:{mime};base64,{data}"
    return ""

logo_b64 = img_to_base64(os.path.join(PROJECT_ROOT, "assets", "logo.jpg"), "image/jpeg")
app_ui_b64 = img_to_base64(os.path.join(PROJECT_ROOT, "assets", "app_interface.png"), "image/png")
print("Assets loaded to Base64.")