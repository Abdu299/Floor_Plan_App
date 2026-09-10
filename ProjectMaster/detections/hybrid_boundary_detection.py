from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import cv2
import numpy as np
from shapely.geometry import MultiPolygon, Polygon

from detections.outer_wall_detection import OuterWallDetector
from detections.room_boundary_detection import RoomBoundaryDetector


@dataclass
class HybridBoundaryDetectionResult:
    """
    Hybrid building-boundary result.

    The hybrid detector combines:

    1. ROOM GEOMETRY
       Room.roomPoly coordinates are used as semantic evidence about where
       the building interior is likely to be.

    2. WALL GEOMETRY
       The thick-wall mask is used to find the actual physical shell.

    3. DOOR/WINDOW OPENING CLOSURE
       Existing detected doors/windows are optional hints that temporarily
       close known gaps in the shell.

    4. STRUCTURAL GAP REPAIR
       Missing door/window detections are handled by the existing structural
       collinear-gap fallback from OuterWallDetector.

    5. FLOOD FILL
       Once a closed shell is found, everything enclosed by that shell becomes
       building interior. Internal fireplaces, stairs, shafts, missing rooms,
       etc. do not become holes in the final building mask.

    Important:
    ----------
    The colored lines drawn by room_detection.py are NEVER used as input.
    Only Room.roomPoly coordinates are used.

    All geometry is in ORIGINAL IMAGE PIXEL coordinates.
    """

    outer_boundary: Optional[Polygon]
    usable_boundary: Optional[Polygon]

    room_mask: np.ndarray
    room_prior_mask: np.ndarray

    global_closed_shell_mask: np.ndarray

    guided_perimeter_band_mask: np.ndarray
    guided_wall_mask: np.ndarray
    guided_closed_shell_mask: np.ndarray

    selected_raw_building_mask: np.ndarray
    building_mask: np.ndarray
    usable_mask: np.ndarray
    outer_wall_mask: np.ndarray

    accepted_room_ids: list[int]
    excluded_room_ids: list[int]

    candidate_source: str

    room_area_coverage: float
    room_centroid_coverage: float
    wall_support: float

    selected_structural_gap_px: int
    estimated_wall_thickness_px: float

    valid: bool
    message: str


class HybridBoundaryDetector:
    """
    Combine the room-based and wall-based approaches.

    The room detector answers:
        "Where is the building likely to be?"

    The wall detector answers:
        "Where is the physical shell?"

    The hybrid detector therefore does NOT trust either one alone.

    Workflow
    --------

        room polygons
            ↓
        room prior / search envelope
            ↓
        candidate exterior-wall band
            ↓
        thick wall pixels near that band
            +
        detected door/window hints
            +
        structural gap repair
            ↓
        closed shell
            ↓
        outside flood fill
            ↓
        solid building interior

    In parallel, a global wall reconstruction is also tested. Several
    candidates are scored against the room polygons and original wall mask.

    mode="ai"
        Raw model detections may contain mistakes. A candidate is allowed to
        exclude a small number of unsupported detections.

    mode="user"
        Corrected room geometry is trusted much more strongly. Nearly all
        corrected room geometry must be covered.
    """

    def __init__(
        self,
        room_detector: Optional[RoomBoundaryDetector] = None,
        max_room_prior_close_fraction: float = 0.12,
        room_prior_steps: int = 4,
        perimeter_band_fraction: float = 0.075,
        min_ai_room_area_coverage: float = 0.58,
        min_user_room_area_coverage: float = 0.985,
        min_ai_centroid_coverage: float = 0.70,
        min_user_centroid_coverage: float = 0.99,
        max_safe_bay_area_ratio: float = 0.06,
        bay_contact_ratio: float = 0.16,
        simplify_epsilon: float = 2.0,
    ):
        self.room_detector = room_detector or RoomBoundaryDetector()

        self.max_room_prior_close_fraction = float(
            np.clip(max_room_prior_close_fraction, 0.03, 0.25)
        )

        self.room_prior_steps = max(2, int(room_prior_steps))

        self.perimeter_band_fraction = float(
            np.clip(perimeter_band_fraction, 0.02, 0.20)
        )

        self.min_ai_room_area_coverage = float(
            np.clip(min_ai_room_area_coverage, 0.0, 1.0)
        )

        self.min_user_room_area_coverage = float(
            np.clip(min_user_room_area_coverage, 0.0, 1.0)
        )

        self.min_ai_centroid_coverage = float(
            np.clip(min_ai_centroid_coverage, 0.0, 1.0)
        )

        self.min_user_centroid_coverage = float(
            np.clip(min_user_centroid_coverage, 0.0, 1.0)
        )

        self.max_safe_bay_area_ratio = float(
            np.clip(max_safe_bay_area_ratio, 0.005, 0.20)
        )

        self.bay_contact_ratio = float(
            np.clip(bay_contact_ratio, 0.02, 0.80)
        )

        self.simplify_epsilon = max(0.0, float(simplify_epsilon))

    # =========================================================
    # PUBLIC API
    # =========================================================

    def detect(
        self,
        rooms: Iterable[object],
        image_shape,
        thick_wall_mask: np.ndarray,
        doors: Optional[Iterable[object]] = None,
        windows: Optional[Iterable[object]] = None,
        mode: str = "ai",
    ) -> HybridBoundaryDetectionResult:

        mode = str(mode).strip().lower()

        if mode not in {"ai", "user"}:
            raise ValueError("mode must be either 'ai' or 'user'")

        height, width = self._shape_hw(image_shape)

        wall_mask = self._normalize_mask(
            thick_wall_mask,
            (height, width),
        )

        empty = np.zeros(
            (height, width),
            dtype=np.uint8,
        )

        if np.count_nonzero(wall_mask) == 0:
            return self._empty_result(
                empty=empty,
                message="The thick-wall mask is empty.",
            )

        # -----------------------------------------------------
        # 1. ROOM-BASED semantic prior
        # -----------------------------------------------------

        room_result = self.room_detector.detect(
            rooms=rooms,
            image_shape=image_shape,
            thick_wall_mask=wall_mask,
            mode=mode,
        )

        if np.count_nonzero(room_result.room_mask) == 0:
            return self._empty_result(
                empty=empty,
                message=(
                    "No valid room polygons were available. "
                    "The hybrid method requires room geometry."
                ),
                accepted_room_ids=room_result.accepted_room_ids,
                excluded_room_ids=room_result.excluded_room_ids,
            )

        room_mask = self._normalize_mask(
            room_result.room_mask,
            (height, width),
        )

        estimated_wall_thickness = max(
            2.0,
            float(room_result.estimated_wall_thickness_px),
        )

        accepted_ids = list(
            room_result.accepted_room_ids
        )

        excluded_ids = list(
            room_result.excluded_room_ids
        )

        accepted_rooms = self._rooms_by_ids(
            rooms,
            accepted_ids,
        )

        room_points = self._room_reference_points(
            accepted_rooms
        )

        # A room prior is deliberately only a rough semantic envelope.
        # It is NOT used directly as the final boundary.
        prior_variants = self._build_room_prior_variants(
            room_mask=room_mask,
            estimated_wall_thickness=estimated_wall_thickness,
        )

        room_prior_mask = prior_variants[-1]

        # -----------------------------------------------------
        # 2. GLOBAL wall reconstruction
        # -----------------------------------------------------
        #
        # This preserves the strong method that already worked well on many
        # plans. It can still win if the room prior happens to be misleading.
        # -----------------------------------------------------

        outer_detector = self._make_outer_detector(
            estimated_wall_thickness=estimated_wall_thickness,
            mode=mode,
        )

        global_result = outer_detector.detect(
            thick_wall_mask=wall_mask,
            rooms=accepted_rooms,
            doors=doors,
            windows=windows,
        )

        candidates = []

        if (
            global_result is not None
            and np.count_nonzero(
                global_result.building_mask
            ) > 0
        ):
            candidates.append(
                self._candidate(
                    source="global-wall",
                    building_mask=
                        global_result.building_mask,
                    closed_shell_mask=
                        global_result.closed_wall_mask,
                    structural_gap_px=
                        global_result.selected_structural_gap_px,
                    room_mask=
                        room_mask,
                    room_points=
                        room_points,
                    room_prior_mask=
                        room_prior_mask,
                    original_wall_mask=
                        wall_mask,
                    estimated_wall_thickness=
                        estimated_wall_thickness,
                )
            )

        # -----------------------------------------------------
        # 3. ROOM-GUIDED wall reconstructions
        # -----------------------------------------------------
        #
        # Instead of allowing structural gap repair to act equally everywhere,
        # we also test wall masks near several room-derived perimeter priors.
        #
        # This helps unusual floor-plan shapes because the room geometry tells
        # us where the exterior shell is likely to be.
        # -----------------------------------------------------

        best_guided_debug = None

        min_dim = min(
            height,
            width,
        )

        base_band_px = max(
            int(
                round(
                    min_dim
                    * self.perimeter_band_fraction
                )
            ),
            int(
                round(
                    estimated_wall_thickness
                    * 5.0
                )
            ),
            30,
        )

        band_values = sorted(
            set(
                [
                    base_band_px,
                    int(
                        round(
                            base_band_px
                            * 1.45
                        )
                    ),
                ]
            )
        )

        for prior_index, prior_mask in enumerate(
            prior_variants
        ):
            for band_px in band_values:

                perimeter_band = self._perimeter_band(
                    prior_mask,
                    band_px,
                )

                guided_wall_mask = cv2.bitwise_and(
                    wall_mask,
                    perimeter_band,
                )

                if (
                    np.count_nonzero(
                        guided_wall_mask
                    )
                    < 100
                ):
                    continue

                guided_detector = self._make_outer_detector(
                    estimated_wall_thickness=
                        estimated_wall_thickness,
                    mode=mode,
                )

                guided_result = guided_detector.detect(
                    thick_wall_mask=
                        guided_wall_mask,
                    rooms=
                        accepted_rooms,
                    doors=
                        doors,
                    windows=
                        windows,
                )

                if (
                    guided_result is None
                    or np.count_nonzero(
                        guided_result.building_mask
                    ) == 0
                ):
                    continue

                candidate = self._candidate(
                    source=(
                        "room-guided-wall"
                        f"-prior{prior_index}"
                        f"-band{band_px}"
                    ),
                    building_mask=
                        guided_result.building_mask,
                    closed_shell_mask=
                        guided_result.closed_wall_mask,
                    structural_gap_px=
                        guided_result.selected_structural_gap_px,
                    room_mask=
                        room_mask,
                    room_points=
                        room_points,
                    room_prior_mask=
                        room_prior_mask,
                    original_wall_mask=
                        wall_mask,
                    estimated_wall_thickness=
                        estimated_wall_thickness,
                )

                candidate[
                    "perimeter_band_mask"
                ] = perimeter_band

                candidate[
                    "guided_wall_mask"
                ] = guided_wall_mask

                candidates.append(
                    candidate
                )

                if (
                    best_guided_debug is None
                    or candidate["score"]
                    > best_guided_debug["score"]
                ):
                    best_guided_debug = (
                        candidate
                    )

        # -----------------------------------------------------
        # 4. Keep ROOM-only reconstruction as DEBUG/FALLBACK EVIDENCE,
        #    but DO NOT let it compete with a physical wall shell.
        # -----------------------------------------------------
        #
        # Why:
        # A detected "room" may actually be a porch, terrace, balcony or
        # another exterior space. If room coverage dominates the score, a
        # room-only polygon can incorrectly pull the building envelope outside
        # the real exterior walls.
        #
        # The room detector is therefore semantic evidence; the FINAL hard
        # boundary must come from a physically closed wall shell whenever one
        # exists.
        # -----------------------------------------------------

        room_fallback_candidate = None

        if (
            room_result is not None
            and np.count_nonzero(
                room_result.building_mask
            ) > 0
        ):
            room_fallback_candidate = self._candidate(
                source="room-fallback",
                building_mask=
                    room_result.building_mask,
                closed_shell_mask=
                    empty,
                structural_gap_px=
                    room_result.selected_bridge_px,
                room_mask=
                    room_mask,
                room_points=
                    room_points,
                room_prior_mask=
                    room_prior_mask,
                original_wall_mask=
                    wall_mask,
                estimated_wall_thickness=
                    estimated_wall_thickness,
                source_penalty=0.0,
            )

        # At this point `candidates` contains ONLY wall-derived candidates:
        # - global wall reconstruction
        # - room-guided wall reconstruction
        #
        # That is intentional.
        candidates = [
            candidate
            for candidate in candidates
            if candidate is not None
        ]

        # -----------------------------------------------------
        # 5. Select a PHYSICALLY PLAUSIBLE wall shell first.
        # -----------------------------------------------------
        #
        # AI mode:
        #   Some room detections may be wrong/outdoor. We therefore allow a
        #   strong wall shell to exclude a minority of room evidence.
        #
        # USER mode:
        #   Corrected room geometry should agree almost completely with the
        #   physical shell.
        # -----------------------------------------------------

        if mode == "user":
            min_candidate_room_area = 0.94
            min_candidate_centroids = 0.95
            min_candidate_wall_support = 0.35
        else:
            min_candidate_room_area = 0.55
            min_candidate_centroids = 0.60
            min_candidate_wall_support = 0.50

        viable_candidates = [
            candidate
            for candidate in candidates
            if (
                candidate["room_area_coverage"]
                >= min_candidate_room_area
                and candidate["centroid_coverage"]
                >= min_candidate_centroids
                and candidate["wall_support"]
                >= min_candidate_wall_support
            )
        ]

        if viable_candidates:
            best = max(
                viable_candidates,
                key=lambda item:
                    item["score"],
            )

        elif candidates:
            # We still expose the best physical attempt for debugging, but it
            # will later fail the normal validity checks instead of silently
            # falling back to a geometrically misleading room-only boundary.
            best = max(
                candidates,
                key=lambda item:
                    item["score"],
            )

        elif room_fallback_candidate is not None:
            # A room-only result is useful as a diagnostic preview, but it is
            # not trustworthy enough to become the optimizer's hard building
            # boundary. Return it as INVALID so the user can correct detections
            # and recalculate.
            best = room_fallback_candidate

        else:
            return self._empty_result(
                empty=empty,
                message=(
                    "No wall-derived or room-derived boundary candidate "
                    "could be reconstructed."
                ),
                room_mask=room_mask,
                room_prior_mask=room_prior_mask,
                global_closed_shell_mask=(
                    global_result.closed_wall_mask
                    if global_result is not None
                    else empty
                ),
                accepted_room_ids=accepted_ids,
                excluded_room_ids=excluded_ids,
                estimated_wall_thickness_px=
                    estimated_wall_thickness,
            )

        raw_building = best[
            "building_mask"
        ].copy()

        # -----------------------------------------------------
        # 6. SELECTED RAW BUILDING MASK IS THE FINAL FOOTPRINT
        # -----------------------------------------------------
        #
        # Once the best candidate has been selected, do not modify its
        # geometry anymore.
        #
        # Previous versions applied extra room-prior and hole-filling
        # operations here. On some floor plans those steps enlarged an
        # already-correct physical footprint because outdoor detected regions
        # such as porches could influence the room prior.
        #
        # From this version onward:
        #
        #     selected_raw_building_mask == final building_mask
        #
        # The outer boundary, usable boundary, and final overlay are all
        # derived directly from this selected raw mask.
        # -----------------------------------------------------

        building_mask = raw_building.copy()

        if (
            np.count_nonzero(
                building_mask
            ) == 0
        ):
            return self._empty_result(
                empty=empty,
                message=(
                    "The selected hybrid candidate became empty during "
                    "solid-interior reconstruction."
                ),
                room_mask=room_mask,
                room_prior_mask=room_prior_mask,
                selected_raw_building_mask=raw_building,
                accepted_room_ids=accepted_ids,
                excluded_room_ids=excluded_ids,
                candidate_source=best["source"],
                estimated_wall_thickness_px=
                    estimated_wall_thickness,
            )

        # -----------------------------------------------------
        # 7. Final metrics
        # -----------------------------------------------------

        room_area_coverage = self._mask_overlap_ratio(
            room_mask,
            building_mask,
        )

        room_centroid_coverage = (
            self._point_coverage(
                building_mask,
                room_points,
            )
        )

        wall_support = self._boundary_wall_support(
            building_mask,
            wall_mask,
            estimated_wall_thickness,
        )

        if mode == "user":
            min_area_coverage = (
                self.min_user_room_area_coverage
            )
            min_centroid_coverage = (
                self.min_user_centroid_coverage
            )
        else:
            min_area_coverage = (
                self.min_ai_room_area_coverage
            )
            min_centroid_coverage = (
                self.min_ai_centroid_coverage
            )

        # IMPORTANT:
        # A room-fallback result may still contain a geometrically useful
        # building footprint. Do NOT return an empty result here.
        #
        # We continue and derive outer_boundary + usable_boundary from the
        # final building mask so the frontend/test overlay can display it.
        #
        # In AI mode it remains PROVISIONAL (valid=False) because no strong
        # physical wall shell was found. In user mode, corrected room geometry
        # can be trusted and may be accepted as valid.
        fallback_only = best["source"] == "room-fallback"

        if (
            room_area_coverage
            < min_area_coverage
            or room_centroid_coverage
            < min_centroid_coverage
        ):
            return self._empty_result(
                empty=empty,
                message=(
                    "A hybrid boundary was reconstructed, but it does not "
                    "cover enough room evidence. "
                    f"Room area coverage={room_area_coverage * 100:.1f}%, "
                    f"centroid coverage={room_centroid_coverage * 100:.1f}%."
                ),
                room_mask=room_mask,
                room_prior_mask=room_prior_mask,
                global_closed_shell_mask=(
                    global_result.closed_wall_mask
                    if global_result is not None
                    else empty
                ),
                guided_perimeter_band_mask=(
                    best.get(
                        "perimeter_band_mask",
                        empty,
                    )
                ),
                guided_wall_mask=(
                    best.get(
                        "guided_wall_mask",
                        empty,
                    )
                ),
                guided_closed_shell_mask=(
                    best.get(
                        "closed_shell_mask",
                        empty,
                    )
                ),
                selected_raw_building_mask=raw_building,
                building_mask=building_mask,
                accepted_room_ids=accepted_ids,
                excluded_room_ids=excluded_ids,
                candidate_source=best["source"],
                room_area_coverage=room_area_coverage,
                room_centroid_coverage=
                    room_centroid_coverage,
                wall_support=wall_support,
                selected_structural_gap_px=
                    best["structural_gap_px"],
                estimated_wall_thickness_px=
                    estimated_wall_thickness,
            )

        # -----------------------------------------------------
        # 8. Outer and usable boundaries
        # -----------------------------------------------------

        outer_boundary = self._mask_to_polygon(
            building_mask
        )

        if outer_boundary is None:
            return self._empty_result(
                empty=empty,
                message=(
                    "Could not convert the final hybrid building mask "
                    "to an outer polygon."
                ),
                room_mask=room_mask,
                room_prior_mask=room_prior_mask,
                selected_raw_building_mask=raw_building,
                building_mask=building_mask,
                accepted_room_ids=accepted_ids,
                excluded_room_ids=excluded_ids,
                candidate_source=best["source"],
                room_area_coverage=room_area_coverage,
                room_centroid_coverage=
                    room_centroid_coverage,
                wall_support=wall_support,
                selected_structural_gap_px=
                    best["structural_gap_px"],
                estimated_wall_thickness_px=
                    estimated_wall_thickness,
            )

        usable_mask = self._make_usable_mask(
            building_mask,
            estimated_wall_thickness,
        )

        usable_boundary = self._mask_to_polygon(
            usable_mask
        )

        if usable_boundary is None:
            # Preserve a valid outer result. This should be rare.
            usable_mask = building_mask.copy()
            usable_boundary = outer_boundary

        outer_wall_mask = self._extract_outer_wall_pixels(
            building_mask=building_mask,
            wall_mask=wall_mask,
            estimated_wall_thickness=
                estimated_wall_thickness,
        )

        guided_band = best.get(
            "perimeter_band_mask",
            empty,
        )

        guided_wall = best.get(
            "guided_wall_mask",
            empty,
        )

        guided_closed = best.get(
            "closed_shell_mask",
            empty,
        )

        if fallback_only and mode == "ai":
            final_valid = False
            message = (
                "A provisional room-derived boundary was reconstructed. "
                "The selected raw building mask is used unchanged as the final footprint. "
                "No sufficiently strong physical wall shell was found, but "
                "outerBoundary and usableBoundary are still returned for "
                "visual review/correction. "
                f"Source={best['source']}. "
                f"Room area coverage={room_area_coverage * 100:.1f}%. "
                f"Room centroid coverage={room_centroid_coverage * 100:.1f}%."
            )
        else:
            final_valid = True
            message = (
                "Hybrid boundary reconstructed successfully. "
                "The selected raw building mask is used unchanged as the final footprint. "
                f"Source={best['source']}. "
                f"Mode={mode}. "
                f"Room area coverage={room_area_coverage * 100:.1f}%. "
                f"Room centroid coverage={room_centroid_coverage * 100:.1f}%. "
                f"Original-wall support={wall_support * 100:.1f}%. "
                f"Structural gap={best['structural_gap_px']}px. "
                f"Estimated wall thickness="
                f"{estimated_wall_thickness:.1f}px."
            )

        return HybridBoundaryDetectionResult(
            outer_boundary=outer_boundary,
            usable_boundary=usable_boundary,

            room_mask=room_mask,
            room_prior_mask=room_prior_mask,

            global_closed_shell_mask=(
                global_result.closed_wall_mask
                if global_result is not None
                else empty.copy()
            ),

            guided_perimeter_band_mask=
                guided_band,
            guided_wall_mask=
                guided_wall,
            guided_closed_shell_mask=
                guided_closed,

            selected_raw_building_mask=
                raw_building,
            building_mask=
                building_mask,
            usable_mask=
                usable_mask,
            outer_wall_mask=
                outer_wall_mask,

            accepted_room_ids=
                accepted_ids,
            excluded_room_ids=
                excluded_ids,

            candidate_source=
                best["source"],

            room_area_coverage=
                room_area_coverage,
            room_centroid_coverage=
                room_centroid_coverage,
            wall_support=
                wall_support,

            selected_structural_gap_px=
                int(
                    best[
                        "structural_gap_px"
                    ]
                ),
            estimated_wall_thickness_px=
                estimated_wall_thickness,

            valid=final_valid,
            message=message,
        )

    # =========================================================
    # OUTER DETECTOR FACTORY
    # =========================================================

    @staticmethod
    def _make_outer_detector(
        estimated_wall_thickness: float,
        mode: str,
    ) -> OuterWallDetector:

        # AI mode must tolerate a wrong porch / isolated false room.
        min_room_coverage = (
            0.68
            if mode == "ai"
            else 0.98
        )

        return OuterWallDetector(
            residual_gap_close_px=5,
            wall_depth_px=max(
                18,
                int(
                    round(
                        estimated_wall_thickness
                        * 1.7
                    )
                ),
            ),
            simplify_epsilon=2.0,
            min_building_area=2000,
            bridge_search_px=max(
                60,
                int(
                    round(
                        estimated_wall_thickness
                        * 5.0
                    )
                ),
            ),
            minimum_bridge_support=3,
            max_structural_gap_ratio=0.24,
            min_room_coverage=min_room_coverage,
        )

    # =========================================================
    # ROOM PRIOR
    # =========================================================

    def _build_room_prior_variants(
        self,
        room_mask: np.ndarray,
        estimated_wall_thickness: float,
    ) -> list[np.ndarray]:

        height, width = room_mask.shape
        min_dim = min(height, width)

        minimum = max(
            9,
            int(
                round(
                    estimated_wall_thickness
                    * 1.5
                )
            ),
        )

        maximum = max(
            minimum,
            int(
                round(
                    min_dim
                    * self.max_room_prior_close_fraction
                )
            ),
        )

        values = np.linspace(
            minimum,
            maximum,
            num=self.room_prior_steps,
        )

        kernels = sorted(
            set(
                max(
                    3,
                    int(round(value))
                )
                for value in values
            )
        )

        variants = []

        for kernel_px in kernels:

            if kernel_px % 2 == 0:
                kernel_px += 1

            kernel = cv2.getStructuringElement(
                cv2.MORPH_RECT,
                (
                    kernel_px,
                    kernel_px,
                ),
            )

            prior = cv2.morphologyEx(
                room_mask,
                cv2.MORPH_CLOSE,
                kernel,
            )

            # Connect very small separation between room polygons and the wall.
            small_dilate_px = max(
                1,
                int(
                    round(
                        estimated_wall_thickness
                        * 0.35
                    )
                ),
            )

            if small_dilate_px > 1:
                d_kernel = cv2.getStructuringElement(
                    cv2.MORPH_RECT,
                    (
                        small_dilate_px,
                        small_dilate_px,
                    ),
                )

                prior = cv2.dilate(
                    prior,
                    d_kernel,
                    iterations=1,
                )

            prior = self._fill_enclosed_holes(
                prior
            )

            variants.append(
                prior
            )

        # Always keep the room detector's raw geometry represented.
        if not variants:
            variants = [
                room_mask.copy()
            ]

        return variants

    @staticmethod
    def _perimeter_band(
        mask: np.ndarray,
        distance_px: int,
    ) -> np.ndarray:

        distance_px = max(
            2,
            int(distance_px),
        )

        kernel_size = (
            2 * distance_px
        ) + 1

        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (
                kernel_size,
                kernel_size,
            ),
        )

        outer = cv2.dilate(
            mask,
            kernel,
            iterations=1,
        )

        inner = cv2.erode(
            mask,
            kernel,
            iterations=1,
        )

        return cv2.subtract(
            outer,
            inner,
        )

    # =========================================================
    # CANDIDATE SCORING
    # =========================================================

    def _candidate(
        self,
        source: str,
        building_mask: np.ndarray,
        closed_shell_mask: np.ndarray,
        structural_gap_px: int,
        room_mask: np.ndarray,
        room_points: list[tuple[float, float]],
        room_prior_mask: np.ndarray,
        original_wall_mask: np.ndarray,
        estimated_wall_thickness: float,
        source_penalty: float = 0.0,
    ):

        building = self._normalize_mask(
            building_mask,
            room_mask.shape,
        )

        area = int(
            np.count_nonzero(
                building
            )
        )

        if area <= 0:
            return None

        image_area = (
            building.shape[0]
            * building.shape[1]
        )

        area_ratio = (
            area
            / max(
                1,
                image_area,
            )
        )

        if area_ratio > 0.97:
            return None

        room_area_coverage = (
            self._mask_overlap_ratio(
                room_mask,
                building,
            )
        )

        centroid_coverage = (
            self._point_coverage(
                building,
                room_points,
            )
        )

        prior_coverage = (
            self._mask_overlap_ratio(
                room_prior_mask,
                building,
            )
        )

        wall_support = (
            self._boundary_wall_support(
                building,
                original_wall_mask,
                estimated_wall_thickness,
            )
        )

        room_area = max(
            1,
            int(
                np.count_nonzero(
                    room_mask
                )
            ),
        )

        expansion_ratio = (
            area
            / room_area
        )

        # A final building boundary is a PHYSICAL envelope.
        #
        # Room geometry is semantic evidence that tells us where the building
        # probably is, but raw room coverage must not beat a strong closed wall
        # shell. This matters when the model detects an outdoor porch/terrace
        # as a room.
        #
        # Therefore physical wall support now has the largest weight.
        score = (
            wall_support
            * 500.0
            + centroid_coverage
            * 260.0
            + room_area_coverage
            * 220.0
            + prior_coverage
            * 35.0
        )

        # Penalize huge unsupported growth beyond detected room geometry.
        if expansion_ratio > 2.2:
            score -= (
                expansion_ratio
                - 2.2
            ) * 65.0

        # A tiny preference for smaller structural repairs.
        score -= (
            max(
                0,
                int(
                    structural_gap_px
                ),
            )
            * 0.025
        )

        score -= float(
            source_penalty
        )

        return {
            "source": source,
            "building_mask": building,
            "closed_shell_mask": (
                self._normalize_mask(
                    closed_shell_mask,
                    building.shape,
                )
                if closed_shell_mask is not None
                else np.zeros_like(
                    building
                )
            ),
            "structural_gap_px": int(
                structural_gap_px
                or 0
            ),
            "room_area_coverage":
                room_area_coverage,
            "centroid_coverage":
                centroid_coverage,
            "prior_coverage":
                prior_coverage,
            "wall_support":
                wall_support,
            "expansion_ratio":
                expansion_ratio,
            "score":
                float(score),
        }

    # =========================================================
    # SOLID INTERIOR
    # =========================================================

    def _fill_room_supported_bays(
        self,
        building_mask: np.ndarray,
        room_prior_mask: np.ndarray,
        estimated_wall_thickness: float,
    ) -> np.ndarray:
        """
        Fill small room-supported bays that a wrong partial shell may have
        classified as outside.

        This is specifically useful for internal structures such as:
        - fireplace/stair blocks,
        - missing hallway detections,
        - shafts,
        - small room-detection gaps.

        Large appendages are NOT absorbed automatically. This is intentional:
        a porch detected as a room should not redefine the exterior shell just
        because it is large.
        """

        building = building_mask.copy()

        missing = cv2.bitwise_and(
            room_prior_mask,
            cv2.bitwise_not(
                building
            ),
        )

        binary = (
            missing > 0
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

        building_area = max(
            1,
            int(
                np.count_nonzero(
                    building
                )
            ),
        )

        max_area = max(
            500,
            int(
                round(
                    building_area
                    * self.max_safe_bay_area_ratio
                )
            ),
        )

        contact_px = max(
            5,
            int(
                round(
                    estimated_wall_thickness
                    * 1.5
                )
            ),
        )

        contact_kernel = (
            cv2.getStructuringElement(
                cv2.MORPH_RECT,
                (
                    2 * contact_px + 1,
                    2 * contact_px + 1,
                ),
            )
        )

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
                area <= 0
                or area > max_area
            ):
                continue

            component = np.zeros_like(
                building
            )

            component[
                labels == label
            ] = 255

            expanded = cv2.dilate(
                component,
                contact_kernel,
                iterations=1,
            )

            ring = cv2.bitwise_and(
                expanded,
                cv2.bitwise_not(
                    component
                ),
            )

            ring_pixels = int(
                np.count_nonzero(
                    ring
                )
            )

            if ring_pixels == 0:
                continue

            contact = cv2.bitwise_and(
                ring,
                building,
            )

            contact_ratio = (
                np.count_nonzero(
                    contact
                )
                / ring_pixels
            )

            if (
                contact_ratio
                < self.bay_contact_ratio
            ):
                continue

            building[
                component > 0
            ] = 255

        return building

    @staticmethod
    def _fill_enclosed_holes(
        mask: np.ndarray,
    ) -> np.ndarray:
        """
        Make every region inside the selected OUTER contour solid.

        This intentionally removes black holes caused by internal walls,
        fireplaces, stair cores, missing room detections, etc.

        For the current project model, the building boundary represents one
        solid usable footprint. Courtyard semantics can be added later as an
        explicit separate feature if needed.
        """

        normalized = (
            mask > 0
        ).astype(
            np.uint8
        ) * 255

        contours, _ = cv2.findContours(
            normalized,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )

        if not contours:
            return normalized

        result = np.zeros_like(
            normalized
        )

        cv2.drawContours(
            result,
            contours,
            -1,
            255,
            cv2.FILLED,
        )

        return result

    # =========================================================
    # FINAL GEOMETRY
    # =========================================================

    @staticmethod
    def _make_usable_mask(
        building_mask: np.ndarray,
        estimated_wall_thickness: float,
    ) -> np.ndarray:

        inward = max(
            3,
            int(
                round(
                    estimated_wall_thickness
                    * 0.65
                )
            ),
        )

        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (
                2 * inward + 1,
                2 * inward + 1,
            ),
        )

        usable = cv2.erode(
            building_mask,
            kernel,
            iterations=1,
        )

        if (
            np.count_nonzero(
                usable
            ) == 0
        ):
            return building_mask.copy()

        return usable

    @staticmethod
    def _extract_outer_wall_pixels(
        building_mask: np.ndarray,
        wall_mask: np.ndarray,
        estimated_wall_thickness: float,
    ) -> np.ndarray:

        distance = max(
            5,
            int(
                round(
                    estimated_wall_thickness
                    * 2.0
                )
            ),
        )

        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (
                2 * distance + 1,
                2 * distance + 1,
            ),
        )

        eroded = cv2.erode(
            building_mask,
            kernel,
            iterations=1,
        )

        boundary_ring = cv2.subtract(
            building_mask,
            eroded,
        )

        return cv2.bitwise_and(
            wall_mask,
            boundary_ring,
        )

    def _boundary_wall_support(
        self,
        building_mask: np.ndarray,
        wall_mask: np.ndarray,
        estimated_wall_thickness: float,
    ) -> float:

        contour_mask = np.zeros_like(
            building_mask
        )

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

        cv2.drawContours(
            contour_mask,
            [contour],
            -1,
            255,
            1,
        )

        search_px = max(
            5,
            int(
                round(
                    estimated_wall_thickness
                    * 2.2
                )
            ),
        )

        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (
                2 * search_px + 1,
                2 * search_px + 1,
            ),
        )

        wall_neighbourhood = cv2.dilate(
            wall_mask,
            kernel,
            iterations=1,
        )

        contour_pixels = int(
            np.count_nonzero(
                contour_mask
            )
        )

        if contour_pixels == 0:
            return 0.0

        supported = cv2.bitwise_and(
            contour_mask,
            wall_neighbourhood,
        )

        return float(
            np.count_nonzero(
                supported
            )
            / contour_pixels
        )

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

        if cv2.contourArea(contour) <= 0:
            return None

        if self.simplify_epsilon > 0:
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
            poly = poly.buffer(0)

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
    # ROOM HELPERS
    # =========================================================

    @staticmethod
    def _rooms_by_ids(
        rooms,
        accepted_ids,
    ) -> list[object]:

        accepted_set = set(
            int(value)
            for value in accepted_ids
        )

        result = []

        for room in rooms or []:
            try:
                room_id = int(
                    getattr(
                        room,
                        "id",
                    )
                )
            except (
                TypeError,
                ValueError,
                AttributeError,
            ):
                continue

            if room_id in accepted_set:
                result.append(
                    room
                )

        return result

    @staticmethod
    def _room_reference_points(
        rooms,
    ) -> list[tuple[float, float]]:

        points = []

        for room in rooms or []:

            poly = getattr(
                room,
                "roomPoly",
                None,
            )

            if (
                poly is None
                or getattr(
                    poly,
                    "is_empty",
                    True,
                )
            ):
                continue

            c = poly.centroid

            points.append(
                (
                    float(c.x),
                    float(c.y),
                )
            )

        return points

    @staticmethod
    def _point_coverage(
        mask: np.ndarray,
        points,
    ) -> float:

        if not points:
            return 1.0

        height, width = mask.shape

        hits = 0

        for x, y in points:

            ix = int(
                round(x)
            )

            iy = int(
                round(y)
            )

            if (
                0 <= ix < width
                and 0 <= iy < height
                and mask[
                    iy,
                    ix,
                ] > 0
            ):
                hits += 1

        return float(
            hits
            / len(points)
        )

    @staticmethod
    def _mask_overlap_ratio(
        evidence_mask: np.ndarray,
        container_mask: np.ndarray,
    ) -> float:

        evidence = (
            evidence_mask > 0
        )

        evidence_count = int(
            np.count_nonzero(
                evidence
            )
        )

        if evidence_count == 0:
            return 1.0

        inside = np.logical_and(
            evidence,
            container_mask > 0,
        )

        return float(
            np.count_nonzero(
                inside
            )
            / evidence_count
        )

    @staticmethod
    def _component_covering_most_rooms(
        mask: np.ndarray,
        room_points,
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

        height, width = mask.shape

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

            hits = 0

            for x, y in room_points:

                ix = int(
                    round(x)
                )

                iy = int(
                    round(y)
                )

                if (
                    0 <= ix < width
                    and 0 <= iy < height
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
                mask
            )

        result = np.zeros_like(
            mask
        )

        result[
            labels == best_label
        ] = 255

        return result

    # =========================================================
    # MASK HELPERS
    # =========================================================

    @staticmethod
    def _shape_hw(
        image_shape,
    ) -> tuple[int, int]:

        if len(image_shape) < 2:
            raise ValueError(
                "image_shape must contain height and width"
            )

        return (
            int(image_shape[0]),
            int(image_shape[1]),
        )

    @staticmethod
    def _normalize_mask(
        mask: np.ndarray,
        target_shape,
    ) -> np.ndarray:

        if mask is None:
            return np.zeros(
                target_shape,
                dtype=np.uint8,
            )

        normalized = mask.copy()

        if normalized.ndim == 3:
            normalized = cv2.cvtColor(
                normalized,
                cv2.COLOR_BGR2GRAY,
            )

        if normalized.shape != tuple(
            target_shape
        ):
            normalized = cv2.resize(
                normalized,
                (
                    target_shape[1],
                    target_shape[0],
                ),
                interpolation=cv2.INTER_NEAREST,
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

    # =========================================================
    # FAILURE RESULT
    # =========================================================

    @staticmethod
    def _empty_result(
        empty: np.ndarray,
        message: str,

        room_mask=None,
        room_prior_mask=None,
        global_closed_shell_mask=None,
        guided_perimeter_band_mask=None,
        guided_wall_mask=None,
        guided_closed_shell_mask=None,
        selected_raw_building_mask=None,
        building_mask=None,
        usable_mask=None,
        outer_wall_mask=None,

        accepted_room_ids=None,
        excluded_room_ids=None,

        candidate_source="none",

        room_area_coverage=0.0,
        room_centroid_coverage=0.0,
        wall_support=0.0,

        selected_structural_gap_px=0,
        estimated_wall_thickness_px=0.0,
    ) -> HybridBoundaryDetectionResult:

        def value_or_empty(
            value
        ):
            return (
                value
                if value is not None
                else empty.copy()
            )

        return HybridBoundaryDetectionResult(
            outer_boundary=None,
            usable_boundary=None,

            room_mask=value_or_empty(
                room_mask
            ),
            room_prior_mask=value_or_empty(
                room_prior_mask
            ),

            global_closed_shell_mask=
                value_or_empty(
                    global_closed_shell_mask
                ),

            guided_perimeter_band_mask=
                value_or_empty(
                    guided_perimeter_band_mask
                ),
            guided_wall_mask=
                value_or_empty(
                    guided_wall_mask
                ),
            guided_closed_shell_mask=
                value_or_empty(
                    guided_closed_shell_mask
                ),

            selected_raw_building_mask=
                value_or_empty(
                    selected_raw_building_mask
                ),
            building_mask=
                value_or_empty(
                    building_mask
                ),
            usable_mask=
                value_or_empty(
                    usable_mask
                ),
            outer_wall_mask=
                value_or_empty(
                    outer_wall_mask
                ),

            accepted_room_ids=list(
                accepted_room_ids
                or []
            ),
            excluded_room_ids=list(
                excluded_room_ids
                or []
            ),

            candidate_source=
                candidate_source,

            room_area_coverage=float(
                room_area_coverage
            ),
            room_centroid_coverage=float(
                room_centroid_coverage
            ),
            wall_support=float(
                wall_support
            ),

            selected_structural_gap_px=int(
                selected_structural_gap_px
            ),
            estimated_wall_thickness_px=float(
                estimated_wall_thickness_px
            ),

            valid=False,
            message=message,
        )