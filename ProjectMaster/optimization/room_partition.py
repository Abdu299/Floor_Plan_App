from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
from scipy.ndimage import distance_transform_edt
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, box
from shapely.ops import unary_union


@dataclass
class PartitionResult:
    detection_result: dict[str, Any]
    boundary: Polygon
    room_polygons: dict[int, Polygon]
    max_fill_distance_pixels: float
    estimated_wall_thickness_pixels: float
    initial_unassigned_pixels: int
    filled_pixels: int
    remaining_unassigned_pixels: int
    overlap_pixels: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "maxFillDistancePixels": self.max_fill_distance_pixels,
            "estimatedWallThicknessPixels": self.estimated_wall_thickness_pixels,
            "initialUnassignedPixels": self.initial_unassigned_pixels,
            "filledPixels": self.filled_pixels,
            "remainingUnassignedPixels": self.remaining_unassigned_pixels,
            "overlapPixels": self.overlap_pixels,
            "rooms": [
                {
                    "id": room_id,
                    "areaPixels": float(polygon.area),
                    "polygon": polygon_to_points(polygon),
                }
                for room_id, polygon in sorted(self.room_polygons.items())
            ],
        }


class RoomPartitionBuilder:
    def __init__(
        self,
        max_fill_distance_pixels: float | None = None,
        wall_thickness_multiplier: float = 1.25,
        default_fill_distance_pixels: float = 12.0,
        maximum_automatic_fill_distance_pixels: float = 35.0,
    ):
        if max_fill_distance_pixels is not None and max_fill_distance_pixels <= 0:
            raise ValueError("max_fill_distance_pixels must be greater than zero")
        if wall_thickness_multiplier <= 0:
            raise ValueError("wall_thickness_multiplier must be greater than zero")
        if default_fill_distance_pixels <= 0:
            raise ValueError("default_fill_distance_pixels must be greater than zero")
        if maximum_automatic_fill_distance_pixels <= 0:
            raise ValueError("maximum_automatic_fill_distance_pixels must be greater than zero")

        self.max_fill_distance_pixels = max_fill_distance_pixels
        self.wall_thickness_multiplier = float(wall_thickness_multiplier)
        self.default_fill_distance_pixels = float(default_fill_distance_pixels)
        self.maximum_automatic_fill_distance_pixels = float(
            maximum_automatic_fill_distance_pixels
        )

    def build(
        self,
        detection_result: dict[str, Any],
        image_shape,
    ) -> PartitionResult:
        height, width = int(image_shape[0]), int(image_shape[1])
        boundary = extract_boundary_polygon(detection_result)
        rooms = extract_room_polygons(detection_result, boundary)

        boundary_mask = rasterize_polygon(boundary, width, height)
        room_masks: dict[int, np.ndarray] = {}
        coverage_count = np.zeros((height, width), dtype=np.uint16)

        for room_id, data in rooms.items():
            mask = rasterize_polygon(data["polygon"], width, height)
            mask = np.where(boundary_mask > 0, mask, 0).astype(np.uint8)
            room_masks[room_id] = mask
            coverage_count += (mask > 0).astype(np.uint16)

        overlap_pixels = int(np.count_nonzero(coverage_count > 1))
        labels = np.zeros((height, width), dtype=np.int32)

        for room_id in sorted(room_masks):
            mask = room_masks[room_id] > 0
            labels[(labels == 0) & mask] = room_id

        inside = boundary_mask > 0
        blank_before = inside & (labels == 0)
        initial_unassigned_pixels = int(np.count_nonzero(blank_before))

        estimated_wall_thickness = get_estimated_wall_thickness(detection_result)
        fill_distance = self._resolve_fill_distance(estimated_wall_thickness)

        nearest_distance = np.full((height, width), np.inf, dtype=np.float64)
        second_distance = np.full((height, width), np.inf, dtype=np.float64)
        nearest_label = np.zeros((height, width), dtype=np.int32)

        for room_id in sorted(room_masks):
            room_mask = room_masks[room_id] > 0
            if not np.any(room_mask):
                continue

            distance = distance_transform_edt(~room_mask)
            better = distance < nearest_distance

            second_distance[better] = nearest_distance[better]
            nearest_distance[better] = distance[better]
            nearest_label[better] = room_id

            second_better = (~better) & (distance < second_distance)
            second_distance[second_better] = distance[second_better]

        boundary_edge_distance = distance_transform_edt(inside)

        near_room = nearest_distance <= fill_distance + 0.5
        between_rooms = second_distance <= (2.0 * fill_distance + 1.0)
        near_boundary = boundary_edge_distance <= fill_distance + 1.0

        fill_mask = (
            blank_before
            & near_room
            & (between_rooms | near_boundary)
            & (nearest_label > 0)
        )

        labels[fill_mask] = nearest_label[fill_mask]
        filled_pixels = int(np.count_nonzero(fill_mask))
        remaining_unassigned_pixels = int(
            np.count_nonzero(inside & (labels == 0))
        )

        normalized_polygons: dict[int, Polygon] = {}

        for room_id, data in rooms.items():
            polygon = label_region_to_polygon(
                labels,
                room_id,
                boundary,
                data["polygon"],
            )

            if polygon is None or polygon.area <= 0.5:
                polygon = data["polygon"]

            normalized_polygons[room_id] = polygon

        normalized_result = deepcopy(detection_result)
        normalized_rooms_by_id = {
            int(room["id"]): room
            for room in normalized_result.get("rooms", [])
        }

        for room_id, polygon in normalized_polygons.items():
            room = normalized_rooms_by_id[room_id]
            centroid = polygon.centroid
            room["polygon"] = polygon_to_points(polygon)
            room["centroid"] = {
                "x": float(centroid.x),
                "y": float(centroid.y),
            }
            room["areaPixels"] = float(polygon.area)

        normalized_result["optimizationPartition"] = {
            "maxFillDistancePixels": float(fill_distance),
            "estimatedWallThicknessPixels": float(estimated_wall_thickness),
            "initialUnassignedPixels": initial_unassigned_pixels,
            "filledPixels": filled_pixels,
            "remainingUnassignedPixels": remaining_unassigned_pixels,
            "overlapPixels": overlap_pixels,
        }

        return PartitionResult(
            detection_result=normalized_result,
            boundary=boundary,
            room_polygons=normalized_polygons,
            max_fill_distance_pixels=float(fill_distance),
            estimated_wall_thickness_pixels=float(estimated_wall_thickness),
            initial_unassigned_pixels=initial_unassigned_pixels,
            filled_pixels=filled_pixels,
            remaining_unassigned_pixels=remaining_unassigned_pixels,
            overlap_pixels=overlap_pixels,
        )

    def _resolve_fill_distance(self, estimated_wall_thickness: float) -> float:
        if self.max_fill_distance_pixels is not None:
            return float(self.max_fill_distance_pixels)

        if estimated_wall_thickness > 0:
            value = estimated_wall_thickness * self.wall_thickness_multiplier
            return float(
                max(
                    4.0,
                    min(
                        value,
                        self.maximum_automatic_fill_distance_pixels,
                    ),
                )
            )

        return self.default_fill_distance_pixels


def get_estimated_wall_thickness(detection_result: dict[str, Any]) -> float:
    boundary = detection_result.get("buildingBoundary") or {}
    assessment = boundary.get("automaticAssessment") or {}
    value = assessment.get("estimatedWallThicknessPixels")

    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0

    if not np.isfinite(number) or number <= 0:
        return 0.0

    return number


def extract_boundary_polygon(detection_result: dict[str, Any]) -> Polygon:
    boundary_data = detection_result.get("buildingBoundary") or {}
    points = boundary_data.get("polygon")

    if not points:
        points = boundary_data.get("usablePolygon")

    if not points:
        raise ValueError("No usable building boundary polygon was returned by detection")

    polygon = points_to_polygon(points)

    if polygon is None:
        raise ValueError("The detected building boundary is not a valid polygon")

    return polygon


def extract_room_polygons(
    detection_result: dict[str, Any],
    boundary: Polygon,
) -> dict[int, dict[str, Any]]:
    rooms: dict[int, dict[str, Any]] = {}

    for room in detection_result.get("rooms", []):
        room_id = int(room["id"])
        polygon = points_to_polygon(room.get("polygon") or [])

        if polygon is None:
            raise ValueError(f"Room {room_id} does not have a valid polygon")

        geometry = polygon.intersection(boundary)
        polygon = choose_polygon_component(geometry, polygon)

        if polygon is None or polygon.area <= 0.5:
            raise ValueError(f"Room {room_id} is outside the usable building boundary")

        rooms[room_id] = {
            "id": room_id,
            "name": str(room.get("name") or f"Room {room_id}"),
            "polygon": polygon,
        }

    if not rooms:
        raise ValueError("No rooms were returned by detection")

    return rooms


def points_to_polygon(points: list[dict[str, Any]]) -> Polygon | None:
    if len(points) < 3:
        return None

    polygon = Polygon(
        [
            (float(point["x"]), float(point["y"]))
            for point in points
        ]
    )

    if not polygon.is_valid:
        polygon = polygon.buffer(0)

    return choose_polygon_component(polygon, None)


def polygon_to_points(polygon: Polygon) -> list[dict[str, float]]:
    coordinates = list(polygon.exterior.coords)

    if len(coordinates) > 1 and coordinates[0] == coordinates[-1]:
        coordinates = coordinates[:-1]

    return [
        {
            "x": float(x),
            "y": float(y),
        }
        for x, y in coordinates
    ]


def rasterize_polygon(
    polygon: Polygon,
    width: int,
    height: int,
) -> np.ndarray:
    mask = np.zeros((height, width), dtype=np.uint8)
    points = np.rint(
        np.asarray(polygon.exterior.coords, dtype=np.float64)
    ).astype(np.int32)

    if len(points) < 3:
        return mask

    points[:, 0] = np.clip(points[:, 0], 0, width - 1)
    points[:, 1] = np.clip(points[:, 1], 0, height - 1)

    cv2.fillPoly(
        mask,
        [points.reshape((-1, 1, 2))],
        255,
    )

    for interior in polygon.interiors:
        hole = np.rint(
            np.asarray(interior.coords, dtype=np.float64)
        ).astype(np.int32)

        if len(hole) >= 3:
            hole[:, 0] = np.clip(hole[:, 0], 0, width - 1)
            hole[:, 1] = np.clip(hole[:, 1], 0, height - 1)
            cv2.fillPoly(
                mask,
                [hole.reshape((-1, 1, 2))],
                0,
            )

    return mask


def label_region_to_polygon(
    labels: np.ndarray,
    room_id: int,
    boundary: Polygon,
    reference: Polygon,
) -> Polygon | None:
    mask = labels == room_id

    if not np.any(mask):
        return None

    pieces = []
    rows = np.where(mask.any(axis=1))[0]

    for y in rows:
        xs = np.flatnonzero(mask[y])

        if xs.size == 0:
            continue

        starts = np.r_[0, np.where(np.diff(xs) > 1)[0] + 1]
        ends = np.r_[starts[1:] - 1, xs.size - 1]

        for start_index, end_index in zip(starts, ends):
            x1 = int(xs[start_index])
            x2 = int(xs[end_index])
            pieces.append(
                box(
                    x1 - 0.5,
                    y - 0.5,
                    x2 + 0.5,
                    y + 0.5,
                )
            )

    if not pieces:
        return None

    geometry = unary_union(pieces).intersection(boundary)
    return choose_polygon_component(geometry, reference)


def choose_polygon_component(
    geometry,
    reference: Polygon | None,
) -> Polygon | None:
    if geometry is None or geometry.is_empty:
        return None

    if isinstance(geometry, Polygon):
        return geometry

    polygons: list[Polygon] = []

    if isinstance(geometry, MultiPolygon):
        polygons = [
            polygon
            for polygon in geometry.geoms
            if not polygon.is_empty
        ]

    elif isinstance(geometry, GeometryCollection):
        polygons = [
            polygon
            for polygon in geometry.geoms
            if isinstance(polygon, Polygon) and not polygon.is_empty
        ]

    if not polygons:
        return None

    if reference is None:
        return max(polygons, key=lambda polygon: polygon.area)

    return max(
        polygons,
        key=lambda polygon: (
            polygon.intersection(reference).area,
            polygon.area,
        ),
    )
