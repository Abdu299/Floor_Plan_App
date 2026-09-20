from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import hypot, log, sqrt
from typing import Any

from amplpy import AMPL, modules
from shapely import affinity
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

from .ampl_room_optimizer import (
    GEOMETRY_TOLERANCE_PIXELS,
    RoomGeometry,
    extract_boundary_polygon,
    extract_room_polygons,
    polygon_holes_to_points,
    polygon_only,
    polygon_to_points,
    resolve_target_room,
    square_metres_to_pixel_area,
)


@dataclass(frozen=True)
class PlacementCandidate:
    candidate_id: int
    room_id: int
    area_ratio: float
    scale_x: float
    scale_y: float
    translation_x: float
    translation_y: float
    movement_pixels: float
    polygon: Polygon

    @property
    def scale_factor(self) -> float:
        """Equivalent uniform scale retained for backwards-compatible JSON."""

        return sqrt(self.scale_x * self.scale_y)

    @property
    def aspect_distortion(self) -> float:
        return abs(log(self.scale_x / self.scale_y))


@dataclass
class GlobalPlacementResult:
    boundary: Polygon
    rooms: dict[int, RoomGeometry]
    target_room_id: int
    target_room_name: str
    selected_placements: dict[int, PlacementCandidate]
    solve_result: str
    invalid_solutions_rejected: int

    @property
    def target_original_area_pixels(self) -> float:
        return self.rooms[self.target_room_id].original_area_pixels

    @property
    def target_optimized_area_pixels(self) -> float:
        return self.rooms[self.target_room_id].optimized_area_pixels

    @property
    def target_gain_pixels(self) -> float:
        return self.target_optimized_area_pixels - self.target_original_area_pixels

    def to_dict(self) -> dict[str, Any]:
        placements = []
        for room_id, candidate in sorted(self.selected_placements.items()):
            placements.append(
                {
                    "candidateId": candidate.candidate_id,
                    "roomId": room_id,
                    "areaRatio": candidate.area_ratio,
                    "scaleFactor": candidate.scale_factor,
                    "scaleX": candidate.scale_x,
                    "scaleY": candidate.scale_y,
                    "aspectDistortion": candidate.aspect_distortion,
                    "translationX": candidate.translation_x,
                    "translationY": candidate.translation_y,
                    "movementPixels": candidate.movement_pixels,
                }
            )

        return {
            "optimizer": "topology-preserving-scale-and-place",
            "targetRoomId": self.target_room_id,
            "targetRoomName": self.target_room_name,
            "solveResult": self.solve_result,
            "invalidSolutionsRejected": self.invalid_solutions_rejected,
            "targetOriginalAreaPixels": self.target_original_area_pixels,
            "targetOptimizedAreaPixels": self.target_optimized_area_pixels,
            "targetGainPixels": self.target_gain_pixels,
            "buildingBoundary": {
                "polygon": polygon_to_points(self.boundary),
                "holes": polygon_holes_to_points(self.boundary),
            },
            "rooms": [
                {
                    "id": room.room_id,
                    "name": room.name,
                    "originalAreaPixels": room.original_area_pixels,
                    "optimizedAreaPixels": room.optimized_area_pixels,
                    "minimumAreaPixels": room.minimum_area_pixels,
                    "areaRatio": (
                        room.optimized_area_pixels / room.original_area_pixels
                        if room.original_area_pixels > 0
                        else 0.0
                    ),
                    "polygon": polygon_to_points(room.optimized_polygon),
                    "holes": polygon_holes_to_points(room.optimized_polygon),
                }
                for room in sorted(self.rooms.values(), key=lambda value: value.room_id)
            ],
            "selectedPlacements": placements,
            "selectedWallTransfers": [],
            "selectedExpansions": [],
        }


class GlobalPlacementOptimizer:
    """Scale and reposition complete rooms, then give the residual to the target.

    AMPL selects one discrete placement candidate for every non-target room.
    Each candidate is a controlled scale-and-translation of a normalized room.
    Original adjacencies between non-target rooms are preserved so the target
    cannot leak into every gap created by independent shrinking. The target is
    reconstructed as the building boundary minus all selected non-target rooms.
    """

    def __init__(
        self,
        solver: str = "highs",
        minimum_area_ratio: float = 0.60,
        placement_step_pixels: int = 20,
        max_movement_pixels: int = 120,
        scale_level_count: int = 5,
        boundary_contact_tolerance_pixels: float = 8.0,
        adjacency_contact_tolerance_pixels: float = 1.0,
        minimum_boundary_contact_pixels: float = 2.0,
        preserve_original_adjacency: bool = True,
        minimum_preserved_adjacency_ratio: float = 0.05,
        minimum_target_bbox_fill_ratio: float = 0.55,
        maximum_aspect_ratio_change: float = 1.75,
        max_invalid_solutions: int = 250,
    ):
        if not 0 < minimum_area_ratio <= 1:
            raise ValueError("minimum_area_ratio must be in the interval (0, 1]")
        if placement_step_pixels <= 0:
            raise ValueError("placement_step_pixels must be greater than zero")
        if max_movement_pixels < 0:
            raise ValueError("max_movement_pixels cannot be negative")
        if boundary_contact_tolerance_pixels < 0:
            raise ValueError("boundary_contact_tolerance_pixels cannot be negative")
        if adjacency_contact_tolerance_pixels < 0:
            raise ValueError("adjacency_contact_tolerance_pixels cannot be negative")
        if scale_level_count <= 0:
            raise ValueError("scale_level_count must be greater than zero")
        if max_invalid_solutions < 0:
            raise ValueError("max_invalid_solutions cannot be negative")
        if not 0 <= minimum_preserved_adjacency_ratio <= 1:
            raise ValueError(
                "minimum_preserved_adjacency_ratio must be in the interval [0, 1]"
            )
        if not 0 < minimum_target_bbox_fill_ratio <= 1:
            raise ValueError(
                "minimum_target_bbox_fill_ratio must be in the interval (0, 1]"
            )
        if maximum_aspect_ratio_change < 1:
            raise ValueError("maximum_aspect_ratio_change must be at least one")

        self.solver = solver
        self.minimum_area_ratio = float(minimum_area_ratio)
        self.placement_step_pixels = int(placement_step_pixels)
        self.max_movement_pixels = int(max_movement_pixels)
        self.scale_level_count = int(scale_level_count)
        self.boundary_contact_tolerance_pixels = float(
            boundary_contact_tolerance_pixels
        )
        self.adjacency_contact_tolerance_pixels = float(
            adjacency_contact_tolerance_pixels
        )
        self.minimum_boundary_contact_pixels = float(
            minimum_boundary_contact_pixels
        )
        self.preserve_original_adjacency = bool(preserve_original_adjacency)
        self.minimum_preserved_adjacency_ratio = float(
            minimum_preserved_adjacency_ratio
        )
        self.minimum_target_bbox_fill_ratio = float(
            minimum_target_bbox_fill_ratio
        )
        self.maximum_aspect_ratio_change = float(maximum_aspect_ratio_change)
        self.max_invalid_solutions = int(max_invalid_solutions)

    def optimize(
        self,
        detection_result: dict[str, Any],
        target_room: int | str,
        minimum_area_pixels: dict[int, float] | None = None,
        minimum_area_square_metres: dict[int, float] | None = None,
        pixels_per_metre: float | None = None,
    ) -> GlobalPlacementResult:
        boundary = extract_boundary_polygon(detection_result)
        rooms = extract_room_polygons(detection_result, boundary)
        target_id = resolve_target_room(rooms, target_room)
        minimums = self._build_minimum_areas(
            rooms,
            target_id,
            minimum_area_pixels or {},
            minimum_area_square_metres or {},
            pixels_per_metre,
        )
        self._validate_initial_layout(rooms, minimums)

        candidates = self._create_candidates(
            rooms=rooms,
            boundary=boundary,
            target_id=target_id,
            minimums=minimums,
        )
        preserved_adjacencies = self._find_preserved_adjacencies(
            rooms=rooms,
            target_id=target_id,
        )
        conflicts = self._find_conflicts(
            candidates,
            preserved_adjacencies,
        )
        forbidden_selections: list[set[int]] = []
        last_invalid_reason = ""

        for attempt in range(self.max_invalid_solutions + 1):
            selected, solve_result = self._solve_with_ampl(
                candidates=candidates,
                conflicts=conflicts,
                boundary=boundary,
                forbidden_selections=forbidden_selections,
            )
            optimized, invalid_reason = self._build_and_validate_partition(
                rooms=rooms,
                boundary=boundary,
                target_id=target_id,
                minimums=minimums,
                selected=selected,
            )

            if optimized is not None:
                room_results = {
                    room_id: RoomGeometry(
                        room_id=room_id,
                        name=data["name"],
                        original_polygon=data["polygon"],
                        optimized_polygon=optimized[room_id],
                        minimum_area_pixels=minimums[room_id],
                    )
                    for room_id, data in rooms.items()
                }
                return GlobalPlacementResult(
                    boundary=boundary,
                    rooms=room_results,
                    target_room_id=target_id,
                    target_room_name=rooms[target_id]["name"],
                    selected_placements={
                        candidate.room_id: candidate for candidate in selected
                    },
                    solve_result=solve_result,
                    invalid_solutions_rejected=attempt,
                )

            last_invalid_reason = invalid_reason or "invalid geometry"
            chosen_ids = {candidate.candidate_id for candidate in selected}
            if not chosen_ids:
                break
            forbidden_selections.append(chosen_ids)

        raise RuntimeError(
            "AMPL found placement-feasible solutions, but none produced a "
            "connected, hole-free target room after "
            f"{len(forbidden_selections)} retries. Last reason: {last_invalid_reason}"
        )

    def _build_minimum_areas(
        self,
        rooms: dict[int, dict[str, Any]],
        target_id: int,
        minimum_area_pixels: dict[int, float],
        minimum_area_square_metres: dict[int, float],
        pixels_per_metre: float | None,
    ) -> dict[int, float]:
        if minimum_area_square_metres and (
            pixels_per_metre is None or pixels_per_metre <= 0
        ):
            raise ValueError(
                "pixels_per_metre must be provided when minimum areas are given "
                "in square metres"
            )

        minimums: dict[int, float] = {}
        for room_id, data in rooms.items():
            original = float(data["polygon"].area)
            value = original if room_id == target_id else original * self.minimum_area_ratio

            if room_id in minimum_area_square_metres:
                value = square_metres_to_pixel_area(
                    minimum_area_square_metres[room_id],
                    float(pixels_per_metre),
                )
            if room_id in minimum_area_pixels:
                value = float(minimum_area_pixels[room_id])
            minimums[room_id] = float(value)

        return minimums

    @staticmethod
    def _validate_initial_layout(
        rooms: dict[int, dict[str, Any]],
        minimums: dict[int, float],
    ) -> None:
        room_ids = sorted(rooms)
        for room_id in room_ids:
            area = float(rooms[room_id]["polygon"].area)
            if minimums[room_id] <= 0:
                raise ValueError(f"Room {room_id} has a non-positive minimum area")
            if minimums[room_id] > area + GEOMETRY_TOLERANCE_PIXELS:
                raise ValueError(
                    f"Room {room_id} minimum ({minimums[room_id]:.2f}px²) exceeds "
                    f"its original area ({area:.2f}px²)"
                )

        for index, first_id in enumerate(room_ids):
            for second_id in room_ids[index + 1 :]:
                overlap = rooms[first_id]["polygon"].intersection(
                    rooms[second_id]["polygon"]
                ).area
                if overlap > GEOMETRY_TOLERANCE_PIXELS:
                    raise ValueError(
                        f"Rooms {first_id} and {second_id} overlap by "
                        f"{overlap:.2f}px² before optimization"
                    )

    def _create_candidates(
        self,
        rooms: dict[int, dict[str, Any]],
        boundary: Polygon,
        target_id: int,
        minimums: dict[int, float],
    ) -> list[PlacementCandidate]:
        candidates: list[PlacementCandidate] = []
        next_id = 1

        for room_id in sorted(rooms):
            if room_id == target_id:
                continue

            original = rooms[room_id]["polygon"]
            original_area = float(original.area)
            minimum_ratio = min(1.0, minimums[room_id] / original_area)
            ratios = self._scale_ratios(minimum_ratio)
            room_candidates: list[PlacementCandidate] = []
            seen: set[tuple[float, float, float, float]] = set()

            for ratio in ratios:
                for scale_x, scale_y in self._scale_pairs(ratio):
                    scaled = affinity.scale(
                        original,
                        xfact=scale_x,
                        yfact=scale_y,
                        origin=(original.centroid.x, original.centroid.y),
                    )

                    for dx, dy in self._translation_options(
                        original=original,
                        scaled=scaled,
                        boundary=boundary,
                    ):
                        key = (
                            round(scale_x, 8),
                            round(scale_y, 8),
                            round(dx, 5),
                            round(dy, 5),
                        )
                        if key in seen:
                            continue
                        seen.add(key)

                        transformed = affinity.translate(scaled, xoff=dx, yoff=dy)
                        outside_area = float(transformed.difference(boundary).area)
                        if outside_area > transformed.area * 0.01:
                            continue
                        # Image-derived exterior walls contain one-pixel stair
                        # steps. Clip only sub-1% protrusions to the fixed shell.
                        polygon = polygon_only(transformed.intersection(boundary))
                        if polygon is None:
                            continue
                        if polygon.interiors or not polygon.is_valid:
                            continue
                        if polygon.area + 1e-6 < minimums[room_id]:
                            continue

                        # Preserve the complete original target footprint.
                        if polygon.intersection(rooms[target_id]["polygon"]).area > (
                            GEOMETRY_TOLERANCE_PIXELS
                        ):
                            continue

                        if not self._preserves_exterior_anchor(
                            original=original,
                            candidate=polygon,
                            boundary=boundary,
                        ):
                            continue

                        movement = hypot(dx, dy)
                        room_candidates.append(
                            PlacementCandidate(
                                candidate_id=next_id,
                                room_id=room_id,
                                area_ratio=float(polygon.area / original_area),
                                scale_x=scale_x,
                                scale_y=scale_y,
                                translation_x=float(dx),
                                translation_y=float(dy),
                                movement_pixels=float(movement),
                                polygon=polygon,
                            )
                        )
                        next_id += 1

            if not room_candidates:
                raise RuntimeError(
                    f"No valid proportional placement candidates were generated "
                    f"for room {room_id}. Increase --max-movement or reduce "
                    "--placement-step."
                )
            candidates.extend(room_candidates)

        return candidates

    def _scale_ratios(self, minimum_ratio: float) -> list[float]:
        if self.scale_level_count == 1 or minimum_ratio >= 1.0 - 1e-9:
            return [minimum_ratio]

        ratios = [
            minimum_ratio
            + (1.0 - minimum_ratio) * level / (self.scale_level_count - 1)
            for level in range(self.scale_level_count)
        ]
        # Near-minimum alternatives compensate for tiny boundary clipping
        # caused by rasterized exterior-wall stair steps. AMPL still chooses
        # the smallest geometrically valid candidate.
        ratios.extend(
            min(1.0, minimum_ratio + delta)
            for delta in (0.0025, 0.005, 0.01, 0.02)
        )
        return sorted(set(ratios))

    def _scale_pairs(self, area_ratio: float) -> list[tuple[float, float]]:
        """Create uniform and one-axis-preserving shapes for one area ratio."""

        uniform = sqrt(area_ratio)
        pairs = [
            (uniform, uniform),
            (1.0, area_ratio),
            (area_ratio, 1.0),
        ]
        return [
            (scale_x, scale_y)
            for scale_x, scale_y in pairs
            if max(scale_x / scale_y, scale_y / scale_x)
            <= self.maximum_aspect_ratio_change + 1e-9
        ]

    def _translation_options(
        self,
        original: Polygon,
        scaled: Polygon,
        boundary: Polygon,
    ) -> list[tuple[float, float]]:
        ominx, ominy, omaxx, omaxy = original.bounds
        sminx, sminy, smaxx, smaxy = scaled.bounds
        bminx, bminy, bmaxx, bmaxy = boundary.bounds
        tolerance = self.boundary_contact_tolerance_pixels

        touches_left = abs(ominx - bminx) <= tolerance
        touches_right = abs(omaxx - bmaxx) <= tolerance
        touches_top = abs(ominy - bminy) <= tolerance
        touches_bottom = abs(omaxy - bmaxy) <= tolerance

        offsets = list(
            range(
                -self.max_movement_pixels,
                self.max_movement_pixels + 1,
                self.placement_step_pixels,
            )
        )
        if 0 not in offsets:
            offsets.append(0)

        if touches_left:
            x_values = [ominx - sminx]
        elif touches_right:
            x_values = [omaxx - smaxx]
        else:
            x_values = [float(value) for value in offsets]
            x_values.extend([ominx - sminx, omaxx - smaxx, 0.0])

        if touches_top:
            y_values = [ominy - sminy]
        elif touches_bottom:
            y_values = [omaxy - smaxy]
        else:
            y_values = [float(value) for value in offsets]
            y_values.extend([ominy - sminy, omaxy - smaxy, 0.0])

        return [(dx, dy) for dx in sorted(set(x_values)) for dy in sorted(set(y_values))]

    def _preserves_exterior_anchor(
        self,
        original: Polygon,
        candidate: Polygon,
        boundary: Polygon,
    ) -> bool:
        original_contact = original.boundary.intersection(boundary.boundary).length
        if original_contact < self.minimum_boundary_contact_pixels:
            return True

        candidate_contact = candidate.boundary.intersection(boundary.boundary).length
        return candidate_contact >= self.minimum_boundary_contact_pixels

    def _find_preserved_adjacencies(
        self,
        rooms: dict[int, dict[str, Any]],
        target_id: int,
    ) -> dict[tuple[int, int], float]:
        if not self.preserve_original_adjacency:
            return {}

        room_ids = sorted(room_id for room_id in rooms if room_id != target_id)
        result: dict[tuple[int, int], float] = {}
        for index, first_id in enumerate(room_ids):
            for second_id in room_ids[index + 1 :]:
                length = rooms[first_id]["polygon"].boundary.intersection(
                    rooms[second_id]["polygon"].boundary
                ).length
                if length >= self.minimum_boundary_contact_pixels:
                    result[(first_id, second_id)] = float(length)
        return result

    def _find_conflicts(
        self,
        candidates: list[PlacementCandidate],
        preserved_adjacencies: dict[tuple[int, int], float],
    ) -> list[tuple[int, int]]:
        conflicts: list[tuple[int, int]] = []
        for first_index, first in enumerate(candidates):
            for second in candidates[first_index + 1 :]:
                if first.room_id == second.room_id:
                    continue
                if first.polygon.intersection(second.polygon).area > (
                    GEOMETRY_TOLERANCE_PIXELS
                ):
                    conflicts.append((first.candidate_id, second.candidate_id))
                    continue

                room_pair = tuple(sorted((first.room_id, second.room_id)))
                original_length = preserved_adjacencies.get(room_pair)
                if original_length is None:
                    continue

                required_length = max(
                    self.minimum_boundary_contact_pixels,
                    original_length * self.minimum_preserved_adjacency_ratio,
                )
                near_contact = first.polygon.boundary.buffer(
                    self.adjacency_contact_tolerance_pixels,
                    cap_style=2,
                    join_style=2,
                ).intersection(second.polygon.boundary).length
                if near_contact < required_length:
                    conflicts.append((first.candidate_id, second.candidate_id))
        return conflicts

    def _solve_with_ampl(
        self,
        candidates: list[PlacementCandidate],
        conflicts: list[tuple[int, int]],
        boundary: Polygon,
        forbidden_selections: list[set[int]],
    ) -> tuple[list[PlacementCandidate], str]:
        candidate_by_id = {
            candidate.candidate_id: candidate for candidate in candidates
        }
        room_ids = sorted({candidate.room_id for candidate in candidates})

        try:
            ampl = AMPL(modules.load())
        except Exception:
            ampl = AMPL()

        ampl.eval(
            """
            set R;
            set C;
            param candidate_room {C} integer;
            param candidate_area {C} >= 0;
            param candidate_movement {C} >= 0;
            param candidate_distortion {C} >= 0;
            param building_area >= 0;

            var choose {C} binary;
            var target_area >= 0;

            subject to ChooseOnePlacement {r in R}:
                sum {c in C: candidate_room[c] = r} choose[c] = 1;

            subject to ResidualTargetArea:
                target_area = building_area
                    - sum {c in C} candidate_area[c] * choose[c];

            maximize TargetAreaThenMovement:
                target_area
                - 0.000001 * sum {c in C} candidate_movement[c] * choose[c]
                - 0.000001 * sum {c in C} candidate_distortion[c] * choose[c];
            """
        )

        data_lines = [
            "data;",
            "set R := " + " ".join(str(room_id) for room_id in room_ids) + ";",
            "set C := "
            + " ".join(str(candidate.candidate_id) for candidate in candidates)
            + ";",
            f"param building_area := {float(boundary.area):.10f};",
            "param candidate_room :=",
        ]
        data_lines.extend(
            f"{candidate.candidate_id} {candidate.room_id}"
            for candidate in candidates
        )
        data_lines.extend([";", "param candidate_area :="])
        data_lines.extend(
            f"{candidate.candidate_id} {float(candidate.polygon.area):.10f}"
            for candidate in candidates
        )
        data_lines.extend([";", "param candidate_movement :="])
        data_lines.extend(
            f"{candidate.candidate_id} {candidate.movement_pixels:.10f}"
            for candidate in candidates
        )
        data_lines.extend([";", "param candidate_distortion :="])
        data_lines.extend(
            f"{candidate.candidate_id} {candidate.aspect_distortion:.10f}"
            for candidate in candidates
        )
        data_lines.append(";")
        ampl.eval("\n".join(data_lines))

        # Compress thousands of pairwise conflict constraints into at most one
        # constraint per candidate. If candidate c is selected, every
        # incompatible candidate must be zero. If c is not selected, the
        # right-hand side equals the number of affected rooms; this is valid
        # because ChooseOnePlacement already selects only one candidate from
        # each room. This formulation is equivalent and also stays within the
        # 2,000-constraint AMPL demo-license limit for typical floor plans.
        incompatible: dict[int, set[int]] = defaultdict(set)
        for first_id, second_id in conflicts:
            incompatible[first_id].add(second_id)
            incompatible[second_id].add(first_id)

        for conflict_index, candidate_id in enumerate(
            sorted(incompatible),
            start=1,
        ):
            incompatible_ids = sorted(incompatible[candidate_id])
            affected_rooms = {
                candidate_by_id[other_id].room_id
                for other_id in incompatible_ids
            }
            terms = " + ".join(
                f"choose[{other_id}]" for other_id in incompatible_ids
            )
            ampl.eval(
                f"subject to PlacementConflict{conflict_index}: "
                f"{terms} <= {len(affected_rooms)} * "
                f"(1 - choose[{candidate_id}]);"
            )

        for cut_index, selection in enumerate(forbidden_selections, start=1):
            terms = " + ".join(
                f"choose[{candidate_id}]" for candidate_id in sorted(selection)
            )
            ampl.eval(
                f"subject to InvalidTargetGeometryCut{cut_index}: "
                f"{terms} <= {len(selection) - 1};"
            )

        ampl.option["solver"] = self.solver
        ampl.solve()
        solve_result = str(ampl.get_value("solve_result"))
        if "solved" not in solve_result.lower():
            raise RuntimeError(
                f"AMPL could not solve the global placement model: {solve_result}"
            )

        selected = [
            candidate_by_id[candidate_id]
            for candidate_id in sorted(candidate_by_id)
            if float(ampl.get_value(f"choose[{candidate_id}]")) > 0.5
        ]
        return selected, solve_result

    def _build_and_validate_partition(
        self,
        rooms: dict[int, dict[str, Any]],
        boundary: Polygon,
        target_id: int,
        minimums: dict[int, float],
        selected: list[PlacementCandidate],
    ) -> tuple[dict[int, Polygon] | None, str | None]:
        optimized = {
            candidate.room_id: candidate.polygon for candidate in selected
        }
        expected_non_target_ids = set(rooms) - {target_id}
        if set(optimized) != expected_non_target_ids:
            return None, "not every non-target room received one placement"

        for room_id, polygon in optimized.items():
            if polygon.area + 1e-6 < minimums[room_id]:
                return None, f"room {room_id} fell below its minimum area"

        target_seed = rooms[target_id]["polygon"].representative_point()
        non_target_union = unary_union(list(optimized.values()))
        residual = boundary.difference(non_target_union)

        # Clipping scaled polygons to a pixel-stair exterior boundary can
        # isolate tiny wall-edge slivers. They are detection artefacts, not
        # usable target-room components. Assign only sub-percent slivers to
        # the adjacent non-target room, then reconstruct the residual.
        if isinstance(residual, MultiPolygon):
            parts = list(residual.geoms)
            seed_parts = [
                part
                for part in parts
                if part.buffer(GEOMETRY_TOLERANCE_PIXELS).covers(target_seed)
            ]
            main = max(seed_parts or parts, key=lambda part: part.area)
            slivers = [part for part in parts if part is not main]
            sliver_area = sum(part.area for part in slivers)

            if sliver_area > boundary.area * 0.005:
                return (
                    None,
                    "the residual target room has substantial disconnected "
                    f"components ({sliver_area:.2f}px²)",
                )

            for sliver in slivers:
                receiver_id = max(
                    optimized,
                    key=lambda room_id: optimized[room_id].boundary.intersection(
                        sliver.boundary
                    ).length,
                )
                shared_length = optimized[receiver_id].boundary.intersection(
                    sliver.boundary
                ).length
                if shared_length <= 0:
                    return None, "an exterior residual sliver has no adjacent room"

                repaired = polygon_only(optimized[receiver_id].union(sliver))
                if repaired is None:
                    return None, f"could not repair boundary sliver near room {receiver_id}"
                optimized[receiver_id] = repaired

            non_target_union = unary_union(list(optimized.values()))
            residual = boundary.difference(non_target_union)

        target = polygon_only(residual)
        if target is None:
            return None, "the residual target room became disconnected or empty"
        if target.interiors:
            return None, "the residual target room contains an interior hole"
        if target.area + 1e-6 < minimums[target_id]:
            return None, "the target room became smaller than its original area"

        if not target.buffer(GEOMETRY_TOLERANCE_PIXELS).covers(target_seed):
            return None, "the residual no longer contains the original target room"

        minimum_x, minimum_y, maximum_x, maximum_y = target.bounds
        bounding_box_area = (maximum_x - minimum_x) * (maximum_y - minimum_y)
        bbox_fill_ratio = target.area / bounding_box_area if bounding_box_area > 0 else 0
        if bbox_fill_ratio + 1e-9 < self.minimum_target_bbox_fill_ratio:
            return (
                None,
                "the target room is too spread out: bounding-box fill ratio "
                f"{bbox_fill_ratio:.3f} is below "
                f"{self.minimum_target_bbox_fill_ratio:.3f}",
            )

        optimized[target_id] = target
        union = unary_union(list(optimized.values()))
        changed_coverage = union.symmetric_difference(boundary).area
        if changed_coverage > GEOMETRY_TOLERANCE_PIXELS:
            return None, f"partition coverage changed by {changed_coverage:.2f}px²"

        return optimized, None
