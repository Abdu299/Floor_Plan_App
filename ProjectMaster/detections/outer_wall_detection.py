from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import cv2
import numpy as np
from shapely.geometry import MultiPolygon, Polygon


@dataclass
class OuterWallDetectionResult:
    """
    Result of exterior-boundary reconstruction.

    All polygons use ORIGINAL IMAGE PIXEL coordinates.

    The detector now uses TWO independent gap-repair mechanisms:

    1. door_window_fill_mask
       Optional hints from detected doors/windows.

    2. structural_gap_fill_mask
       Geometry-only repair of collinear wall gaps. This is the important
       fallback: the boundary can still be reconstructed when a window or
       door detector misses an opening.

    closed_wall_mask contains:
        thick wall mask
        + optional detected-opening bridges
        + structural collinear gap repair
        + a tiny residual raster closing
    """

    outer_boundary: Optional[Polygon]
    usable_boundary: Optional[Polygon]

    door_window_fill_mask: np.ndarray
    structural_gap_fill_mask: np.ndarray
    closed_wall_mask: np.ndarray
    outside_mask: np.ndarray
    building_mask: np.ndarray
    outer_wall_mask: np.ndarray
    usable_mask: np.ndarray

    bridged_doors: int
    bridged_windows: int

    selected_structural_gap_px: int
    room_coverage: float
    boundary_support: float

    valid: bool
    message: str


class OuterWallDetector:
    """
    Reconstruct the exterior building boundary from:

        thick wall mask
        + detected doors
        + detected windows

    Main idea
    ---------
    Doors and windows create intentional gaps in exterior walls. Instead of
    guessing where those gaps are, this detector uses the door/window
    detections that already exist in ProjectMaster.

    For boundary reconstruction only, a thin bridge is drawn through a
    detected door/window when wall material is found on BOTH sides of it.

    The original wall mask and the original door/window detections are NOT
    changed.

    After the temporary bridges are added, the algorithm flood-fills the
    background from outside the image. Anything that the flood-fill cannot
    reach is enclosed by the building shell.

    The hard constraint for optimization will later be:

        room_polygon must be inside usable_boundary
    """

    def __init__(
        self,
        residual_gap_close_px: int = 7,
        wall_depth_px: int = 24,
        simplify_epsilon: float = 2.0,
        min_building_area: int = 2000,
        bridge_search_px: int = 70,
        minimum_bridge_support: int = 3,
        max_structural_gap_ratio: float = 0.20,
        min_room_coverage: float = 0.80,
    ):
        self.residual_gap_close_px = max(
            1,
            int(residual_gap_close_px),
        )

        if self.residual_gap_close_px % 2 == 0:
            self.residual_gap_close_px += 1

        self.wall_depth_px = max(
            1,
            int(wall_depth_px),
        )

        self.simplify_epsilon = max(
            0.0,
            float(simplify_epsilon),
        )

        self.min_building_area = max(
            1,
            int(min_building_area),
        )

        self.bridge_search_px = max(
            8,
            int(bridge_search_px),
        )

        self.minimum_bridge_support = max(
            1,
            int(minimum_bridge_support),
        )

        self.max_structural_gap_ratio = float(
            np.clip(
                max_structural_gap_ratio,
                0.02,
                0.35,
            )
        )

        self.min_room_coverage = float(
            np.clip(
                min_room_coverage,
                0.0,
                1.0,
            )
        )


    # =========================================================
    # PUBLIC API
    # =========================================================

    def detect(
        self,
        thick_wall_mask: np.ndarray,
        rooms: Optional[Iterable[object]] = None,
        doors: Optional[Iterable[object]] = None,
        windows: Optional[Iterable[object]] = None,
    ) -> OuterWallDetectionResult:

        wall_mask = self._normalize_mask(
            thick_wall_mask
        )

        if (
            wall_mask.size == 0
            or np.count_nonzero(wall_mask) == 0
        ):
            return self._empty_result(
                wall_mask,
                "The thick-wall mask is empty.",
            )

        # -----------------------------------------------------
        # 1. Estimate wall thickness
        # -----------------------------------------------------

        estimated_wall_thickness = (
            self._estimate_wall_thickness(
                wall_mask
            )
        )

        bridge_thickness = int(
            np.clip(
                round(
                    estimated_wall_thickness
                ),
                6,
                max(
                    6,
                    self.wall_depth_px,
                ),
            )
        )

        # -----------------------------------------------------
        # 2. OPTIONAL AI opening hints
        # -----------------------------------------------------
        #
        # These are helpful, but they are no longer required.
        # If a window detector misses an opening, the structural
        # repair stage below can still close the wall gap.
        # -----------------------------------------------------

        (
            door_window_fill_mask,
            bridged_doors,
            bridged_windows,
        ) = self._create_door_window_fill_mask(
            wall_mask=wall_mask,
            doors=doors,
            windows=windows,
            bridge_thickness=bridge_thickness,
        )

        base_mask = cv2.bitwise_or(
            wall_mask,
            door_window_fill_mask,
        )

        room_points = self._room_reference_points(
            rooms
        )

        # -----------------------------------------------------
        # 3. STRUCTURAL gap repair
        # -----------------------------------------------------
        #
        # This is the main reliability improvement.
        #
        # We test several increasing maximum gap sizes. For each
        # one, we complete ONLY collinear horizontal/vertical wall
        # segments. Then we flood-fill from outside and score the
        # resulting building.
        #
        # The best candidate is selected using:
        # - how many detected room centroids it contains,
        # - how much of the candidate outer boundary is supported
        #   by the original thick-wall mask,
        # - building area,
        # - and a preference for smaller gap repairs when all else
        #   is effectively equal.
        #
        # Door/window detections are therefore hints, not a single
        # point of failure.
        # -----------------------------------------------------

        (
            structural_gap_fill_mask,
            closed_wall_mask,
            outside_mask,
            building_mask,
            selected_gap_px,
            room_coverage,
            boundary_support,
        ) = self._find_best_structural_reconstruction(
            base_mask=base_mask,
            original_wall_mask=wall_mask,
            room_points=room_points,
            estimated_wall_thickness=
                estimated_wall_thickness,
        )

        building_pixels = int(
            np.count_nonzero(
                building_mask
            )
        )

        if (
            building_pixels
            < self.min_building_area
        ):
            return self._empty_result(
                wall_mask,
                (
                    "No sufficiently large building component could "
                    "be reconstructed from the wall geometry."
                ),
                door_window_fill_mask=
                    door_window_fill_mask,
                structural_gap_fill_mask=
                    structural_gap_fill_mask,
                closed_wall_mask=
                    closed_wall_mask,
                outside_mask=
                    outside_mask,
                bridged_doors=
                    bridged_doors,
                bridged_windows=
                    bridged_windows,
                selected_structural_gap_px=
                    selected_gap_px,
                room_coverage=
                    room_coverage,
                boundary_support=
                    boundary_support,
            )

        # Do not call a result VALID merely because it contains
        # one room. That was the problem in the previous version.
        if (
            room_points
            and room_coverage
                < self.min_room_coverage
        ):
            return self._empty_result(
                wall_mask,
                (
                    "A partial enclosure was found, but it contains "
                    f"only {room_coverage * 100:.1f}% of detected room "
                    "centroids. The exterior shell is probably still open."
                ),
                door_window_fill_mask=
                    door_window_fill_mask,
                structural_gap_fill_mask=
                    structural_gap_fill_mask,
                closed_wall_mask=
                    closed_wall_mask,
                outside_mask=
                    outside_mask,
                building_mask=
                    building_mask,
                bridged_doors=
                    bridged_doors,
                bridged_windows=
                    bridged_windows,
                selected_structural_gap_px=
                    selected_gap_px,
                room_coverage=
                    room_coverage,
                boundary_support=
                    boundary_support,
            )

        # -----------------------------------------------------
        # 4. Create usable INNER boundary
        # -----------------------------------------------------

        inward_offset = int(
            np.clip(
                round(
                    estimated_wall_thickness
                ),
                6,
                max(
                    6,
                    self.wall_depth_px,
                ),
            )
        )

        kernel_size = (
            2 * inward_offset
        ) + 1

        inner_kernel = (
            cv2.getStructuringElement(
                cv2.MORPH_RECT,
                (
                    kernel_size,
                    kernel_size,
                ),
            )
        )

        usable_mask = cv2.erode(
            building_mask,
            inner_kernel,
            iterations=1,
        )

        usable_mask = (
            self._largest_component(
                usable_mask
            )
        )

        if (
            np.count_nonzero(
                usable_mask
            )
            < self.min_building_area
        ):
            return self._empty_result(
                wall_mask,
                (
                    "The building shell was found, but no usable "
                    "interior remained after moving inside the "
                    "exterior-wall thickness."
                ),
                door_window_fill_mask=
                    door_window_fill_mask,
                structural_gap_fill_mask=
                    structural_gap_fill_mask,
                closed_wall_mask=
                    closed_wall_mask,
                outside_mask=
                    outside_mask,
                building_mask=
                    building_mask,
                usable_mask=
                    usable_mask,
                bridged_doors=
                    bridged_doors,
                bridged_windows=
                    bridged_windows,
                selected_structural_gap_px=
                    selected_gap_px,
                room_coverage=
                    room_coverage,
                boundary_support=
                    boundary_support,
            )

        # -----------------------------------------------------
        # 5. Mark REAL exterior wall material
        # -----------------------------------------------------

        boundary_ring = (
            building_mask.copy()
        )

        boundary_ring[
            usable_mask > 0
        ] = 0

        # Only original wall pixels count as "real exterior wall".
        # Temporary bridge pixels are never presented as real walls.
        outer_wall_mask = cv2.bitwise_and(
            wall_mask,
            boundary_ring,
        )

        # -----------------------------------------------------
        # 6. Convert masks to polygons
        # -----------------------------------------------------

        outer_boundary = (
            self._mask_to_polygon(
                building_mask
            )
        )

        usable_boundary = (
            self._mask_to_polygon(
                usable_mask
            )
        )

        if (
            outer_boundary is None
            or outer_boundary.is_empty
        ):
            return self._empty_result(
                wall_mask,
                "Could not convert the detected building to an outer polygon.",
                door_window_fill_mask=
                    door_window_fill_mask,
                structural_gap_fill_mask=
                    structural_gap_fill_mask,
                closed_wall_mask=
                    closed_wall_mask,
                outside_mask=
                    outside_mask,
                building_mask=
                    building_mask,
                outer_wall_mask=
                    outer_wall_mask,
                usable_mask=
                    usable_mask,
                bridged_doors=
                    bridged_doors,
                bridged_windows=
                    bridged_windows,
                selected_structural_gap_px=
                    selected_gap_px,
                room_coverage=
                    room_coverage,
                boundary_support=
                    boundary_support,
            )

        if (
            usable_boundary is None
            or usable_boundary.is_empty
        ):
            return self._empty_result(
                wall_mask,
                "Could not convert the usable interior to a polygon.",
                door_window_fill_mask=
                    door_window_fill_mask,
                structural_gap_fill_mask=
                    structural_gap_fill_mask,
                closed_wall_mask=
                    closed_wall_mask,
                outside_mask=
                    outside_mask,
                building_mask=
                    building_mask,
                outer_wall_mask=
                    outer_wall_mask,
                usable_mask=
                    usable_mask,
                bridged_doors=
                    bridged_doors,
                bridged_windows=
                    bridged_windows,
                selected_structural_gap_px=
                    selected_gap_px,
                room_coverage=
                    room_coverage,
                boundary_support=
                    boundary_support,
            )

        return OuterWallDetectionResult(
            outer_boundary=
                outer_boundary,
            usable_boundary=
                usable_boundary,

            door_window_fill_mask=
                door_window_fill_mask,
            structural_gap_fill_mask=
                structural_gap_fill_mask,
            closed_wall_mask=
                closed_wall_mask,
            outside_mask=
                outside_mask,
            building_mask=
                building_mask,
            outer_wall_mask=
                outer_wall_mask,
            usable_mask=
                usable_mask,

            bridged_doors=
                bridged_doors,
            bridged_windows=
                bridged_windows,

            selected_structural_gap_px=
                selected_gap_px,
            room_coverage=
                room_coverage,
            boundary_support=
                boundary_support,

            valid=True,

            message=(
                "Exterior boundary reconstructed successfully. "
                f"AI hints bridged {bridged_doors} door gap(s) and "
                f"{bridged_windows} window gap(s). "
                f"Structural fallback gap limit: {selected_gap_px}px. "
                f"Room coverage: {room_coverage * 100:.1f}%. "
                f"Boundary wall support: {boundary_support * 100:.1f}%."
            ),
        )

    # =========================================================
    # STRUCTURAL GAP RECONSTRUCTION
    # =========================================================

    def _find_best_structural_reconstruction(
        self,
        base_mask: np.ndarray,
        original_wall_mask: np.ndarray,
        room_points: list[tuple[float, float]],
        estimated_wall_thickness: float,
    ):
        """
        Try multiple gap limits and keep the strongest building candidate.

        This makes missed windows/doors survivable:
        the algorithm can infer a missing opening from two collinear wall
        segments even when no object detector reported that opening.
        """

        candidates = []

        gap_limits = (
            self._structural_gap_candidates(
                base_mask.shape,
                estimated_wall_thickness,
            )
        )

        for gap_px in gap_limits:

            if gap_px <= 0:

                structural_fill = np.zeros_like(
                    base_mask
                )

                candidate_closed = (
                    base_mask.copy()
                )

            else:

                (
                    candidate_closed,
                    structural_fill,
                ) = self._complete_collinear_gaps(
                    base_mask,
                    max_gap_px=
                        gap_px,
                    estimated_wall_thickness=
                        estimated_wall_thickness,
                )

            # Tiny raster cleanup only.
            if (
                self.residual_gap_close_px
                > 1
            ):

                kernel = (
                    cv2.getStructuringElement(
                        cv2.MORPH_RECT,
                        (
                            self.residual_gap_close_px,
                            self.residual_gap_close_px,
                        ),
                    )
                )

                candidate_closed = (
                    cv2.morphologyEx(
                        candidate_closed,
                        cv2.MORPH_CLOSE,
                        kernel,
                    )
                )

            candidate_outside = (
                self._find_outside_space(
                    candidate_closed
                )
            )

            enclosed_mask = np.zeros_like(
                candidate_closed
            )

            enclosed_mask[
                candidate_outside == 0
            ] = 255

            candidate_building = (
                self._select_building_component(
                    enclosed_mask,
                    room_points,
                )
            )

            area = int(
                np.count_nonzero(
                    candidate_building
                )
            )

            if area <= 0:
                continue

            coverage = (
                self._room_coverage(
                    candidate_building,
                    room_points,
                )
            )

            support = (
                self._boundary_support_ratio(
                    candidate_building,
                    original_wall_mask,
                    estimated_wall_thickness,
                )
            )

            image_area = (
                candidate_building.shape[0]
                * candidate_building.shape[1]
            )

            area_ratio = (
                area
                / max(
                    1,
                    image_area,
                )
            )

            # Reject obvious over-closing of the entire canvas.
            if area_ratio > 0.96:
                continue

            candidates.append(
                {
                    "gap_px":
                        int(
                            gap_px
                        ),
                    "structural_fill":
                        structural_fill,
                    "closed":
                        candidate_closed,
                    "outside":
                        candidate_outside,
                    "building":
                        candidate_building,
                    "area":
                        area,
                    "coverage":
                        coverage,
                    "support":
                        support,
                }
            )

        if not candidates:

            empty = np.zeros_like(
                base_mask
            )

            return (
                empty,
                base_mask.copy(),
                self._find_outside_space(
                    base_mask
                ),
                empty,
                0,
                0.0,
                0.0,
            )

        # -----------------------------------------------------
        # Candidate selection
        # -----------------------------------------------------
        #
        # Room coverage is strongest when room detections exist.
        # This prevents a top strip / single room from being called
        # the whole building.
        #
        # If two candidates cover the same rooms, prefer:
        # 1. greater enclosed area,
        # 2. greater original-wall support,
        # 3. smaller repair gap.
        #
        # The large-area tie break is useful when one room detector
        # is an outlier but the full shell can still be reconstructed.
        # -----------------------------------------------------

        if room_points:

            best = max(
                candidates,
                key=lambda item: (
                    round(
                        item[
                            "coverage"
                        ],
                        4,
                    ),
                    item[
                        "area"
                    ],
                    round(
                        item[
                            "support"
                        ],
                        4,
                    ),
                    -item[
                        "gap_px"
                    ],
                ),
            )

        else:

            # With no room detections available, prefer a large enclosed
            # component that is still well supported by original wall pixels.
            # Area must matter strongly here; otherwise a tiny perfectly
            # supported room can beat the full building.
            best = max(
                candidates,
                key=lambda item: (
                    item[
                        "area"
                    ]
                    * (
                        0.50
                        + 0.50
                        * item[
                            "support"
                        ]
                    ),
                    item[
                        "support"
                    ],
                    -item[
                        "gap_px"
                    ],
                ),
            )

        return (
            best[
                "structural_fill"
            ],
            best[
                "closed"
            ],
            best[
                "outside"
            ],
            best[
                "building"
            ],
            int(
                best[
                    "gap_px"
                ]
            ),
            float(
                best[
                    "coverage"
                ]
            ),
            float(
                best[
                    "support"
                ]
            ),
        )

    def _structural_gap_candidates(
        self,
        shape,
        estimated_wall_thickness: float,
    ) -> list[int]:

        height, width = (
            shape[:2]
        )

        largest_dimension = max(
            height,
            width,
        )

        max_gap = max(
            int(
                round(
                    largest_dimension
                    * self.max_structural_gap_ratio
                )
            ),
            int(
                round(
                    estimated_wall_thickness
                    * 5.0
                )
            ),
        )

        raw = [
            0,
            int(
                round(
                    estimated_wall_thickness
                    * 3.0
                )
            ),
            int(
                round(
                    largest_dimension
                    * 0.04
                )
            ),
            int(
                round(
                    largest_dimension
                    * 0.06
                )
            ),
            int(
                round(
                    largest_dimension
                    * 0.08
                )
            ),
            int(
                round(
                    largest_dimension
                    * 0.10
                )
            ),
            int(
                round(
                    largest_dimension
                    * 0.12
                )
            ),
            int(
                round(
                    largest_dimension
                    * 0.15
                )
            ),
            int(
                round(
                    largest_dimension
                    * 0.18
                )
            ),
            max_gap,
        ]

        return sorted(
            {
                int(
                    np.clip(
                        value,
                        0,
                        max_gap,
                    )
                )
                for value in raw
            }
        )

    def _complete_collinear_gaps(
        self,
        mask: np.ndarray,
        max_gap_px: int,
        estimated_wall_thickness: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Complete gaps between collinear wall segments.

        Crucially, this does NOT ask whether the gap was detected as a
        window/door.

        Horizontal gaps are connected only by horizontal support.
        Vertical gaps are connected only by vertical support.

        This is far safer than a large square morphological closing, because
        it does not freely merge nearby walls in every direction.
        """

        source = self._normalize_mask(
            mask
        )

        fill_mask = np.zeros_like(
            source
        )

        if max_gap_px <= 0:
            return (
                source,
                fill_mask,
            )

        alignment_tolerance = max(
            2,
            int(
                round(
                    estimated_wall_thickness
                    * 0.30
                )
            ),
        )

        min_segment_length = max(
            10,
            int(
                round(
                    estimated_wall_thickness
                    * 2.0
                )
            ),
            int(
                round(
                    max_gap_px
                    * 0.18
                )
            ),
        )

        # -----------------------------------------------------
        # Horizontal support
        # -----------------------------------------------------

        horizontal_support = cv2.dilate(
            source,
            cv2.getStructuringElement(
                cv2.MORPH_RECT,
                (
                    1,
                    (
                        2
                        * alignment_tolerance
                    )
                    + 1,
                ),
            ),
            iterations=1,
        )

        height, width = (
            source.shape
        )

        for y in range(
            height
        ):

            runs = (
                self._true_runs(
                    horizontal_support[
                        y
                    ] > 0
                )
            )

            if len(runs) < 2:
                continue

            for (
                left_start,
                left_end,
            ), (
                right_start,
                right_end,
            ) in zip(
                runs,
                runs[
                    1:
                ],
            ):

                gap = (
                    right_start
                    - left_end
                    - 1
                )

                if (
                    gap <= 0
                    or gap > max_gap_px
                ):
                    continue

                left_length = (
                    left_end
                    - left_start
                    + 1
                )

                right_length = (
                    right_end
                    - right_start
                    + 1
                )

                if (
                    left_length
                    < min_segment_length
                    or right_length
                    < min_segment_length
                ):
                    continue

                fill_mask[
                    y,
                    left_end + 1:
                    right_start,
                ] = 255

        # -----------------------------------------------------
        # Vertical support
        # -----------------------------------------------------

        vertical_support = cv2.dilate(
            source,
            cv2.getStructuringElement(
                cv2.MORPH_RECT,
                (
                    (
                        2
                        * alignment_tolerance
                    )
                    + 1,
                    1,
                ),
            ),
            iterations=1,
        )

        for x in range(
            width
        ):

            runs = (
                self._true_runs(
                    vertical_support[
                        :,
                        x
                    ] > 0
                )
            )

            if len(runs) < 2:
                continue

            for (
                top_start,
                top_end,
            ), (
                bottom_start,
                bottom_end,
            ) in zip(
                runs,
                runs[
                    1:
                ],
            ):

                gap = (
                    bottom_start
                    - top_end
                    - 1
                )

                if (
                    gap <= 0
                    or gap > max_gap_px
                ):
                    continue

                top_length = (
                    top_end
                    - top_start
                    + 1
                )

                bottom_length = (
                    bottom_end
                    - bottom_start
                    + 1
                )

                if (
                    top_length
                    < min_segment_length
                    or bottom_length
                    < min_segment_length
                ):
                    continue

                fill_mask[
                    top_end + 1:
                    bottom_start,
                    x,
                ] = 255

        # Keep only newly created geometry in the debug mask.
        fill_mask[
            source > 0
        ] = 0

        closed = cv2.bitwise_or(
            source,
            fill_mask,
        )

        return (
            closed,
            fill_mask,
        )

    @staticmethod
    def _true_runs(
        values: np.ndarray,
    ) -> list[tuple[int, int]]:

        indices = np.flatnonzero(
            values
        )

        if indices.size == 0:
            return []

        split_locations = np.where(
            np.diff(
                indices
            ) > 1
        )[0]

        starts = np.concatenate(
            (
                indices[
                    :1
                ],
                indices[
                    split_locations + 1
                ],
            )
        )

        ends = np.concatenate(
            (
                indices[
                    split_locations
                ],
                indices[
                    -1:
                ],
            )
        )

        return [
            (
                int(
                    start
                ),
                int(
                    end
                ),
            )
            for start, end in zip(
                starts,
                ends,
            )
        ]

    @staticmethod
    def _room_coverage(
        building_mask: np.ndarray,
        room_points: list[tuple[float, float]],
    ) -> float:

        if not room_points:
            return 1.0

        height, width = (
            building_mask.shape
        )

        hits = 0

        for x, y in room_points:

            ix = int(
                round(
                    x
                )
            )

            iy = int(
                round(
                    y
                )
            )

            if (
                0 <= ix < width
                and 0 <= iy < height
                and building_mask[
                    iy,
                    ix
                ] > 0
            ):
                hits += 1

        return (
            hits
            / len(
                room_points
            )
        )

    @staticmethod
    def _boundary_support_ratio(
        building_mask: np.ndarray,
        original_wall_mask: np.ndarray,
        estimated_wall_thickness: float,
    ) -> float:
        """
        How much of the reconstructed outer contour lies near REAL wall pixels.

        This is a sanity signal:
        a boundary invented across a huge unsupported region scores poorly.
        """

        contours, _ = cv2.findContours(
            building_mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_NONE,
        )

        if not contours:
            return 0.0

        contour = max(
            contours,
            key=cv2.contourArea,
        )

        contour_mask = np.zeros_like(
            building_mask
        )

        cv2.drawContours(
            contour_mask,
            [
                contour
            ],
            -1,
            255,
            thickness=1,
        )

        radius = max(
            3,
            int(
                round(
                    estimated_wall_thickness
                    * 1.75
                )
            ),
        )

        kernel_size = (
            2
            * radius
        ) + 1

        supported_region = cv2.dilate(
            original_wall_mask,
            cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE,
                (
                    kernel_size,
                    kernel_size,
                ),
            ),
            iterations=1,
        )

        contour_pixels = (
            contour_mask > 0
        )

        total = int(
            np.count_nonzero(
                contour_pixels
            )
        )

        if total == 0:
            return 0.0

        supported = int(
            np.count_nonzero(
                contour_pixels
                & (
                    supported_region
                    > 0
                )
            )
        )

        return (
            supported
            / total
        )


    # =========================================================
    # DOOR / WINDOW BRIDGING
    # =========================================================

    def _create_door_window_fill_mask(
        self,
        wall_mask: np.ndarray,
        doors: Optional[Iterable[object]],
        windows: Optional[Iterable[object]],
        bridge_thickness: int,
    ) -> tuple[np.ndarray, int, int]:

        fill_mask = np.zeros_like(
            wall_mask
        )

        bridged_doors = 0
        bridged_windows = 0

        for door in doors or []:

            poly = self._get_object_polygon(
                door
            )

            if self._bridge_object_gap(
                wall_mask=wall_mask,
                fill_mask=fill_mask,
                poly=poly,
                bridge_thickness=bridge_thickness,
            ):
                bridged_doors += 1

        for window in windows or []:

            poly = self._get_object_polygon(
                window
            )

            if self._bridge_object_gap(
                wall_mask=wall_mask,
                fill_mask=fill_mask,
                poly=poly,
                bridge_thickness=bridge_thickness,
            ):
                bridged_windows += 1

        return (
            fill_mask,
            bridged_doors,
            bridged_windows,
        )

    @staticmethod
    def _get_object_polygon(
        obj,
    ):

        if obj is None:
            return None

        # Windows in the current ProjectMaster implementation
        # are already Shapely Polygon objects.
        if isinstance(
            obj,
            Polygon,
        ):
            return obj

        possible_attributes = [
            "doorPoly",
            "door_poly",
            "openingPoly",
            "roomPoly",
            "poly",
        ]

        for attribute in possible_attributes:

            poly = getattr(
                obj,
                attribute,
                None,
            )

            if poly is not None:
                return poly

        return None

    def _bridge_object_gap(
        self,
        wall_mask: np.ndarray,
        fill_mask: np.ndarray,
        poly,
        bridge_thickness: int,
    ) -> bool:
        """
        Draw a THIN temporary strip across a detected object.

        We do not fill the full YOLO door bounding box because a door box may
        include the swing arc and extend far into a room.

        Instead:
        1. inspect nearby wall pixels,
        2. determine whether the opening belongs to a horizontal or vertical
           wall,
        3. bridge only between wall material found on opposite sides.

        If wall support is not found on both sides, nothing is invented and
        the object is skipped.
        """

        if (
            poly is None
            or getattr(
                poly,
                "is_empty",
                True,
            )
        ):
            return False

        h, w = wall_mask.shape

        min_x, min_y, max_x, max_y = (
            poly.bounds
        )

        x1 = int(
            np.floor(min_x)
        )
        y1 = int(
            np.floor(min_y)
        )
        x2 = int(
            np.ceil(max_x)
        )
        y2 = int(
            np.ceil(max_y)
        )

        x1 = int(
            np.clip(
                x1,
                0,
                w - 1,
            )
        )
        x2 = int(
            np.clip(
                x2,
                0,
                w - 1,
            )
        )
        y1 = int(
            np.clip(
                y1,
                0,
                h - 1,
            )
        )
        y2 = int(
            np.clip(
                y2,
                0,
                h - 1,
            )
        )

        if (
            x2 <= x1
            or y2 <= y1
        ):
            return False

        object_width = (
            x2 - x1
        )
        object_height = (
            y2 - y1
        )

        search = max(
            self.bridge_search_px,
            bridge_thickness * 3,
            int(
                round(
                    min(
                        max(
                            object_width,
                            object_height,
                        )
                        * 0.45,
                        120,
                    )
                )
            ),
        )

        # A small dilation makes support detection tolerant to
        # one/two-pixel raster differences.
        support_kernel = (
            cv2.getStructuringElement(
                cv2.MORPH_RECT,
                (3, 3),
            )
        )

        support_mask = cv2.dilate(
            wall_mask,
            support_kernel,
            iterations=1,
        )

        horizontal = (
            self._best_horizontal_bridge(
                support_mask,
                x1,
                y1,
                x2,
                y2,
                search,
                bridge_thickness,
            )
        )

        vertical = (
            self._best_vertical_bridge(
                support_mask,
                x1,
                y1,
                x2,
                y2,
                search,
                bridge_thickness,
            )
        )

        # Each result:
        # (score, bridge_start, bridge_end, fixed_coordinate)
        h_score = (
            horizontal[0]
            if horizontal is not None
            else -1
        )

        v_score = (
            vertical[0]
            if vertical is not None
            else -1
        )

        if (
            h_score < 0
            and v_score < 0
        ):
            return False

        half = max(
            2,
            bridge_thickness // 2,
        )

        if h_score >= v_score:

            _, start_x, end_x, y = (
                horizontal
            )

            cv2.rectangle(
                fill_mask,
                (
                    max(
                        0,
                        start_x - 2,
                    ),
                    max(
                        0,
                        y - half,
                    ),
                ),
                (
                    min(
                        w - 1,
                        end_x + 2,
                    ),
                    min(
                        h - 1,
                        y + half,
                    ),
                ),
                255,
                thickness=cv2.FILLED,
            )

            return True

        _, start_y, end_y, x = (
            vertical
        )

        cv2.rectangle(
            fill_mask,
            (
                max(
                    0,
                    x - half,
                ),
                max(
                    0,
                    start_y - 2,
                ),
            ),
            (
                min(
                    w - 1,
                    x + half,
                ),
                min(
                    h - 1,
                    end_y + 2,
                ),
            ),
            255,
            thickness=cv2.FILLED,
        )

        return True

    def _best_horizontal_bridge(
        self,
        wall_mask: np.ndarray,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        search: int,
        bridge_thickness: int,
    ):

        h, w = wall_mask.shape

        y_start = max(
            0,
            y1 - search,
        )

        y_end = min(
            h - 1,
            y2 + search,
        )

        left_start = max(
            0,
            x1 - search,
        )

        left_end = min(
            w - 1,
            x1 + bridge_thickness,
        )

        right_start = max(
            0,
            x2 - bridge_thickness,
        )

        right_end = min(
            w - 1,
            x2 + search,
        )

        if (
            left_end <= left_start
            or right_end <= right_start
        ):
            return None

        band_half = max(
            1,
            bridge_thickness // 4,
        )

        best = None

        for y in range(
            y_start,
            y_end + 1,
        ):

            yy1 = max(
                0,
                y - band_half,
            )

            yy2 = min(
                h,
                y + band_half + 1,
            )

            left_region = wall_mask[
                yy1:yy2,
                left_start:left_end + 1,
            ]

            right_region = wall_mask[
                yy1:yy2,
                right_start:right_end + 1,
            ]

            left_count = int(
                np.count_nonzero(
                    left_region
                )
            )

            right_count = int(
                np.count_nonzero(
                    right_region
                )
            )

            if (
                left_count
                < self.minimum_bridge_support
                or right_count
                < self.minimum_bridge_support
            ):
                continue

            # Require support on BOTH sides.
            score = (
                3
                * min(
                    left_count,
                    right_count,
                )
                + left_count
                + right_count
            )

            if (
                best is not None
                and score <= best[0]
            ):
                continue

            # Find actual wall pixels nearest the opening.
            left_points = np.argwhere(
                left_region > 0
            )

            right_points = np.argwhere(
                right_region > 0
            )

            if (
                left_points.size == 0
                or right_points.size == 0
            ):
                continue

            left_x = int(
                left_start
                + np.max(
                    left_points[:, 1]
                )
            )

            right_x = int(
                right_start
                + np.min(
                    right_points[:, 1]
                )
            )

            if right_x <= left_x:
                continue

            best = (
                score,
                left_x,
                right_x,
                y,
            )

        return best

    def _best_vertical_bridge(
        self,
        wall_mask: np.ndarray,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        search: int,
        bridge_thickness: int,
    ):

        h, w = wall_mask.shape

        x_start = max(
            0,
            x1 - search,
        )

        x_end = min(
            w - 1,
            x2 + search,
        )

        top_start = max(
            0,
            y1 - search,
        )

        top_end = min(
            h - 1,
            y1 + bridge_thickness,
        )

        bottom_start = max(
            0,
            y2 - bridge_thickness,
        )

        bottom_end = min(
            h - 1,
            y2 + search,
        )

        if (
            top_end <= top_start
            or bottom_end <= bottom_start
        ):
            return None

        band_half = max(
            1,
            bridge_thickness // 4,
        )

        best = None

        for x in range(
            x_start,
            x_end + 1,
        ):

            xx1 = max(
                0,
                x - band_half,
            )

            xx2 = min(
                w,
                x + band_half + 1,
            )

            top_region = wall_mask[
                top_start:top_end + 1,
                xx1:xx2,
            ]

            bottom_region = wall_mask[
                bottom_start:bottom_end + 1,
                xx1:xx2,
            ]

            top_count = int(
                np.count_nonzero(
                    top_region
                )
            )

            bottom_count = int(
                np.count_nonzero(
                    bottom_region
                )
            )

            if (
                top_count
                < self.minimum_bridge_support
                or bottom_count
                < self.minimum_bridge_support
            ):
                continue

            score = (
                3
                * min(
                    top_count,
                    bottom_count,
                )
                + top_count
                + bottom_count
            )

            if (
                best is not None
                and score <= best[0]
            ):
                continue

            top_points = np.argwhere(
                top_region > 0
            )

            bottom_points = np.argwhere(
                bottom_region > 0
            )

            if (
                top_points.size == 0
                or bottom_points.size == 0
            ):
                continue

            top_y = int(
                top_start
                + np.max(
                    top_points[:, 0]
                )
            )

            bottom_y = int(
                bottom_start
                + np.min(
                    bottom_points[:, 0]
                )
            )

            if bottom_y <= top_y:
                continue

            best = (
                score,
                top_y,
                bottom_y,
                x,
            )

        return best

    # =========================================================
    # OUTSIDE / BUILDING RECONSTRUCTION
    # =========================================================

    @staticmethod
    def _find_outside_space(
        closed_wall_mask: np.ndarray,
    ) -> np.ndarray:
        """
        Flood-fill free background from a guaranteed outside border.

        White in returned outside_mask means:
            reachable from outside the drawing/building.
        """

        free_space = np.zeros_like(
            closed_wall_mask
        )

        free_space[
            closed_wall_mask == 0
        ] = 255

        # Add a guaranteed free border so seed (0,0) is outside even when
        # the actual drawing touches an image edge.
        padded = cv2.copyMakeBorder(
            free_space,
            1,
            1,
            1,
            1,
            cv2.BORDER_CONSTANT,
            value=255,
        )

        flood = padded.copy()

        flood_mask = np.zeros(
            (
                flood.shape[0] + 2,
                flood.shape[1] + 2,
            ),
            dtype=np.uint8,
        )

        cv2.floodFill(
            flood,
            flood_mask,
            seedPoint=(0, 0),
            newVal=128,
        )

        outside_padded = np.zeros_like(
            flood
        )

        outside_padded[
            flood == 128
        ] = 255

        return outside_padded[
            1:-1,
            1:-1,
        ]

    def _select_building_component(
        self,
        enclosed_mask: np.ndarray,
        room_points: list[tuple[float, float]],
    ) -> np.ndarray:
        """
        Select the enclosed component that best represents the building.

        If room centroids are available:
            choose the component containing the most room centroids.

        Tie-break:
            larger pixel area.

        If no room centroids are available:
            choose the largest enclosed component.
        """

        binary = (
            enclosed_mask > 0
        ).astype(
            np.uint8
        )

        (
            num_labels,
            labels,
            stats,
            _,
        ) = cv2.connectedComponentsWithStats(
            binary,
            connectivity=8,
        )

        if num_labels <= 1:
            return np.zeros_like(
                enclosed_mask
            )

        h, w = enclosed_mask.shape

        best_label = None
        best_hits = -1
        best_area = -1

        for label in range(
            1,
            num_labels,
        ):

            area = int(
                stats[
                    label,
                    cv2.CC_STAT_AREA,
                ]
            )

            if (
                area
                < self.min_building_area
            ):
                continue

            hits = 0

            for x, y in room_points:

                ix = int(
                    round(x)
                )

                iy = int(
                    round(y)
                )

                if (
                    0 <= ix < w
                    and 0 <= iy < h
                    and labels[
                        iy,
                        ix,
                    ] == label
                ):
                    hits += 1

            if (
                hits > best_hits
                or (
                    hits == best_hits
                    and area > best_area
                )
            ):
                best_label = label
                best_hits = hits
                best_area = area

        if best_label is None:
            return np.zeros_like(
                enclosed_mask
            )

        result = np.zeros_like(
            enclosed_mask
        )

        result[
            labels == best_label
        ] = 255

        return result

    # =========================================================
    # ROOM SUPPORT
    # =========================================================

    @staticmethod
    def _room_reference_points(
        rooms: Optional[Iterable[object]],
    ) -> list[tuple[float, float]]:

        points = []

        for room in rooms or []:

            centroid = getattr(
                room,
                "centroid",
                None,
            )

            if centroid is None:

                poly = getattr(
                    room,
                    "roomPoly",
                    None,
                )

                if (
                    poly is not None
                    and not poly.is_empty
                ):
                    c = poly.centroid

                    centroid = (
                        c.x,
                        c.y,
                    )

            if centroid is None:
                continue

            try:
                x = float(
                    centroid[0]
                )

                y = float(
                    centroid[1]
                )

            except (
                TypeError,
                ValueError,
                IndexError,
            ):
                continue

            if (
                np.isfinite(x)
                and np.isfinite(y)
            ):
                points.append(
                    (
                        x,
                        y,
                    )
                )

        return points

    @staticmethod
    def _has_room_support(
        building_mask: np.ndarray,
        room_points: list[tuple[float, float]],
    ) -> bool:

        h, w = building_mask.shape

        for x, y in room_points:

            ix = int(
                round(x)
            )

            iy = int(
                round(y)
            )

            if (
                0 <= ix < w
                and 0 <= iy < h
                and building_mask[
                    iy,
                    ix,
                ] > 0
            ):
                return True

        return False

    # =========================================================
    # GENERAL MASK HELPERS
    # =========================================================

    @staticmethod
    def _normalize_mask(
        mask: np.ndarray,
    ) -> np.ndarray:

        if mask is None:
            raise ValueError(
                "thick_wall_mask cannot be None"
            )

        normalized = mask.copy()

        if normalized.ndim == 3:
            normalized = (
                cv2.cvtColor(
                    normalized,
                    cv2.COLOR_BGR2GRAY,
                )
            )

        if normalized.ndim != 2:
            raise ValueError(
                "thick_wall_mask must be a 2D or 3-channel image"
            )

        _, normalized = cv2.threshold(
            normalized,
            127,
            255,
            cv2.THRESH_BINARY,
        )

        return normalized.astype(
            np.uint8
        )

    @staticmethod
    def _estimate_wall_thickness(
        wall_mask: np.ndarray,
    ) -> float:

        binary = (
            wall_mask > 0
        ).astype(
            np.uint8
        )

        distance = cv2.distanceTransform(
            binary,
            cv2.DIST_L2,
            5,
        )

        values = distance[
            distance > 0
        ]

        if values.size == 0:
            return 8.0

        # 85th percentile avoids using the very thickest wall intersections.
        radius = float(
            np.percentile(
                values,
                85,
            )
        )

        return max(
            2.0,
            radius * 2.0,
        )

    @staticmethod
    def _largest_component(
        mask: np.ndarray,
    ) -> np.ndarray:

        binary = (
            mask > 0
        ).astype(
            np.uint8
        )

        (
            num_labels,
            labels,
            stats,
            _,
        ) = cv2.connectedComponentsWithStats(
            binary,
            connectivity=8,
        )

        if num_labels <= 1:
            return np.zeros_like(
                mask
            )

        best_label = (
            int(
                np.argmax(
                    stats[
                        1:,
                        cv2.CC_STAT_AREA,
                    ]
                )
            )
            + 1
        )

        result = np.zeros_like(
            mask
        )

        result[
            labels == best_label
        ] = 255

        return result

    # =========================================================
    # POLYGON CONVERSION
    # =========================================================

    def _mask_to_polygon(
        self,
        mask: np.ndarray,
    ) -> Optional[Polygon]:

        contours, _ = cv2.findContours(
            mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )

        if not contours:
            return None

        contour = max(
            contours,
            key=cv2.contourArea,
        )

        if (
            cv2.contourArea(
                contour
            )
            <= 0
        ):
            return None

        if (
            self.simplify_epsilon
            > 0
        ):
            contour = cv2.approxPolyDP(
                contour,
                self.simplify_epsilon,
                True,
            )

        points = contour.reshape(
            -1,
            2,
        )

        if len(points) < 3:
            return None

        poly = Polygon(
            [
                (
                    float(x),
                    float(y),
                )
                for x, y in points
            ]
        )

        if not poly.is_valid:
            poly = poly.buffer(
                0
            )

        if poly.is_empty:
            return None

        if isinstance(
            poly,
            MultiPolygon,
        ):
            poly = max(
                poly.geoms,
                key=lambda item:
                    item.area,
            )

        if not isinstance(
            poly,
            Polygon,
        ):
            return None

        return poly

    # =========================================================
    # FAILURE RESULT
    # =========================================================

    @staticmethod
    def _empty_result(
        reference_mask: np.ndarray,
        message: str,
        door_window_fill_mask: Optional[np.ndarray] = None,
        structural_gap_fill_mask: Optional[np.ndarray] = None,
        closed_wall_mask: Optional[np.ndarray] = None,
        outside_mask: Optional[np.ndarray] = None,
        building_mask: Optional[np.ndarray] = None,
        outer_wall_mask: Optional[np.ndarray] = None,
        usable_mask: Optional[np.ndarray] = None,
        bridged_doors: int = 0,
        bridged_windows: int = 0,
        selected_structural_gap_px: int = 0,
        room_coverage: float = 0.0,
        boundary_support: float = 0.0,
    ) -> OuterWallDetectionResult:

        if (
            reference_mask is None
            or reference_mask.size == 0
        ):
            empty = np.zeros(
                (1, 1),
                dtype=np.uint8,
            )
        else:
            empty = np.zeros_like(
                reference_mask,
                dtype=np.uint8,
            )

        def value_or_empty(
            value,
        ):
            return (
                value
                if value is not None
                else empty.copy()
            )

        return OuterWallDetectionResult(
            outer_boundary=None,
            usable_boundary=None,

            door_window_fill_mask=
                value_or_empty(
                    door_window_fill_mask
                ),
            structural_gap_fill_mask=
                value_or_empty(
                    structural_gap_fill_mask
                ),
            closed_wall_mask=
                value_or_empty(
                    closed_wall_mask
                ),
            outside_mask=
                value_or_empty(
                    outside_mask
                ),
            building_mask=
                value_or_empty(
                    building_mask
                ),
            outer_wall_mask=
                value_or_empty(
                    outer_wall_mask
                ),
            usable_mask=
                value_or_empty(
                    usable_mask
                ),

            bridged_doors=
                bridged_doors,
            bridged_windows=
                bridged_windows,

            selected_structural_gap_px=
                int(
                    selected_structural_gap_px
                ),
            room_coverage=
                float(
                    room_coverage
                ),
            boundary_support=
                float(
                    boundary_support
                ),

            valid=False,
            message=message,
        )