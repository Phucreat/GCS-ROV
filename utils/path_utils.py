r"""
utils/path_utils.py - Enterprise Safe Path & Directory Resolver
===============================================================
Ensures proper Windows folder separation:
- Read-Only App Binaries: Program Files / PyInstaller internal
- Writable User State / SQLite DB / Logs: %LOCALAPPDATA%\CNC_NExora
- Writable Media / Recordings / Snapshots: ~/Documents/CNC_NExora_Media
"""

import os
import sys

def get_app_data_dir() -> str:
    """Trả về thư mục AppData có đầy đủ quyền đọc/ghi (Read/Write)."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
        app_dir = os.path.join(base, "CNC_NExora")
    else:
        app_dir = os.path.expanduser("~/.cnc_nexora")
    try:
        os.makedirs(app_dir, exist_ok=True)
    except Exception:
        pass
    return app_dir

def get_db_path() -> str:
    """Trả về đường dẫn tệp cơ sở dữ liệu SQLite WAL an toàn."""
    db_dir = os.path.join(get_app_data_dir(), "logs", "db")
    try:
        os.makedirs(db_dir, exist_ok=True)
    except Exception:
        pass
    return os.path.join(db_dir, "gcs_database.db")

def get_logs_dir() -> str:
    """Trả về thư mục ghi logs hoạt động."""
    log_dir = os.path.join(get_app_data_dir(), "logs")
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception:
        pass
    return log_dir

def get_crash_dump_dir() -> str:
    """Trả về thư mục lưu crash dumps."""
    dump_dir = os.path.join(get_app_data_dir(), "logs", "crash_dumps")
    try:
        os.makedirs(dump_dir, exist_ok=True)
    except Exception:
        pass
    return dump_dir

def get_default_media_dir() -> str:
    """Trả về thư mục lưu video/snapshot mặc định trong Documents."""
    docs = os.path.join(os.path.expanduser("~"), "Documents", "CNC_NExora_Media")
    try:
        os.makedirs(docs, exist_ok=True)
        return docs
    except Exception:
        fallback = os.path.join(get_app_data_dir(), "media")
        try:
            os.makedirs(fallback, exist_ok=True)
        except Exception:
            pass
        return fallback

def get_tts_cache_dir() -> str:
    """Trả về thư mục lưu cache audio tts."""
    cache = os.path.join(get_app_data_dir(), "cache", "tts")
    try:
        os.makedirs(cache, exist_ok=True)
    except Exception:
        pass
    return cache

def get_resource_path(relative_path: str) -> str:
    """
    Trả về đường dẫn tuyệt đối chính xác cho tài nguyên (mô hình 3D, YOLO model, config)
    kể cả khi chạy file .exe đóng gói (PyInstaller one-dir / one-file) hoặc chạy từ source.
    """
    if not relative_path:
        return ""
    if os.path.isabs(relative_path) and os.path.exists(relative_path):
        return relative_path

    # 1. PyInstaller _MEIPASS (one-file mode)
    if hasattr(sys, '_MEIPASS'):
        p = os.path.join(sys._MEIPASS, relative_path)
        if os.path.exists(p):
            return p

    # 2. Bên cạnh file thực thi .exe (one-dir mode)
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    p_exe = os.path.join(exe_dir, relative_path)
    if os.path.exists(p_exe):
        return p_exe

    # 3. Trong thư mục _internal của PyInstaller
    p_internal = os.path.join(exe_dir, "_internal", relative_path)
    if os.path.exists(p_internal):
        return p_internal

    # 4. Thư mục gốc source code
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p_root = os.path.join(root_dir, relative_path)
    if os.path.exists(p_root):
        return p_root

    # 5. Thư mục làm việc hiện tại
    p_cwd = os.path.join(os.getcwd(), relative_path)
    if os.path.exists(p_cwd):
        return p_cwd

    return relative_path