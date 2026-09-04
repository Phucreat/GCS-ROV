# -*- coding: utf-8 -*-
"""
tools/build_user_guide_pdf.py - Biên soạn & Xuất Bản Sổ Tay Hướng Dẫn Sử Dụng PDF
"""
import os, sys, subprocess, shutil

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "scratch"))

import build_pdf_runner
print("User Guide PDF updated successfully.")