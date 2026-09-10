from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import cv2
import numpy as np
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union


@dataclass
class RoomBoundaryDetectionResult:
    """
    Boundary reconstructed primarily from detected/corrected room polygons.

    All polygons use ORIGINAL IMAGE PIXEL coordinates.

    The important distinction is:

        usable_boundary
            The reconstructed interior envelope. Rooms used by the optimizer
            must stay inside this polygon.

        outer_boundary
            The exterior edge after nearby real wall pixels are added around
            the reconstructed interior.

    room_mask
        Raw rasterization of accepted room polygons.

    reconstructed_interior_mask
        Room-derived interior envelope after spatial gap reconstruction.

    nearby_wall_mask
        Thick-wall pixels captured around the room-derived envelope.

    building_mask
        reconstructed_interior_mask + nearby_wall_mask.

    outer_wall_mask
        Wall pixels close to the exterior edge of building_mask.
    """

    usable_boundary: Optional[Polygon]
    outer_boundary: Optional[Polygon]

    room_mask: np.ndarray
    reconstructed_interior_mask: np.ndarray
    nearby_wall_mask: np.ndarray
    building_mask: np.ndarray
    outer_wall_mask: np.ndarray

    accepted_room_ids: list[int]
    excluded_room_ids: list[int]

    room_coverage: float
    wall_support: float
    selected_bridge_px: int
    estimated_wall_thickness_px: float

    valid: bool
    message: str


class RoomBoundaryDetector:
    """
    Reconstruct a building boundary from ROOM GEOMETRY first.

    Why this approach
    -----------------
    Floor plans are unpredictable. A wall-only algorithm has to guess how to
    close windows, exterior doors, porches, recesses, garages, and many other
    shapes. Room detection already provides strong semantic evidence about
    which regions belong to the building.

    This detector therefore uses:

        PRIMARY:
            room.roomPoly coordinates

        SECONDARY:
            thick-wall mask, only to refine/capture the real exterior wall

    It does NOT use the colored lines drawn by room_detection.py. Those are
    visualization only.

    AI mode vs user mode
    --------------------
    mode="ai":
        Room detections can contain outliers. A conservative spatial outlier
        filter is used before reconstructing the envelope.

    mode="user":
        The user has corrected the room geometry. Every supplied room is
        trusted and must be covered by the reconstructed boundary.

    The intended workflow is:

        AI rooms -> calculate boundary -> Revision 1
        user corrects rooms -> recalculate boundary -> Revision 2+
    """

    def __init__(
        self,
        min_room_area_px: float = 150.0,
        min_ai_room_confidence: float = 0.0,
        cluster_link_fraction: float = 0.045,
        max_bridge_fraction: float = 0.18,
        candidate_steps: int = 7,
        wall_capture_multiplier: float = 2.5,
        boundary_support_multiplier: float = 2.5,
        small_close_px: int = 5,
        simplify_epsilon: float = 2.0,
    ):
        self.min_room_area_px = max(1.0, float(min_room_area_px))
        self.min_ai_room_confidence = float(min_ai_room_confidence)
        self.cluster_link_fraction = max(0.005, float(cluster_link_fraction))
        self.max_bridge_fraction = max(0.02, float(max_bridge_fraction))
        self.candidate_steps = max(2, int(candidate_steps))
        self.wall_capture_multiplier = max(1.0, float(wall_capture_multiplier))
        self.boundary_support_multiplier = max(1.0, float(boundary_support_multiplier))
        self.small_close_px = max(1, int(small_close_px))
        if self.small_close_px % 2 == 0:
            self.small_close_px += 1
        self.simplify_epsilon = max(0.0, float(simplify_epsilon))

    # =========================================================
    # PUBLIC API
    # =========================================================

    def detect(
        self,
        rooms: Iterable[object],
        image_shape,
        thick_wall_mask: Optional[np.ndarray] = None,
        mode: str = "ai",
    ) -> RoomBoundaryDetectionResult:

        mode = str(mode).strip().lower()
        if mode not in {"ai", "user"}:
            raise ValueError("mode must be either 'ai' or 'user'")

        height, width = self._shape_hw(image_shape)
        empty = np.zeros((height, width), dtype=np.uint8)

        wall_mask = (
            self._normalize_mask(thick_wall_mask, (height, width))
            if thick_wall_mask is not None
            else empty.copy()
        )

        estimated_wall_thickness = self._estimate_wall_thickness(wall_mask)

        room_records = self._collect_rooms(
            rooms=rooms,
            width=width,
            height=height,
            mode=mode,
        )

        if not room_records:
            return self._empty_result(
                empty,
                estimated_wall_thickness,
                "No valid room polygons were available for boundary reconstruction.",
            )

        accepted, excluded = self._filter_ai_outliers(
            room_records=room_records,
            width=width,
            height=height,
            mode=mode,
            estimated_wall_thickness=estimated_wall_thickness,
        )

        if not accepted:
            return self._empty_result(
                empty,
                estimated_wall_thickness,
                "All room polygons were rejected as invalid/outliers.",
                excluded_room_ids=[record["id"] for record in excluded],
            )

        room_mask = self._rasterize_rooms(
            accepted,
            width,
            height,
        )

        raw_area = int(np.count_nonzero(room_mask))
        if raw_area == 0:
            return self._empty_result(
                empty,
                estimated_wall_thickness,
                "The accepted room polygons produced an empty room mask.",
                accepted_room_ids=[record["id"] for record in accepted],
                excluded_room_ids=[record["id"] for record in excluded],
            )

        reference_points = [
            record["centroid"]
            for record in accepted
        ]

        bridge_values = self._bridge_candidates(
            accepted=accepted,
            width=width,
            height=height,
            estimated_wall_thickness=estimated_wall_thickness,
        )

        best = None

        for bridge_px in bridge_values:
            candidate = self._reconstruct_interior(
                room_mask=room_mask,
                bridge_px=bridge_px,
            )

            candidate = self._component_covering_most_rooms(
                candidate,
                reference_points,
            )

            if np.count_nonzero(candidate) == 0:
                continue

            coverage = self._room_point_coverage(
                candidate,
                reference_points,
            )

            wall_support = self._boundary_wall_support(
                candidate,
                wall_mask,
                support_distance=max(
                    8,
                    int(round(
                        estimated_wall_thickness
                        * self.boundary_support_multiplier
                    )),
                ),
            )

            candidate_area = int(np.count_nonzero(candidate))
            expansion_ratio = candidate_area / max(raw_area, 1)

            # Coverage dominates. Wall support chooses between similarly
            # complete candidates. Expansion penalty prevents the envelope
            # from growing into large unsupported exterior regions.
            score = (
                coverage * 1000.0
                + wall_support * 150.0
                - max(0.0, expansion_ratio - 1.0) * 18.0
                - bridge_px * 0.02
            )

            candidate_data = {
                "mask": candidate,
                "coverage": coverage,
                "wall_support": wall_support,
                "bridge_px": bridge_px,
                "score": score,
                "expansion_ratio": expansion_ratio,
            }

            if best is None or candidate_data["score"] > best["score"]:
                best = candidate_data

        if best is None:
            return self._empty_result(
                empty,
                estimated_wall_thickness,
                "Could not reconstruct an interior envelope from the room polygons.",
                room_mask=room_mask,
                accepted_room_ids=[record["id"] for record in accepted],
                excluded_room_ids=[record["id"] for record in excluded],
            )

        required_coverage = 0.999 if mode == "user" else 0.80

        if best["coverage"] < required_coverage:
            return self._empty_result(
                empty,
                estimated_wall_thickness,
                (
                    f"Room-derived envelope only covers "
                    f"{best['coverage'] * 100:.1f}% of accepted room centroids."
                ),
                room_mask=room_mask,
                reconstructed_interior_mask=best["mask"],
                accepted_room_ids=[record["id"] for record in accepted],
                excluded_room_ids=[record["id"] for record in excluded],
                room_coverage=best["coverage"],
                wall_support=best["wall_support"],
                selected_bridge_px=best["bridge_px"],
            )

        reconstructed = best["mask"]

        # The usable boundary is derived from ROOM COORDINATES, not from the
        # room detector's drawn visualization.
        usable_boundary = self._mask_to_polygon(reconstructed)

        if usable_boundary is None:
            return self._empty_result(
                empty,
                estimated_wall_thickness,
                "Could not convert the reconstructed room interior to a polygon.",
                room_mask=room_mask,
                reconstructed_interior_mask=reconstructed,
                accepted_room_ids=[record["id"] for record in accepted],
                excluded_room_ids=[record["id"] for record in excluded],
                room_coverage=best["coverage"],
                wall_support=best["wall_support"],
                selected_bridge_px=best["bridge_px"],
            )

        nearby_wall_mask = self._capture_nearby_walls(
            reconstructed_interior_mask=reconstructed,
            wall_mask=wall_mask,
            estimated_wall_thickness=estimated_wall_thickness,
        )

        building_mask = cv2.bitwise_or(
            reconstructed,
            nearby_wall_mask,
        )

        if self.small_close_px > 1:
            kernel = cv2.getStructuringElement(
                cv2.MORPH_RECT,
                (self.small_close_px, self.small_close_px),
            )
            building_mask = cv2.morphologyEx(
                building_mask,
                cv2.MORPH_CLOSE,
                kernel,
            )

        building_mask = self._component_covering_most_rooms(
            building_mask,
            reference_points,
        )

        outer_boundary = self._mask_to_polygon(building_mask)

        if outer_boundary is None:
            # Wall mask is optional. If it cannot improve the envelope,
            # preserve a valid room-derived result rather than failing.
            outer_boundary = usable_boundary
            building_mask = reconstructed.copy()
            nearby_wall_mask = empty.copy()

        outer_wall_mask = self._extract_outer_wall_pixels(
            building_mask=building_mask,
            wall_mask=wall_mask,
            estimated_wall_thickness=estimated_wall_thickness,
        )

        message = (
            "Room-based boundary reconstructed successfully. "
            f"Mode={mode}. "
            f"Accepted rooms={len(accepted)}, excluded rooms={len(excluded)}. "
            f"Room coverage={best['coverage'] * 100:.1f}%. "
            f"Boundary wall support={best['wall_support'] * 100:.1f}%. "
            f"Bridge={best['bridge_px']}px. "
            f"Estimated wall thickness={estimated_wall_thickness:.1f}px."
        )

        return RoomBoundaryDetectionResult(
            usable_boundary=usable_boundary,
            outer_boundary=outer_boundary,
            room_mask=room_mask,
            reconstructed_interior_mask=reconstructed,
            nearby_wall_mask=nearby_wall_mask,
            building_mask=building_mask,
            outer_wall_mask=outer_wall_mask,
            accepted_room_ids=[record["id"] for record in accepted],
            excluded_room_ids=[record["id"] for record in excluded],
            room_coverage=best["coverage"],
            wall_support=best["wall_support"],
            selected_bridge_px=best["bridge_px"],
            estimated_wall_thickness_px=estimated_wall_thickness,
            valid=True,
            message=message,
        )

    # =========================================================
    # ROOM COLLECTION / OUTLIERS
    # =========================================================

    def _collect_rooms(self, rooms, width, height, mode):
        image_box = Polygon([
            (0.0, 0.0),
            (float(width - 1), 0.0),
            (float(width - 1), float(height - 1)),
            (0.0, float(height - 1)),
        ])

        records = []

        for index, room in enumerate(rooms or []):
            poly = getattr(room, "roomPoly", None)
            if poly is None or getattr(poly, "is_empty", True):
                continue

            try:
                poly = poly.buffer(0)
            except Exception:
                continue

            if poly.is_empty:
                continue

            if isinstance(poly, MultiPolygon):
                poly = max(poly.geoms, key=lambda item: item.area)

            if not isinstance(poly, Polygon):
                continue

            try:
                poly = poly.intersection(image_box)
            except Exception:
                continue

            if poly.is_empty:
                continue

            if isinstance(poly, MultiPolygon):
                poly = max(poly.geoms, key=lambda item: item.area)

            if poly.area < self.min_room_area_px:
                continue

            confidence = getattr(room, "confidence", None)
            try:
                confidence_value = float(confidence) if confidence is not None else 1.0
            except (TypeError, ValueError):
                confidence_value = 1.0

            if mode == "ai" and confidence_value < self.min_ai_room_confidence:
                continue

            room_id = getattr(room, "id", index + 1)
            try:
                room_id = int(room_id)
            except (TypeError, ValueError):
                room_id = index + 1

            c = poly.centroid

            records.append({
                "id": room_id,
                "poly": poly,
                "centroid": (float(c.x), float(c.y)),
                "area": float(poly.area),
                "confidence": confidence_value,
            })

        return records

    def _filter_ai_outliers(
        self,
        room_records,
        width,
        height,
        mode,
        estimated_wall_thickness,
    ):
        if mode == "user" or len(room_records) <= 2:
            return list(room_records), []

        diagonal = float(np.hypot(width, height))
        link_distance = max(
            estimated_wall_thickness * 4.0,
            diagonal * self.cluster_link_fraction,
            18.0,
        )

        n = len(room_records)
        adjacency = [set() for _ in range(n)]

        for i in range(n):
            for j in range(i + 1, n):
                distance = room_records[i]["poly"].distance(room_records[j]["poly"])
                if distance <= link_distance:
                    adjacency[i].add(j)
                    adjacency[j].add(i)

        components = []
        unseen = set(range(n))

        while unseen:
            start = unseen.pop()
            stack = [start]
            component = [start]

            while stack:
                current = stack.pop()
                for neighbour in adjacency[current]:
                    if neighbour in unseen:
                        unseen.remove(neighbour)
                        stack.append(neighbour)
                        component.append(neighbour)

            components.append(component)

        if len(components) == 1:
            return list(room_records), []

        # Prefer number of rooms first, then total room area. This prevents one
        # giant false-positive polygon from beating a coherent cluster of many
        # real rooms.
        components.sort(
            key=lambda comp: (
                len(comp),
                sum(room_records[i]["area"] for i in comp),
            ),
            reverse=True,
        )

        main = components[0]
        main_records = [room_records[i] for i in main]
        main_union = unary_union([record["poly"] for record in main_records])

        accepted_indices = set(main)

        # Be conservative: an additional component is kept when it is still
        # reasonably close to the main cluster. This helps attached garages or
        # rooms separated by a missed hallway detection.
        secondary_keep_distance = link_distance * 2.25

        for component in components[1:]:
            component_union = unary_union([
                room_records[i]["poly"]
                for i in component
            ])

            if component_union.distance(main_union) <= secondary_keep_distance:
                accepted_indices.update(component)

        accepted = [
            room_records[i]
            for i in range(n)
            if i in accepted_indices
        ]

        excluded = [
            room_records[i]
            for i in range(n)
            if i not in accepted_indices
        ]

        return accepted, excluded

    # =========================================================
    # ROOM-BASED INTERIOR RECONSTRUCTION
    # =========================================================

    def _bridge_candidates(
        self,
        accepted,
        width,
        height,
        estimated_wall_thickness,
    ):
        min_dimension = float(min(width, height))

        bounds = [record["poly"].bounds for record in accepted]
        room_short_sides = [
            max(1.0, min(max_x - min_x, max_y - min_y))
            for min_x, min_y, max_x, max_y in bounds
        ]

        median_short_side = float(np.median(room_short_sides))

        base = max(
            6.0,
            estimated_wall_thickness * 1.5,
            median_short_side * 0.04,
        )

        maximum = max(
            base,
            min(
                min_dimension * self.max_bridge_fraction,
                median_short_side * 0.85,
            ),
        )

        values = np.linspace(
            base,
            maximum,
            self.candidate_steps,
        )

        unique = sorted({max(1, int(round(value))) for value in values})
        return unique

    def _reconstruct_interior(self, room_mask, bridge_px):
        mask = room_mask.copy()

        # Fill only BETWEEN existing room evidence. Nothing is extended beyond
        # the left/right or top/bottom extent of room evidence on that scanline.
        # This is safer for L/U shaped buildings than taking a convex hull.
        for _ in range(2):
            mask = self._fill_horizontal_gaps(mask, bridge_px)
            mask = self._fill_vertical_gaps(mask, bridge_px)

        # A modest closing connects diagonal/raster discontinuities.
        close_size = max(3, int(round(bridge_px * 0.35)))
        if close_size % 2 == 0:
            close_size += 1

        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (close_size, close_size),
        )

        mask = cv2.morphologyEx(
            mask,
            cv2.MORPH_CLOSE,
            kernel,
        )

        return mask

    @staticmethod
    def _fill_horizontal_gaps(mask, max_gap):
        output = mask.copy()
        height, width = output.shape

        for y in range(height):
            xs = np.flatnonzero(output[y] > 0)
            if xs.size < 2:
                continue

            # Runs of white pixels.
            breaks = np.where(np.diff(xs) > 1)[0]
            run_starts = np.r_[0, breaks + 1]
            run_ends = np.r_[breaks, xs.size - 1]

            for index in range(len(run_starts) - 1):
                left_end = int(xs[run_ends[index]])
                right_start = int(xs[run_starts[index + 1]])
                gap = right_start - left_end - 1

                if 0 < gap <= max_gap:
                    output[y, left_end:right_start + 1] = 255

        return output

    @staticmethod
    def _fill_vertical_gaps(mask, max_gap):
        output = mask.copy()
        height, width = output.shape

        for x in range(width):
            ys = np.flatnonzero(output[:, x] > 0)
            if ys.size < 2:
                continue

            breaks = np.where(np.diff(ys) > 1)[0]
            run_starts = np.r_[0, breaks + 1]
            run_ends = np.r_[breaks, ys.size - 1]

            for index in range(len(run_starts) - 1):
                top_end = int(ys[run_ends[index]])
                bottom_start = int(ys[run_starts[index + 1]])
                gap = bottom_start - top_end - 1

                if 0 < gap <= max_gap:
                    output[top_end:bottom_start + 1, x] = 255

        return output

    # =========================================================
    # WALL REFINEMENT
    # =========================================================

    def _capture_nearby_walls(
        self,
        reconstructed_interior_mask,
        wall_mask,
        estimated_wall_thickness,
    ):
        if np.count_nonzero(wall_mask) == 0:
            return np.zeros_like(reconstructed_interior_mask)

        capture = max(
            6,
            int(round(
                estimated_wall_thickness
                * self.wall_capture_multiplier
            )),
        )

        kernel_size = capture * 2 + 1
        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (kernel_size, kernel_size),
        )

        search_band = cv2.dilate(
            reconstructed_interior_mask,
            kernel,
            iterations=1,
        )

        nearby = cv2.bitwise_and(
            wall_mask,
            search_band,
        )

        return nearby

    def _extract_outer_wall_pixels(
        self,
        building_mask,
        wall_mask,
        estimated_wall_thickness,
    ):
        if np.count_nonzero(wall_mask) == 0:
            return np.zeros_like(building_mask)

        depth = max(
            6,
            int(round(estimated_wall_thickness * 2.0)),
        )

        kernel_size = depth * 2 + 1
        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (kernel_size, kernel_size),
        )

        eroded = cv2.erode(
            building_mask,
            kernel,
            iterations=1,
        )

        perimeter_band = cv2.subtract(
            building_mask,
            eroded,
        )

        return cv2.bitwise_and(
            wall_mask,
            perimeter_band,
        )

    # =========================================================
    # SCORING / COMPONENTS
    # =========================================================

    def _boundary_wall_support(self, mask, wall_mask, support_distance):
        if np.count_nonzero(wall_mask) == 0:
            return 0.0

        contour_pixels = np.zeros_like(mask)
        contours, _ = cv2.findContours(
            mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_NONE,
        )

        if not contours:
            return 0.0

        contour = max(contours, key=cv2.contourArea)
        cv2.drawContours(
            contour_pixels,
            [contour],
            -1,
            255,
            1,
        )

        boundary_count = int(np.count_nonzero(contour_pixels))
        if boundary_count == 0:
            return 0.0

        kernel_size = support_distance * 2 + 1
        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (kernel_size, kernel_size),
        )

        wall_nearby = cv2.dilate(
            wall_mask,
            kernel,
            iterations=1,
        )

        supported = cv2.bitwise_and(
            contour_pixels,
            wall_nearby,
        )

        return float(np.count_nonzero(supported)) / float(boundary_count)

    @staticmethod
    def _component_covering_most_rooms(mask, room_points):
        binary = (mask > 0).astype(np.uint8)
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
            binary,
            connectivity=8,
        )

        if num_labels <= 1:
            return np.zeros_like(mask)

        height, width = mask.shape
        best_label = None
        best_hits = -1
        best_area = -1

        for label in range(1, num_labels):
            hits = 0

            for x, y in room_points:
                ix = int(round(x))
                iy = int(round(y))

                if (
                    0 <= ix < width
                    and 0 <= iy < height
                    and labels[iy, ix] == label
                ):
                    hits += 1

            area = int(stats[label, cv2.CC_STAT_AREA])

            if hits > best_hits or (hits == best_hits and area > best_area):
                best_label = label
                best_hits = hits
                best_area = area

        result = np.zeros_like(mask)
        if best_label is not None:
            result[labels == best_label] = 255

        return result

    @staticmethod
    def _room_point_coverage(mask, room_points):
        if not room_points:
            return 0.0

        height, width = mask.shape
        hits = 0

        for x, y in room_points:
            ix = int(round(x))
            iy = int(round(y))

            if (
                0 <= ix < width
                and 0 <= iy < height
                and mask[iy, ix] > 0
            ):
                hits += 1

        return hits / len(room_points)

    # =========================================================
    # RASTER / POLYGON HELPERS
    # =========================================================

    @staticmethod
    def _rasterize_rooms(records, width, height):
        mask = np.zeros((height, width), dtype=np.uint8)

        for record in records:
            poly = record["poly"]
            points = np.rint(
                np.asarray(poly.exterior.coords, dtype=np.float64)
            ).astype(np.int32)

            if len(points) >= 3:
                cv2.fillPoly(mask, [points.reshape((-1, 1, 2))], 255)

        return mask

    def _mask_to_polygon(self, mask):
        contours, _ = cv2.findContours(
            mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )

        if not contours:
            return None

        contour = max(contours, key=cv2.contourArea)
        if cv2.contourArea(contour) <= 0:
            return None

        if self.simplify_epsilon > 0:
            contour = cv2.approxPolyDP(
                contour,
                self.simplify_epsilon,
                True,
            )

        points = contour.reshape(-1, 2)
        if len(points) < 3:
            return None

        poly = Polygon([
            (float(x), float(y))
            for x, y in points
        ])

        if not poly.is_valid:
            poly = poly.buffer(0)

        if poly.is_empty:
            return None

        if isinstance(poly, MultiPolygon):
            poly = max(poly.geoms, key=lambda item: item.area)

        return poly if isinstance(poly, Polygon) else None

    @staticmethod
    def _normalize_mask(mask, target_shape):
        if mask is None:
            return np.zeros(target_shape, dtype=np.uint8)

        normalized = mask.copy()

        if normalized.ndim == 3:
            normalized = cv2.cvtColor(normalized, cv2.COLOR_BGR2GRAY)

        if normalized.shape != target_shape:
            normalized = cv2.resize(
                normalized,
                (target_shape[1], target_shape[0]),
                interpolation=cv2.INTER_NEAREST,
            )

        _, normalized = cv2.threshold(
            normalized,
            127,
            255,
            cv2.THRESH_BINARY,
        )

        return normalized.astype(np.uint8)

    @staticmethod
    def _estimate_wall_thickness(wall_mask):
        if wall_mask is None or np.count_nonzero(wall_mask) == 0:
            return 8.0

        binary = (wall_mask > 0).astype(np.uint8)
        distance = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
        values = distance[distance > 0]

        if values.size == 0:
            return 8.0

        radius = float(np.percentile(values, 85))
        return max(2.0, radius * 2.0)

    @staticmethod
    def _shape_hw(image_shape):
        if image_shape is None:
            raise ValueError("image_shape is required")

        if len(image_shape) < 2:
            raise ValueError("image_shape must contain height and width")

        return int(image_shape[0]), int(image_shape[1])

    # =========================================================
    # FAILURE RESULT
    # =========================================================

    @staticmethod
    def _empty_result(
        reference_mask,
        estimated_wall_thickness,
        message,
        room_mask=None,
        reconstructed_interior_mask=None,
        nearby_wall_mask=None,
        building_mask=None,
        outer_wall_mask=None,
        accepted_room_ids=None,
        excluded_room_ids=None,
        room_coverage=0.0,
        wall_support=0.0,
        selected_bridge_px=0,
    ):
        empty = np.zeros_like(reference_mask, dtype=np.uint8)

        def value_or_empty(value):
            return value if value is not None else empty.copy()

        return RoomBoundaryDetectionResult(
            usable_boundary=None,
            outer_boundary=None,
            room_mask=value_or_empty(room_mask),
            reconstructed_interior_mask=value_or_empty(reconstructed_interior_mask),
            nearby_wall_mask=value_or_empty(nearby_wall_mask),
            building_mask=value_or_empty(building_mask),
            outer_wall_mask=value_or_empty(outer_wall_mask),
            accepted_room_ids=list(accepted_room_ids or []),
            excluded_room_ids=list(excluded_room_ids or []),
            room_coverage=float(room_coverage),
            wall_support=float(wall_support),
            selected_bridge_px=int(selected_bridge_px),
            estimated_wall_thickness_px=float(estimated_wall_thickness),
            valid=False,
            message=message,
        )