"""
splash_screen.py - Autodesk Fusion 360 Style Premium Splash Screen
===================================================================
Splash screen khởi động ứng dụng đẳng cấp thương mại Fusion 360:
- Cửa sổ tràn viền không viền (Frameless Window) với bóng mờ hiện đại.
- Hỗ trợ hiển thị 1 ảnh hoặc Trình chiếu Slide ảnh (Image Carousel/Slider) khi chờ loading.
- Thanh Progress Bar cyan phát sáng tinh tế ở cạnh dưới (Bottom Bar).
- Nhãn hiển thị tiến trình khởi động ngầm thời gian thực (Real-time Status Text).
- Hiệu ứng xuất hiện (Fade-In) và mờ dần (Fade-Out) chuyển cảnh mượt mà.
"""

from __future__ import annotations

import os
import time
from typing import List, Optional

try:
    from PyQt6.QtCore import (
        Qt,
        QTimer,
        QPropertyAnimation,
        QEasingCurve,
        pyqtSignal,
        QRect,
        QSize,
    )
    from PyQt6.QtGui import (
        QPixmap,
        QPainter,
        QColor,
        QLinearGradient,
        QFont,
        QBrush,
        QPen,
        QGuiApplication,
    )
    from PyQt6.QtWidgets import (
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QProgressBar,
        QGraphicsOpacityEffect,
        QFrame,
        QApplication,
    )
    _PYQT6 = True
except ImportError:
    from PyQt5.QtCore import (
        Qt,
        QTimer,
        QPropertyAnimation,
        QEasingCurve,
        pyqtSignal,
        QRect,
        QSize,
    )
    from PyQt5.QtGui import (
        QPixmap,
        QPainter,
        QColor,
        QLinearGradient,
        QFont,
        QBrush,
        QPen,
        QGuiApplication,
    )
    from PyQt5.QtWidgets import (
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QProgressBar,
        QGraphicsOpacityEffect,
        QFrame,
        QApplication,
    )
    _PYQT6 = False


class FusionSplashScreen(QWidget):
    """
    Autodesk Fusion 360 Style Premium Splash Screen.
    """

    sig_finished = pyqtSignal()

    def __init__(
        self,
        image_paths: Optional[List[str]] = None,
        app_title: str = "CNX GCS ROV PRO",
        app_subtitle: str = "Commercial Subsea Inspection & AI Co-Pilot Platform",
        version_text: str = "v3.8.5 Enterprise",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self._app_title = app_title
        self._app_subtitle = app_subtitle
        self._version_text = version_text

        # List of image slides for carousel slider
        self._image_paths: List[str] = image_paths or []
        self._current_slide_idx: int = 0
        self._slide_pixmaps: List[QPixmap] = []

        # Window properties (850x500 fixed size like Fusion 360)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.SplashScreen
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(850, 500)

        # Build UI layout & Opacity Animation
        self._build_ui()
        self._load_slide_images()
        self._center_on_screen()

        # Timer for slideshow auto-rotate if multiple images exist
        self._slide_timer = QTimer(self)
        self._slide_timer.timeout.connect(self._next_slide)
        if len(self._slide_pixmaps) > 1:
            self._slide_timer.start(2500)  # Rotate every 2.5 seconds

        # Opacity effect for smooth Fade-In / Fade-Out
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        self._opacity_effect.setOpacity(1.0)

    def _center_on_screen(self) -> None:
        """Center the splash screen on the primary monitor."""
        screen = QGuiApplication.primaryScreen()
        if screen:
            geo = screen.geometry()
            x = (geo.width() - self.width()) // 2
            y = (geo.height() - self.height()) // 2
            self.move(x, y)

    def _load_slide_images(self) -> None:
        """Discover and load splash images from GUI/img/splash or GUI/img."""
        if not self._image_paths:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            splash_dir = os.path.join(base_dir, "img", "splash")
            img_dir = os.path.join(base_dir, "img")

            # 1. Primary: Load ALL images in GUI/img/splash/ without restriction!
            if os.path.exists(splash_dir):
                for f in sorted(os.listdir(splash_dir)):
                    if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                        self._image_paths.append(os.path.join(splash_dir, f))

            # 2. Fallback: Search GUI/img/ if splash folder is empty
            if not self._image_paths and os.path.exists(img_dir):
                for f in sorted(os.listdir(img_dir)):
                    if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                        if any(k in f.lower() for k in ["splash", "slide", "desktop", "banner", "logo"]):
                            self._image_paths.append(os.path.join(img_dir, f))

        # Convert valid image paths to QPixmap
        for path in self._image_paths:
            if os.path.exists(path):
                pix = QPixmap(path)
                if not pix.isNull():
                    self._slide_pixmaps.append(pix)

        # Update initial slide if images exist
        if self._slide_pixmaps:
            self._update_slide_display()

    def _build_ui(self) -> None:
        """Construct Autodesk Fusion 360 styled layout."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Container Frame (Dark rounded container)
        self.container = QFrame(self)
        self.container.setStyleSheet(
            """
            QFrame {
                background-color: #060B14;
                border: 1px solid rgba(0, 229, 255, 0.25);
                border-radius: 8px;
            }
            """
        )
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # Top Hero Content Area (Image / Branding)
        self.hero_widget = QWidget(self.container)
        self.hero_widget.setStyleSheet("background: transparent;")
        hero_layout = QVBoxLayout(self.hero_widget)
        hero_layout.setContentsMargins(32, 28, 32, 20)

        # Top Header Row (Logo + Title + Version)
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        # Orange Fusion-Style Icon Box
        self.icon_box = QLabel("F")
        self.icon_box.setFixedSize(48, 48)
        self.icon_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_box.setStyleSheet(
            """
            QLabel {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FF6D00, stop:1 #FF3D00);
                color: #FFFFFF;
                font-family: 'Segoe UI', sans-serif;
                font-weight: 900;
                font-size: 26px;
                border-radius: 6px;
            }
            """
        )
        header_row.addWidget(self.icon_box)

        # Title & Subtitle Stack
        title_stack = QVBoxLayout()
        title_stack.setSpacing(2)

        self.lbl_title = QLabel(self._app_title)
        self.lbl_title.setStyleSheet(
            "color: #FFFFFF; font-family: 'Segoe UI', 'Rajdhani', sans-serif; font-size: 24px; font-weight: bold; letter-spacing: 1px;"
        )
        self.lbl_subtitle = QLabel(self._app_subtitle)
        self.lbl_subtitle.setStyleSheet(
            "color: #00E5FF; font-family: 'Segoe UI', sans-serif; font-size: 12px; font-weight: 600;"
        )

        title_stack.addWidget(self.lbl_title)
        title_stack.addWidget(self.lbl_subtitle)
        header_row.addLayout(title_stack)
        header_row.addStretch(1)

        # Right Enterprise Badge
        self.lbl_brand_right = QLabel("CNC NExos")
        self.lbl_brand_right.setStyleSheet(
            "color: #94A9C4; font-family: 'Segoe UI', sans-serif; font-weight: bold; font-size: 13px; letter-spacing: 1.5px;"
        )
        header_row.addWidget(self.lbl_brand_right, alignment=Qt.AlignmentFlag.AlignTop)

        hero_layout.addLayout(header_row)

        # Center Slideshow Image / Visual Art Banner
        self.lbl_image_banner = QLabel(self.hero_widget)
        self.lbl_image_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_image_banner.setStyleSheet("background: transparent;")
        hero_layout.addWidget(self.lbl_image_banner, stretch=1)

        container_layout.addWidget(self.hero_widget, stretch=1)

        # ── Fusion 360 Bottom Loading Bar (Footer) ────────────────────────── #
        self.bottom_bar = QWidget(self.container)
        self.bottom_bar.setFixedHeight(44)
        self.bottom_bar.setStyleSheet(
            """
            QWidget {
                background-color: #040810;
                border-top: 1px solid rgba(255, 255, 255, 0.08);
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
            }
            """
        )
        bottom_layout = QHBoxLayout(self.bottom_bar)
        bottom_layout.setContentsMargins(24, 0, 24, 0)
        bottom_layout.setSpacing(16)

        # Status text at bottom left ("Initializing...")
        self.lbl_status = QLabel("Initializing application...")
        self.lbl_status.setStyleSheet(
            "color: #94A9C4; font-family: 'Segoe UI', 'Consolas', sans-serif; font-size: 12px; font-weight: 500;"
        )
        bottom_layout.addWidget(self.lbl_status, stretch=1)

        # Glowing Progress Bar at bottom right
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedSize(360, 6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(
            """
            QProgressBar {
                background-color: #121F33;
                border: none;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00A8FF, stop:1 #00E5FF);
                border-radius: 3px;
            }
            """
        )
        bottom_layout.addWidget(self.progress_bar)

        # Version text at bottom right
        self.lbl_version = QLabel(self._version_text)
        self.lbl_version.setStyleSheet(
            "color: #526784; font-family: 'Segoe UI', sans-serif; font-size: 11px; font-weight: 600;"
        )
        bottom_layout.addWidget(self.lbl_version)

        container_layout.addWidget(self.bottom_bar)
        main_layout.addWidget(self.container)

    def _next_slide(self) -> None:
        """Advance to the next image slide in the carousel."""
        if not self._slide_pixmaps:
            return
        self._current_slide_idx = (self._current_slide_idx + 1) % len(self._slide_pixmaps)
        self._update_slide_display()

    def _update_slide_display(self) -> None:
        """Render the current slide image maintaining aspect ratio."""
        if not self._slide_pixmaps:
            return
        pix = self._slide_pixmaps[self._current_slide_idx]
        scaled = pix.scaled(
            780,
            330,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.lbl_image_banner.setPixmap(scaled)

    def set_progress(self, value: int, status_text: str = "") -> None:
        """
        Update the progress bar value (0 to 100) and status description text.
        Processes Qt GUI events immediately so progress updates instantly.
        """
        self.progress_bar.setValue(max(0, min(100, value)))
        if status_text:
            self.lbl_status.setText(status_text)
        QApplication.processEvents()

    def fade_out(self, duration_ms: int = 400) -> None:
        """Smoothly fade out the splash screen and close."""
        if hasattr(self, "_slide_timer") and self._slide_timer.isActive():
            self._slide_timer.stop()

        anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        anim.setDuration(duration_ms)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.OutQuad)

        def _on_done():
            self.hide()
            self.close()
            self.sig_finished.emit()

        anim.finished.connect(_on_done)
        anim.start()
        # Keep animation handle alive
        self._anim = anim

    def finish(self, main_window: QWidget, duration_ms: int = 300) -> None:
        """Kết thúc màn hình splash và bảo đảm cửa sổ chính bung 100% toàn màn hình."""
        if hasattr(self, "_slide_timer") and self._slide_timer.isActive():
            self._slide_timer.stop()

        anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        anim.setDuration(duration_ms)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.OutQuad)

        def _on_done():
            self.hide()
            self.close()
            if main_window:
                main_window.setWindowState(Qt.WindowState.WindowMaximized)
                main_window.showMaximized()
                main_window.raise_()
                main_window.activateWindow()
            self.sig_finished.emit()

        anim.finished.connect(_on_done)
        anim.start()
        self._anim = anim
