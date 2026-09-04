# -*- coding: utf-8 -*-
import os, sys, subprocess, shutil
from part1 import css, logo_b64, app_ui_b64, PROJECT_ROOT, OUTPUT_PDF_ROOT, OUTPUT_PDF_DIST, HTML_TEMP_PATH
from part2 import build_html_body

body_content = build_html_body(logo_b64, app_ui_b64)

full_html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>HƯỚNG DẪN SỬ DỤNG - CNC NEXORA GCS</title>
    <style>
        {css}
    </style>
</head>
<body>
    {body_content}
</body>
</html>
"""

with open(HTML_TEMP_PATH, "w", encoding="utf-8") as f:
    f.write(full_html)

print(f"HTML saved at {HTML_TEMP_PATH} ({os.path.getsize(HTML_TEMP_PATH)} bytes)")

edge_candidates = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]
edge_path = None
for p in edge_candidates:
    if os.path.exists(p):
        edge_path = p
        break

if not edge_path:
    print("Edge not found!")
    sys.exit(1)

print(f"Executing Edge headless PDF generator...")
edge_cmd = [
    edge_path,
    "--headless",
    "--disable-gpu",
    "--no-pdf-header-footer",
    f"--print-to-pdf={OUTPUT_PDF_ROOT}",
    f"file:///{HTML_TEMP_PATH.replace(os.sep, '/')}"
]

proc = subprocess.run(edge_cmd, capture_output=True, text=True)

if os.path.exists(OUTPUT_PDF_ROOT) and os.path.getsize(OUTPUT_PDF_ROOT) > 1000:
    shutil.copyfile(OUTPUT_PDF_ROOT, OUTPUT_PDF_DIST)
    size_kb = os.path.getsize(OUTPUT_PDF_ROOT) / 1024
    print(f"SUCCESS: Generated PDF at {OUTPUT_PDF_ROOT} ({size_kb:.1f} KB)")
    print(f"COPIED to {OUTPUT_PDF_DIST}")
else:
    print(f"ERROR: {proc.stderr}")