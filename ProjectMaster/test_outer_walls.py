"""
Test the new exterior-boundary reconstruction using the REAL ProjectMaster
room, door and window detectors.

This file does NOT change the normal API/detection pipeline.

It reuses the existing detection logic exactly as it already exists:

    MMDetection + EasyOCR -> rooms
    YOLO                  -> doors + windows
    keep_only_thick_lines -> wall mask

Then it tests only the new boundary step:

    thick wall mask
        +
    detected door/window gaps
        ↓
    temporary closed wall mask
        ↓
    outside flood fill
        ↓
    building footprint
        ↓
    usable inner boundary

Expected location
-----------------
ProjectMaster/
├── test_outer_walls.py
├── detection_pipeline.py
├── configs/
├── detections/
│   ├── room_detection.py
│   ├── objectDetect.py
│   └── outer_wall_detection.py
└── weights/

Run from the ProjectMaster root:

    python test_outer_walls.py image8.jpg

Optional:

    python test_outer_walls.py image8.jpg \
        --output-dir outer_wall_test \
        --object-conf 0.3 \
        --bridge-search 70
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

from configs.keep_only_thick_lines import (
    keep_only_thick_lines,
)
from configs.mmdet_ImageToJson import (
    CascadeDetector,
)
from detections.room_detection import (
    imageToRooms,
)
from detections.objectDetect import (
    object_detect,
)
from detections.outer_wall_detection import (
    OuterWallDetectionResult,
    OuterWallDetector,
)


# =============================================================
# COLORS
# =============================================================

# OpenCV BGR
BRIDGE_COLOR = (0, 215, 255)           # yellow/orange
STRUCTURAL_COLOR = (0, 210, 0)           # green
OUTER_WALL_COLOR = (0, 140, 255)         # orange
OUTER_BOUNDARY_COLOR = (255, 0, 255)     # magenta
USABLE_BOUNDARY_COLOR = (255, 255, 0)    # cyan
TEXT_COLOR = (25, 25, 25)

BRIDGE_ALPHA = 0.34
STRUCTURAL_ALPHA = 0.26
OUTER_WALL_ALPHA = 0.30


# =============================================================
# ARGUMENTS
# =============================================================

def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description=(
            "Run real room/door/window detection and test "
            "exterior-boundary reconstruction."
        )
    )

    parser.add_argument(
        "image",
        type=Path,
        help="Floor-plan image path.",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "outer_wall_test"
        ),
    )

    parser.add_argument(
        "--detection-conf",
        type=float,
        default=0.4,
        help="MMDetection confidence. Default: 0.4",
    )

    parser.add_argument(
        "--room-conf",
        type=float,
        default=0.4,
        help="Room confidence. Default: 0.4",
    )

    parser.add_argument(
        "--object-conf",
        type=float,
        default=0.3,
        help="YOLO door/window confidence. Default: 0.3",
    )

    parser.add_argument(
        "--residual-close",
        type=int,
        default=7,
        help=(
            "Small closing kernel used only after known "
            "door/window gaps are bridged. Default: 7."
        ),
    )

    parser.add_argument(
        "--wall-depth",
        type=int,
        default=24,
        help=(
            "Maximum inward offset used for the usable "
            "boundary. Default: 24 px."
        ),
    )

    parser.add_argument(
        "--bridge-search",
        type=int,
        default=70,
        help=(
            "How far around a detected door/window to look "
            "for wall support. Default: 70 px."
        ),
    )

    parser.add_argument(
        "--simplify",
        type=float,
        default=2.0,
        help="Boundary simplification epsilon. Default: 2 px.",
    )

    parser.add_argument(
        "--min-building-area",
        type=int,
        default=2000,
        help="Minimum accepted building component area.",
    )

    parser.add_argument(
        "--max-structural-gap-ratio",
        type=float,
        default=0.20,
        help=(
            "Maximum collinear wall gap considered by the structural "
            "fallback, as a fraction of the largest image dimension. "
            "Default: 0.20."
        ),
    )

    parser.add_argument(
        "--min-room-coverage",
        type=float,
        default=0.80,
        help=(
            "Minimum detected-room centroid coverage required before the "
            "result is considered valid. Default: 0.80."
        ),
    )

    return parser.parse_args()


# =============================================================
# IMAGE HELPERS
# =============================================================

def save_image(
    path: Path,
    image: np.ndarray,
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not cv2.imwrite(
        str(path),
        image,
    ):
        raise RuntimeError(
            f"Could not save image: {path}"
        )


def tint_mask(
    image: np.ndarray,
    mask: np.ndarray,
    color: tuple[int, int, int],
    alpha: float,
) -> np.ndarray:

    output = image.copy()

    if (
        mask is None
        or mask.size == 0
        or not np.any(
            mask > 0
        )
    ):
        return output

    selected = (
        mask > 0
    )

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


def polygon_to_cv_points(
    poly,
):

    if (
        poly is None
        or poly.is_empty
    ):
        return None

    coordinates = np.asarray(
        list(
            poly.exterior.coords
        ),
        dtype=np.float64,
    )

    if (
        len(coordinates)
        < 3
    ):
        return None

    return (
        np.rint(
            coordinates
        )
        .astype(
            np.int32
        )
        .reshape(
            (-1, 1, 2)
        )
    )


# =============================================================
# RESULT OVERLAY
# =============================================================

def create_result_overlay(
    original_image: np.ndarray,
    result: OuterWallDetectionResult,
) -> np.ndarray:

    output = original_image.copy()

    # Show only temporary bridge locations lightly.
    output = tint_mask(
        output,
        result.door_window_fill_mask,
        BRIDGE_COLOR,
        BRIDGE_ALPHA,
    )

    # Structural fallback bridges are geometry-only repairs.
    output = tint_mask(
        output,
        result.structural_gap_fill_mask,
        STRUCTURAL_COLOR,
        STRUCTURAL_ALPHA,
    )

    # Show real exterior wall material.
    output = tint_mask(
        output,
        result.outer_wall_mask,
        OUTER_WALL_COLOR,
        OUTER_WALL_ALPHA,
    )

    outer_points = polygon_to_cv_points(
        result.outer_boundary
    )

    if outer_points is not None:

        cv2.polylines(
            output,
            [outer_points],
            True,
            OUTER_BOUNDARY_COLOR,
            4,
            cv2.LINE_AA,
        )

    usable_points = polygon_to_cv_points(
        result.usable_boundary
    )

    if usable_points is not None:

        cv2.polylines(
            output,
            [usable_points],
            True,
            USABLE_BOUNDARY_COLOR,
            3,
            cv2.LINE_AA,
        )

    return add_legend(
        output,
        result,
    )


def add_legend(
    image: np.ndarray,
    result: OuterWallDetectionResult,
) -> np.ndarray:

    output = image.copy()

    lines = [
        (
            "AI door/window bridge (optional hint)",
            BRIDGE_COLOR,
        ),
        (
            "Structural gap repair (no AI required)",
            STRUCTURAL_COLOR,
        ),
        (
            "Real exterior wall",
            OUTER_WALL_COLOR,
        ),
        (
            "Outer boundary",
            OUTER_BOUNDARY_COLOR,
        ),
        (
            "Usable room boundary",
            USABLE_BOUNDARY_COLOR,
        ),
    ]

    x = 20
    y = 30

    width = 455
    line_height = 29

    height = (
        48
        + len(lines)
        * line_height
    )

    overlay = output.copy()

    cv2.rectangle(
        overlay,
        (
            x - 10,
            y - 22,
        ),
        (
            x - 10 + width,
            y - 22 + height,
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

    status = (
        "VALID"
        if result.valid
        else "FAILED"
    )

    cv2.putText(
        output,
        (
            "Boundary detection: "
            f"{status}"
        ),
        (x, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.60,
        TEXT_COLOR,
        2,
        cv2.LINE_AA,
    )

    current_y = (
        y + 32
    )

    for label, color in lines:

        cv2.line(
            output,
            (
                x,
                current_y - 6,
            ),
            (
                x + 35,
                current_y - 6,
            ),
            color,
            5,
            cv2.LINE_AA,
        )

        cv2.putText(
            output,
            label,
            (
                x + 48,
                current_y,
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            TEXT_COLOR,
            1,
            cv2.LINE_AA,
        )

        current_y += (
            line_height
        )

    return output


# =============================================================
# GEOMETRY PRINTING
# =============================================================

def print_polygon_info(
    name: str,
    polygon,
) -> None:

    if (
        polygon is None
        or polygon.is_empty
    ):
        print(
            f"{name}: NOT FOUND"
        )
        return

    (
        min_x,
        min_y,
        max_x,
        max_y,
    ) = polygon.bounds

    print(
        f"{name}:"
        f"\n  area: {polygon.area:.1f} px²"
        f"\n  points: "
        f"{len(polygon.exterior.coords) - 1}"
        f"\n  bounds: "
        f"x={min_x:.1f}..{max_x:.1f}, "
        f"y={min_y:.1f}..{max_y:.1f}"
    )


# =============================================================
# REAL PROJECTMASTER DETECTION
# =============================================================

def run_existing_detection(
    image_path: Path,
    original_image: np.ndarray,
    detection_conf: float,
    room_conf: float,
    object_conf: float,
):
    """
    Reuses the existing ProjectMaster room/door/window detection logic.
    Nothing in those detection algorithms is changed here.
    """

    print(
        "1. Loading existing room detector..."
    )

    cascade_detector = (
        CascadeDetector(
            confidence_threshold=
                detection_conf
        )
    )

    room_detector = (
        imageToRooms(
            detector=
                cascade_detector,
            detection_conf=
                detection_conf,
            room_conf=
                room_conf,
        )
    )

    print(
        "2. Detecting rooms..."
    )

    rooms, annotated_image = (
        room_detector.returnRoom(
            str(image_path)
        )
    )

    rooms = (
        rooms
        or []
    )

    print(
        f"   Rooms kept: {len(rooms)}"
    )

    print(
        "3. Detecting doors and windows..."
    )

    detection_result = (
        object_detect(
            "Door",
            original_image,
            annotated_image,
            object_conf,
            rooms,
            image_path.name,
            True,
        )
        .detect()
    )

    if detection_result is None:

        doors = []
        windows = []

    else:

        (
            doors,
            annotated_image,
            windows,
        ) = detection_result

        doors = (
            doors
            or []
        )

        windows = (
            windows
            or []
        )

    outside_candidates = sum(
        1
        for door in doors
        if getattr(
            door,
            "room2",
            None,
        ) is None
    )

    print(
        f"   Doors kept: {len(doors)}"
    )

    print(
        "   Possible exterior doors "
        f"(room2=None): "
        f"{outside_candidates}"
    )

    print(
        f"   Windows kept: {len(windows)}"
    )

    return (
        rooms,
        doors,
        windows,
        annotated_image,
    )


# =============================================================
# MAIN TEST
# =============================================================

def run_test(
    image_path: Path,
    output_dir: Path,
    detection_conf: float,
    room_conf: float,
    object_conf: float,
    residual_close_px: int,
    wall_depth_px: int,
    bridge_search_px: int,
    simplify_epsilon: float,
    min_building_area: int,
    max_structural_gap_ratio: float,
    min_room_coverage: float,
) -> int:

    image_path = (
        image_path
        .expanduser()
        .resolve()
    )

    output_dir = (
        output_dir
        .expanduser()
        .resolve()
    )

    if not image_path.exists():

        print(
            "ERROR: Image does not exist:"
        )

        print(
            image_path
        )

        return 1

    original_image = cv2.imread(
        str(
            image_path
        )
    )

    if original_image is None:

        print(
            "ERROR: OpenCV could not read:"
        )

        print(
            image_path
        )

        return 1

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        "=" * 72
    )

    print(
        "OUTER-WALL TEST USING REAL DOOR/WINDOW DETECTIONS"
    )

    print(
        "=" * 72
    )

    print(
        f"Input: {image_path}"
    )

    print(
        "Image size: "
        f"{original_image.shape[1]} x "
        f"{original_image.shape[0]} px"
    )

    print(
        f"Output: {output_dir}"
    )

    print()

    save_image(
        output_dir
        / "00_original.png",
        original_image,
    )

    # ---------------------------------------------------------
    # A. Existing detections
    # ---------------------------------------------------------

    (
        rooms,
        doors,
        windows,
        detection_overlay,
    ) = run_existing_detection(
        image_path=
            image_path,
        original_image=
            original_image,
        detection_conf=
            detection_conf,
        room_conf=
            room_conf,
        object_conf=
            object_conf,
    )

    save_image(
        output_dir
        / "01_ai_detections.png",
        detection_overlay,
    )

    # ---------------------------------------------------------
    # B. Existing thick-wall extraction
    # ---------------------------------------------------------

    print(
        "4. Creating thick-wall mask..."
    )

    thick_wall_path = (
        output_dir
        / "02_thick_wall_mask.png"
    )

    thick_wall_mask = (
        keep_only_thick_lines(
            input_path=
                str(
                    image_path
                ),
            output_path=
                str(
                    thick_wall_path
                ),
            threshold_value=120,
            min_thickness=8,
            min_area=500,
            min_length=40,
        )
    )

    if (
        thick_wall_mask is None
        or np.count_nonzero(
            thick_wall_mask
        ) == 0
    ):

        print(
            "ERROR: thick wall mask is empty."
        )

        return 2

    print(
        "   Wall pixels: "
        f"{np.count_nonzero(thick_wall_mask):,}"
    )

    # ---------------------------------------------------------
    # C. New boundary reconstruction
    # ---------------------------------------------------------

    print(
        "5. Filling known door/window gaps and "
        "reconstructing the boundary..."
    )

    detector = (
        OuterWallDetector(
            residual_gap_close_px=
                residual_close_px,
            wall_depth_px=
                wall_depth_px,
            simplify_epsilon=
                simplify_epsilon,
            min_building_area=
                min_building_area,
            bridge_search_px=
                bridge_search_px,
            max_structural_gap_ratio=
                max_structural_gap_ratio,
            min_room_coverage=
                min_room_coverage,
        )
    )

    result = detector.detect(
        thick_wall_mask=
            thick_wall_mask,
        rooms=
            rooms,
        doors=
            doors,
        windows=
            windows,
    )

    print(
        f"   Valid: {result.valid}"
    )

    print(
        f"   Message: {result.message}"
    )

    print(
        "   AI opening hints used: "
        f"{result.bridged_doors} door(s), "
        f"{result.bridged_windows} window(s)"
    )

    print(
        "   Structural fallback gap limit: "
        f"{result.selected_structural_gap_px}px"
    )

    print(
        "   Room coverage: "
        f"{result.room_coverage * 100:.1f}%"
    )

    print(
        "   Boundary wall support: "
        f"{result.boundary_support * 100:.1f}%"
    )

    # ---------------------------------------------------------
    # D. Save debug masks
    # ---------------------------------------------------------

    print(
        "6. Saving debug images..."
    )

    save_image(
        output_dir
        / "03_ai_opening_fill_mask.png",
        result.door_window_fill_mask,
    )

    save_image(
        output_dir
        / "04_structural_gap_fill_mask.png",
        result.structural_gap_fill_mask,
    )

    save_image(
        output_dir
        / "05_closed_wall_mask.png",
        result.closed_wall_mask,
    )

    save_image(
        output_dir
        / "06_outside_mask.png",
        result.outside_mask,
    )

    save_image(
        output_dir
        / "07_building_mask.png",
        result.building_mask,
    )

    save_image(
        output_dir
        / "08_outer_wall_mask.png",
        result.outer_wall_mask,
    )

    save_image(
        output_dir
        / "09_usable_mask.png",
        result.usable_mask,
    )

    result_overlay = (
        create_result_overlay(
            original_image,
            result,
        )
    )

    save_image(
        output_dir
        / "10_outer_wall_result.png",
        result_overlay,
    )

    # ---------------------------------------------------------
    # E. Print geometry
    # ---------------------------------------------------------

    print()

    print(
        "-" * 72
    )

    print(
        "GEOMETRY"
    )

    print(
        "-" * 72
    )

    print_polygon_info(
        "Outer boundary",
        result.outer_boundary,
    )

    print()

    print_polygon_info(
        "Usable boundary",
        result.usable_boundary,
    )

    print()

    print(
        "Building pixels: "
        f"{np.count_nonzero(result.building_mask):,}"
    )

    print(
        "Usable pixels: "
        f"{np.count_nonzero(result.usable_mask):,}"
    )

    print()

    print(
        "-" * 72
    )

    print(
        "IMPORTANT FILES"
    )

    print(
        "-" * 72
    )

    print(
        output_dir
        / "01_ai_detections.png"
    )

    print(
        output_dir
        / "03_ai_opening_fill_mask.png"
    )

    print(
        output_dir
        / "04_structural_gap_fill_mask.png"
    )

    print(
        output_dir
        / "05_closed_wall_mask.png"
    )

    print(
        output_dir
        / "07_building_mask.png"
    )

    print(
        output_dir
        / "10_outer_wall_result.png"
    )

    print()

    if not result.valid:

        print(
            "RESULT: FAILED"
        )

        print(
            "Send me these files:"
        )

        print(
            "  01_ai_detections.png"
        )

        print(
            "  02_thick_wall_mask.png"
        )

        print(
            "  03_ai_opening_fill_mask.png"
        )

        print(
            "  04_structural_gap_fill_mask.png"
        )

        print(
            "  05_closed_wall_mask.png"
        )

        print(
            "  06_outside_mask.png"
        )

        print(
            "  07_building_mask.png"
        )

        return 3

    print(
        "RESULT: SUCCESS"
    )

    print(
        "Open 10_outer_wall_result.png."
    )

    return 0


def main() -> None:

    args = parse_args()

    exit_code = run_test(
        image_path=
            args.image,
        output_dir=
            args.output_dir,
        detection_conf=
            args.detection_conf,
        room_conf=
            args.room_conf,
        object_conf=
            args.object_conf,
        residual_close_px=
            args.residual_close,
        wall_depth_px=
            args.wall_depth,
        bridge_search_px=
            args.bridge_search,
        simplify_epsilon=
            args.simplify,
        min_building_area=
            args.min_building_area,
        max_structural_gap_ratio=
            args.max_structural_gap_ratio,
        min_room_coverage=
            args.min_room_coverage,
    )

    raise SystemExit(
        exit_code
    )


if __name__ == "__main__":
    main()