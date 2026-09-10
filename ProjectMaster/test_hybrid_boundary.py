"""
Test the HYBRID room + wall building-boundary detector (V4 compact output).

IMPORTANT
---------
This test uses:
- Room.roomPoly coordinates
- the thick-wall mask
- existing door detections
- existing window detections

It does NOT use the colored room outlines drawn by room_detection.py as input.
That annotated image is saved only for visual comparison.

Expected files:

ProjectMaster/
├── test_hybrid_boundary.py
└── detections/
    ├── hybrid_boundary_detection.py
    ├── room_boundary_detection.py
    ├── outer_wall_detection.py
    ├── room_detection.py
    └── objectDetect.py

Run:

    python test_hybrid_boundary.py image8.jpg

For corrected user geometry later:

    python test_hybrid_boundary.py image8.jpg --mode user
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

from configs.keep_only_thick_lines import keep_only_thick_lines
from configs.mmdet_ImageToJson import CascadeDetector

from detections.room_detection import imageToRooms
from detections.objectDetect import object_detect

from detections.hybrid_boundary_detection import (
    HybridBoundaryDetector,
    HybridBoundaryDetectionResult,
)


# OpenCV BGR colors used ONLY for debug visualization.
ROOM_COLOR = (255, 90, 90)
OUTER_COLOR = (255, 0, 255)
USABLE_COLOR = (255, 255, 0)
WALL_COLOR = (0, 140, 255)
TEXT_COLOR = (20, 20, 20)


def parse_args():

    parser = argparse.ArgumentParser(
        description=(
            "Test hybrid room + wall building-boundary reconstruction."
        )
    )

    parser.add_argument(
        "image",
        type=Path,
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "hybrid_boundary_test"
        ),
    )

    parser.add_argument(
        "--detection-conf",
        type=float,
        default=0.4,
    )

    parser.add_argument(
        "--room-conf",
        type=float,
        default=0.4,
    )

    parser.add_argument(
        "--object-conf",
        type=float,
        default=0.3,
    )

    parser.add_argument(
        "--mode",
        choices=[
            "ai",
            "user",
        ],
        default="ai",
    )

    return parser.parse_args()


def save_image(
    path: Path,
    image: np.ndarray,
):

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not cv2.imwrite(
        str(path),
        image,
    ):
        raise RuntimeError(
            f"Could not save: {path}"
        )


def polygon_points(
    poly,
):

    if (
        poly is None
        or poly.is_empty
    ):
        return None

    points = np.rint(
        np.asarray(
            poly.exterior.coords,
            dtype=np.float64,
        )
    ).astype(
        np.int32
    )

    if len(points) < 3:
        return None

    return points.reshape(
        (-1, 1, 2)
    )


def draw_room_coordinates(
    original,
    rooms,
    accepted_ids,
    excluded_ids,
):

    output = original.copy()

    accepted = set(
        accepted_ids
    )

    excluded = set(
        excluded_ids
    )

    for room in rooms:

        poly = getattr(
            room,
            "roomPoly",
            None,
        )

        pts = polygon_points(
            poly
        )

        if pts is None:
            continue

        try:
            room_id = int(
                room.id
            )
        except Exception:
            continue

        if room_id in accepted:
            color = ROOM_COLOR
            thickness = 3

        elif room_id in excluded:
            color = (0, 0, 255)
            thickness = 4

        else:
            color = (130, 130, 130)
            thickness = 2

        cv2.polylines(
            output,
            [pts],
            True,
            color,
            thickness,
            cv2.LINE_AA,
        )

        c = poly.centroid

        cv2.putText(
            output,
            f"R{room_id}",
            (
                int(c.x),
                int(c.y),
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            color,
            2,
            cv2.LINE_AA,
        )

    return output


def tint_mask(
    image,
    mask,
    color,
    alpha,
):

    output = image.copy()

    selected = (
        mask > 0
    )

    if not np.any(
        selected
    ):
        return output

    color_image = np.zeros_like(
        output
    )

    color_image[:] = color

    blended = cv2.addWeighted(
        output,
        1.0 - alpha,
        color_image,
        alpha,
        0.0,
    )

    output[
        selected
    ] = blended[
        selected
    ]

    return output


def create_final_overlay(
    original,
    result:
        HybridBoundaryDetectionResult,
):

    output = original.copy()

    output = tint_mask(
        output,
        result.outer_wall_mask,
        WALL_COLOR,
        0.34,
    )

    outer = polygon_points(
        result.outer_boundary
    )

    if outer is not None:
        cv2.polylines(
            output,
            [outer],
            True,
            OUTER_COLOR,
            4,
            cv2.LINE_AA,
        )

    usable = polygon_points(
        result.usable_boundary
    )

    if usable is not None:
        cv2.polylines(
            output,
            [usable],
            True,
            USABLE_COLOR,
            3,
            cv2.LINE_AA,
        )

    lines = [
        f"VALID: {result.valid}",
        f"source: {result.candidate_source}",
        (
            "room area coverage: "
            f"{result.room_area_coverage * 100:.1f}%"
        ),
        (
            "centroid coverage: "
            f"{result.room_centroid_coverage * 100:.1f}%"
        ),
        (
            "wall support: "
            f"{result.wall_support * 100:.1f}%"
        ),
        (
            "structural gap: "
            f"{result.selected_structural_gap_px}px"
        ),
    ]

    overlay = output.copy()

    cv2.rectangle(
        overlay,
        (12, 12),
        (
            520,
            32
            + len(lines) * 27,
        ),
        (255, 255, 255),
        cv2.FILLED,
    )

    output = cv2.addWeighted(
        overlay,
        0.84,
        output,
        0.16,
        0.0,
    )

    y = 35

    for line in lines:
        cv2.putText(
            output,
            line,
            (24, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.52,
            TEXT_COLOR,
            1,
            cv2.LINE_AA,
        )

        y += 27

    return output


def main():

    args = parse_args()

    image_path = (
        args.image
        .expanduser()
        .resolve()
    )

    output_dir = (
        args.output_dir
        .expanduser()
        .resolve()
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    original = cv2.imread(
        str(image_path)
    )

    if original is None:
        raise SystemExit(
            f"Could not read image: {image_path}"
        )

    print(
        "=" * 72
    )

    print(
        "HYBRID ROOM + WALL BOUNDARY TEST"
    )

    print(
        "=" * 72
    )

    print(
        f"Image: {image_path}"
    )

    print(
        f"Mode: {args.mode}"
    )

    print()

    save_image(
        output_dir
        / "00_original.png",
        original,
    )

    # ---------------------------------------------------------
    # 1. Existing room detection
    # ---------------------------------------------------------

    print(
        "1. Running existing room detection..."
    )

    cascade_detector = CascadeDetector(
        confidence_threshold=
            args.detection_conf
    )

    room_detector = imageToRooms(
        detector=
            cascade_detector,
        detection_conf=
            args.detection_conf,
        room_conf=
            args.room_conf,
    )

    (
        rooms,
        model_debug_image,
    ) = room_detector.returnRoom(
        str(image_path)
    )

    rooms = rooms or []

    print(
        f"   Rooms returned: {len(rooms)}"
    )

    # ---------------------------------------------------------
    # 2. Existing door/window detection
    # ---------------------------------------------------------

    print(
        "2. Running existing door/window detection..."
    )

    detection_result = (
        object_detect(
            "Door",
            original,
            model_debug_image.copy(),
            args.object_conf,
            rooms,
            image_path.name,
            True,
        )
        .detect()
    )

    if detection_result is None:
        doors = []
        windows = []
        object_debug = (
            model_debug_image.copy()
        )

    else:
        (
            doors,
            object_debug,
            windows,
        ) = detection_result

        doors = doors or []
        windows = windows or []

    print(
        f"   Doors: {len(doors)}"
    )

    print(
        f"   Windows: {len(windows)}"
    )

    print(
        "   Possible exterior doors: "
        f"{sum(1 for door in doors if getattr(door, 'room2', None) is None)}"
    )

    save_image(
        output_dir
        / "01_detections.png",
        object_debug,
    )

    # ---------------------------------------------------------
    # 3. Existing wall extraction
    # ---------------------------------------------------------

    print(
        "3. Creating thick-wall mask..."
    )

    wall_mask = keep_only_thick_lines(
        input_path=
            str(image_path),
        output_path=
            str(
                output_dir
                / "02_thick_wall_mask.png"
            ),
        threshold_value=120,
        min_thickness=8,
        min_area=500,
        min_length=40,
    )

    # ---------------------------------------------------------
    # 4. Hybrid reconstruction
    # ---------------------------------------------------------

    print(
        "4. Running hybrid boundary detector V6 (selected raw mask is final)..."
    )

    detector = HybridBoundaryDetector()

    result = detector.detect(
        rooms=rooms,
        image_shape=original.shape,
        thick_wall_mask=wall_mask,
        doors=doors,
        windows=windows,
        mode=args.mode,
    )

    print(
        f"   Valid: {result.valid}"
    )

    print(
        f"   Source: {result.candidate_source}"
    )

    print(
        f"   Message: {result.message}"
    )

    # 03 is the FINAL building footprint.
    # result.building_mask is intentionally identical to
    # result.selected_raw_building_mask in V6.
    save_image(
        output_dir
        / "03_FINAL_selected_raw_building_mask.png",
        result.building_mask,
    )

    # The overlay is generated directly from the same final mask.
    final_overlay = create_final_overlay(
        original,
        result,
    )

    save_image(
        output_dir
        / "05_hybrid_boundary_result.png",
        final_overlay,
    )

    print()

    print(
        "METRICS"
    )

    print(
        "-" * 72
    )

    print(
        "Accepted rooms:",
        result.accepted_room_ids,
    )

    print(
        "Excluded rooms:",
        result.excluded_room_ids,
    )

    print(
        "Candidate source:",
        result.candidate_source,
    )

    print(
        "Room area coverage:",
        f"{result.room_area_coverage * 100:.1f}%",
    )

    print(
        "Room centroid coverage:",
        f"{result.room_centroid_coverage * 100:.1f}%",
    )

    print(
        "Wall support:",
        f"{result.wall_support * 100:.1f}%",
    )

    print(
        "Structural gap:",
        f"{result.selected_structural_gap_px}px",
    )

    print(
        "Estimated wall thickness:",
        f"{result.estimated_wall_thickness_px:.1f}px",
    )

    print()

    print(
        "OUTPUT FILES"
    )

    print(
        "  00_original.png"
    )

    print(
        "  01_detections.png"
    )

    print(
        "  02_thick_wall_mask.png"
    )

    print(
        "  03_FINAL_selected_raw_building_mask.png"
    )

    print(
        "  05_hybrid_boundary_result.png"
    )

    # A provisional AI boundary can intentionally have valid=False while
    # still returning outer/usable geometry for visual review.
    if result.outer_boundary is None:
        raise SystemExit(2)


if __name__ == "__main__":
    main()