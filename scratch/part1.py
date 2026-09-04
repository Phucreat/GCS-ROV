# -*- coding: utf-8 -*-
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

css = """
@page {
    size: A4 portrait;
    margin: 15mm 13mm 15mm 13mm;
    @bottom-right {
        content: "Trang " counter(page);
    }
}
* {
    box-sizing: border-box;
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
}
body {
    font-family: 'Segoe UI', Arial, sans-serif;
    color: #1E293B;
    background-color: #FFFFFF;
    line-height: 1.55;
    font-size: 13px;
    margin: 0;
    padding: 0;
}
.page-break {
    page-break-before: always;
}
.cover-page {
    height: 100%;
    min-height: 250mm;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    border: 3px solid #0284C7;
    border-radius: 12px;
    padding: 35px 30px;
    background: linear-gradient(135deg, #F0F9FF 0%, #E0F2FE 50%, #F8FAFC 100%);
}
.cover-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 2px solid #BAE6FD;
    padding-bottom: 15px;
}
.cover-logo img {
    max-height: 65px;
    border-radius: 6px;
}
.cover-badge {
    background-color: #0369A1;
    color: #FFFFFF;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
    padding: 6px 14px;
    border-radius: 20px;
    text-transform: uppercase;
}
.cover-body {
    margin: auto 0;
    text-align: center;
}
.cover-title-sub {
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 2px;
    color: #0284C7;
    text-transform: uppercase;
    margin-bottom: 8px;
}
.cover-title-main {
    font-size: 29px;
    font-weight: 800;
    color: #0F172A;
    line-height: 1.25;
    margin: 0 0 12px 0;
}
.cover-desc {
    font-size: 13.5px;
    color: #475569;
    max-width: 550px;
    margin: 0 auto 18px auto;
}
.cover-mockup {
    margin: 10px auto;
    max-width: 90%;
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 10px 24px rgba(2, 132, 199, 0.22);
    border: 2px solid #38BDF8;
}
.cover-mockup img {
    width: 100%;
    display: block;
}
.cover-footer {
    border-top: 2px solid #BAE6FD;
    padding-top: 12px;
    display: flex;
    justify-content: space-between;
    font-size: 11.5px;
    color: #64748B;
}
h1 {
    font-size: 18px;
    color: #0369A1;
    border-left: 5px solid #0284C7;
    padding-left: 10px;
    margin-top: 20px;
    margin-bottom: 10px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
h2 {
    font-size: 14.5px;
    color: #0F172A;
    border-bottom: 1.5px solid #E2E8F0;
    padding-bottom: 4px;
    margin-top: 16px;
    margin-bottom: 8px;
}
h3 {
    font-size: 13px;
    color: #0284C7;
    margin-top: 12px;
    margin-bottom: 5px;
}
p {
    margin-top: 0;
    margin-bottom: 8px;
    color: #334155;
}
.callout {
    border-radius: 8px;
    padding: 10px 14px;
    margin: 10px 0;
    font-size: 12px;
}
.callout-info {
    background-color: #F0F9FF;
    border-left: 4px solid #0284C7;
    color: #0C4A6E;
}
.callout-tip {
    background-color: #ECFDF5;
    border-left: 4px solid #10B981;
    color: #064E3B;
}
.callout-warn {
    background-color: #FFFBEB;
    border-left: 4px solid #F59E0B;
    color: #78350F;
}
.callout-title {
    font-weight: 700;
    margin-bottom: 3px;
}
table {
    width: 100%;
    border-collapse: collapse;
    margin: 10px 0;
    font-size: 11.5px;
}
th, td {
    border: 1px solid #CBD5E1;
    padding: 6px 8px;
    text-align: left;
}
th {
    background-color: #F1F5F9;
    color: #0F172A;
    font-weight: 700;
}
tr:nth-child(even) {
    background-color: #F8FAFC;
}
.key-badge {
    display: inline-block;
    background: #E2E8F0;
    border: 1px solid #94A3B8;
    border-radius: 4px;
    padding: 1px 5px;
    font-family: Consolas, monospace;
    font-size: 11px;
    font-weight: 700;
    color: #1E293B;
}
.badge-status {
    display: inline-block;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 10.5px;
    font-weight: bold;
}
.badge-green { background: #DCFCE7; color: #166534; }
.badge-amber { background: #FEF3C7; color: #92400E; }
.badge-blue { background: #DBEAFE; color: #1E40AF; }
.step-container {
    margin: 8px 0;
}
.step-item {
    display: flex;
    align-items: flex-start;
    margin-bottom: 8px;
}
.step-num {
    flex-shrink: 0;
    width: 22px;
    height: 22px;
    background-color: #0284C7;
    color: #FFFFFF;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: bold;
    font-size: 11px;
    margin-right: 8px;
    margin-top: 2px;
}
.step-content {
    flex: 1;
}
.step-content strong {
    color: #0F172A;
    display: block;
}
.toc-box {
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    padding: 12px 16px;
    margin: 14px 0;
}
.toc-item {
    display: flex;
    justify-content: space-between;
    padding: 3.5px 0;
    border-bottom: 1px dotted #CBD5E1;
    font-size: 12px;
}
.toc-item:last-child {
    border-bottom: none;
}
.toc-item span:first-child {
    color: #0369A1;
    font-weight: 600;
}
.toc-page {
    color: #64748B;
    font-weight: 600;
}
.img-caption {
    font-size: 11px;
    color: #64748B;
    text-align: center;
    font-style: italic;
    margin-top: 3px;
    margin-bottom: 10px;
}
"""