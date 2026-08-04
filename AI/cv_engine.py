"""
cv_engine.py - Subsea CV Engine (Task 1) with YOLOv11 & Fine-Tuning
====================================================================
Quản lý Thị giác Máy tính dưới nước (Subsea Computer Vision):
  - Nhận diện đối tượng: Diver, Pipe, Leak, Fish, ROV, Coral, Debris
  - Kỹ thuật Transfer Learning / Freeze Backbone cho Incremental Learning
  - Phát hiện sự kiện nguy hiểm (Diver proximity, Pipeline Leak) -> Bắn sang Voice Agent
"""

from __future__ import annotations

import os
import time
from typing import Dict, List, Optional, Tuple

import numpy as np

# Import AIVisionProcessor and Detection
from GUI.widgets.ai_vision_processor import AIVisionProcessor, Detection

# Subsea Colors
SUBSEA_CLASS_COLORS: Dict[str, Tuple[int, int, int]] = {
    "diver":         (0, 255, 0),     # Green
    "pipe":          (0, 255, 255),   # Yellow
    "leak":          (0, 0, 255),     # Red (Emergency)
    "fish":          (255, 192, 0),   # Cyan/Gold
    "rov":           (255, 128, 0),   # Orange
    "coral":         (255, 0, 255),   # Magenta
    "sea_structure": (128, 255, 0),   # Bright Lime
    "debris":        (128, 128, 128), # Gray
}


class SubseaCVEngine(AIVisionProcessor):
    """
    Enhanced Computer Vision Engine extending AIVisionProcessor.
    Adds subsea class alerts, event dispatcher, and YOLOv11 fine-tuning pipeline.
    """

    def __init__(
        self,
        model_path: str = "models/underwater_yolov11.pt",
        confidence: float = 0.45,
        parent=None,
    ) -> None:
        super().__init__(model_path=model_path, confidence=confidence, parent=parent)
        self._last_event_time: Dict[str, float] = {}
        self._event_cooldown_s: float = 5.0  # Prevent spamming voice alerts

    def _process_detections(self, detections: List[Detection], frame_w: int, frame_h: int) -> None:
        """Analyze detections for critical subsea events."""
        now = time.time()

        for det in detections:
            cls_name = det.class_name.lower()

            # 1. Pipeline Leak Event Detection
            if cls_name == "leak" and det.confidence >= 0.6:
                if now - self._last_event_time.get("pipeline_leak", 0.0) > self._event_cooldown_s:
                    self._last_event_time["pipeline_leak"] = now
                    self.sig_error.emit(f"⚠️ CV CRITICAL ALERT: Phát hiện RÒ RỈ ĐƯỜNG ỐNG ({det.confidence*100:.1f}%)")

            # 2. Diver Hazard Detection (Diver near center thruster area)
            elif cls_name == "diver":
                # Check if diver bbox intersects center ROV safety zone
                cx = (det.xmin + det.xmax) / 2.0
                cy = (det.ymin + det.ymax) / 2.0
                dist_from_center = np.sqrt(((cx - frame_w/2)/frame_w)**2 + ((cy - frame_h/2)/frame_h)**2)

                if dist_from_center < 0.25 and det.confidence >= 0.5:
                    if now - self._last_event_time.get("diver_danger", 0.0) > self._event_cooldown_s:
                        self._last_event_time["diver_danger"] = now
                        self.sig_error.emit(f"⚠️ CV CRITICAL ALERT: Thợ lặn ở quá gần vùng chân vịt ({det.confidence*100:.1f}%)")


def fine_tune_yolov11(
    data_yaml_path: str,
    base_model_path: str = "yolov8n.pt",
    output_dir: str = "models/fine_tuned",
    epochs: int = 20,
    freeze_backbone_layers: int = 10,
) -> Tuple[bool, str]:
    """
    Fine-tune / Incremental Learning pipeline using Ultralytics YOLOv11.
    Uses Transfer Learning with Freeze Backbone to add new subsea classes quickly.
    """
    try:
        from ultralytics import YOLO

        if not os.path.exists(data_yaml_path):
            return False, f"File dataset config không tồn tại: {data_yaml_path}"

        print(f"[YOLOv11 Fine-Tune] Starting fine-tuning from {base_model_path}...")
        model = YOLO(base_model_path)

        # Freeze backbone layers for transfer learning
        results = model.train(
            data=data_yaml_path,
            epochs=epochs,
            imgsz=640,
            freeze=freeze_backbone_layers,
            project=output_dir,
            name="subsea_yolo11",
            exist_ok=True,
            verbose=True,
        )

        best_weights = os.path.join(output_dir, "subsea_yolo11", "weights", "best.pt")
        if os.path.exists(best_weights):
            return True, f"Fine-tuning thành công! Weights mới: {best_weights}"
        return True, f"Training hoàn tất. Kiểm tra thư mục {output_dir}"

    except Exception as exc:
        return False, f"Lỗi trong quá trình fine-tune YOLOv11: {exc}"
