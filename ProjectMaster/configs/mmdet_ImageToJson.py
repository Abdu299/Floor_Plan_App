"""
Local MMDetection Cascade detector.


It returns the same JSON structure that your client.py already expects:

{
    "type": "floor_plan",
    "confidence": 0.82,
    "detectionResults": {
        "walls": [...],
        "rooms": [...]
    }
}
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import cv2
import numpy as np
import torch
from mmdet.apis import init_detector, inference_detector


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



DEFAULT_CONFIG_PATH = "configs/mmdetection_files/cascade_swin_local.py"
DEFAULT_CHECKPOINT_PATH = "weights/cascade_swin_latest.pth"


DEFAULT_CONFIDENCE_THRESHOLD = 0.40


LABEL_NAMES = {
    0: "wall",
    1: "room",
}


class CascadeDetector:
    """
    Loads the MMDetection Cascade model once, then lets you call predict_json().
    
    """

    def __init__(
        self,
        config_path: str = DEFAULT_CONFIG_PATH,
        checkpoint_path: str = DEFAULT_CHECKPOINT_PATH,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        device: Optional[str] = None,
    ) -> None:
        self.config_path = Path(config_path)
        self.checkpoint_path = Path(checkpoint_path)
        self.confidence_threshold = confidence_threshold
        self.device = device or self._determine_device()
        self.model = self._load_model()

    def _determine_device(self) -> str:
        if torch.cuda.is_available():
            try:
                torch.cuda.init()
                return "cuda:0"
            except Exception as exc:
                logger.warning("CUDA initialization failed: %s. Falling back to CPU.", exc)
        return "cpu"

    def _load_model(self):
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        if not self.checkpoint_path.exists():
            raise FileNotFoundError(f"Checkpoint file not found: {self.checkpoint_path}")

        logger.info("Loading Cascade model on %s", self.device)

        try:
            model = init_detector(
                str(self.config_path),
                str(self.checkpoint_path),
                device=self.device,
            )
            logger.info("Model loaded successfully")
            return model
        except Exception:
            if self.device == "cuda:0":
                logger.exception("Failed to load on CUDA. Trying CPU instead.")
                self.device = "cpu"
                model = init_detector(
                    str(self.config_path),
                    str(self.checkpoint_path),
                    device=self.device,
                )
                logger.info("Model loaded successfully on CPU")
                return model
            raise

    def set_confidence(self, confidence_threshold: float) -> None:
        """Change detection confidence after the model has loaded."""
        self._validate_confidence(confidence_threshold)
        self.confidence_threshold = confidence_threshold

    def predict_json(
        self,
        image_path: str,
        confidence_threshold: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Run detection and return JSON/dict.

        Example:
            detector = CascadeDetector(confidence_threshold=0.4)
            data = detector.predict_json("floorPlan.png")

        You can also override confidence for one call:
            data = detector.predict_json("floorPlan.png", confidence_threshold=0.6)
        """
        threshold = self.confidence_threshold if confidence_threshold is None else confidence_threshold
        self._validate_confidence(threshold)

        image_path_obj = Path(image_path)
        if not image_path_obj.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")

        
        result = inference_detector(self.model, str(image_path_obj))
        return self._result_to_json(result, threshold)

    def _result_to_json(self, result, threshold: float) -> Dict[str, Any]:
        pred_instances = result.pred_instances

        bboxes = pred_instances.bboxes.detach().cpu().numpy()
        labels = pred_instances.labels.detach().cpu().numpy()
        scores = pred_instances.scores.detach().cpu().numpy()

        walls = []
        rooms = []
        kept_scores = []
        counters = {"wall": 0, "room": 0}

        for bbox, label, score in zip(bboxes, labels, scores):
            score_float = float(score)

            if score_float < threshold:
                continue

            label_int = int(label)
            label_name = LABEL_NAMES.get(label_int, f"class_{label_int}")

            x1, y1, x2, y2 = [float(v) for v in bbox]
            kept_scores.append(score_float)

            if label_name not in counters:
                counters[label_name] = 0
            counters[label_name] += 1

            item = {
                "id": f"{label_name}_{counters[label_name]}",
                "position": {
                    "start": {"x": x1, "y": y1},
                    "end": {"x": x2, "y": y2},
                },
                "confidence": score_float,
            }

            if label_name == "wall":
                walls.append(item)
            elif label_name == "room":
                rooms.append(item)

        overall_confidence = float(np.mean(kept_scores)) if kept_scores else 0.0

        return {
            "type": "floor_plan",
            "model": "cascade_rcnn",
            "device": self.device,
            "confidence_threshold": float(threshold),
            "confidence": overall_confidence,
            "detectionResults": {
                "walls": walls,
                "rooms": rooms,
            },
        }

    @staticmethod
    def _validate_confidence(confidence_threshold: float) -> None:
        if not 0 <= confidence_threshold <= 1:
            raise ValueError("confidence_threshold must be between 0 and 1")


if __name__ == "__main__":
    
    import argparse

    parser = argparse.ArgumentParser(description="Run local Cascade MMDetection inference")
    parser.add_argument("image", help="Path to the image")
    parser.add_argument("--conf", type=float, default=DEFAULT_CONFIDENCE_THRESHOLD)
    parser.add_argument("--out", default="cascade_result.json")
    args = parser.parse_args()

    detector = CascadeDetector(confidence_threshold=args.conf)
    data = detector.predict_json(args.image)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(json.dumps(data, indent=2))
    print(f"Saved JSON to {args.out}")
