from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from typing import Any

from amplpy import AMPL, modules
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon
from shapely.ops import unary_union


@dataclass
class RoomGeometry:
    room_id: int
    name: str
    original_polygon: Polygon
    optimized_polygon: Polygon
    minimum_area_pixels: float

    @property
    def original_area_pixels(self) -> float:
        return float(self.original_polygon.area)

    @property
    def optimized_area_pixels(self) -> float:
        return float(self.optimized_polygon.area)


@dataclass
class ExpansionOption:
    option_id: int
    neighbor_id: int
    depth_pixels: int
    transfer_polygon: Polygon | None
    remaining_polygon: Polygon
    gain_pixels: float
    remaining_area_pixels: float


@dataclass
class OptimizationResult:
    boundary: Polygon
    rooms: dict[int, RoomGeometry]
    target_room_id: int
    target_room_name: str
    selected_options: dict[int, ExpansionOption]
    solve_result: str

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
        return {
            "targetRoomId": self.target_room_id,
            "targetRoomName": self.target_room_name,
            "solveResult": self.solve_result,
            "targetOriginalAreaPixels": self.target_original_area_pixels,
            "targetOptimizedAreaPixels": self.target_optimized_area_pixels,
            "targetGainPixels": self.target_gain_pixels,
            "buildingBoundary": {
                "polygon": polygon_to_points(self.boundary),
            },
            "rooms": [
                {
                    "id": room.room_id,
                    "name": room.name,
                    "originalAreaPixels": room.original_area_pixels,
                    "optimizedAreaPixels": room.optimized_area_pixels,
                    "minimumAreaPixels": room.minimum_area_pixels,
                    "polygon": polygon_to_points(room.optimized_polygon),
                }
                for room in sorted(self.rooms.values(), key=lambda value: value.room_id)
            ],
            "selectedExpansions": [
                {
                    "neighborRoomId": option.neighbor_id,
                    "depthPixels": option.depth_pixels,
                    "gainPixels": option.gain_pixels,
                    "remainingAreaPixels": option.remaining_area_pixels,
                }
                for option in sorted(
                    self.selected_options.values(),
                    key=lambda value: value.neighbor_id,
                )
            ],
        }


class AmplRoomOptimizer:
    def __init__(
        self,
        solver: str = "highs",
        expansion_step_pixels: int = 5,
        max_expansion_pixels: int = 250,
        minimum_area_ratio: float = 0.60,
        minimum_shared_wall_pixels: float = 8.0,
    ):
        if expansion_step_pixels <= 0:
            raise ValueError("expansion_step_pixels must be greater than zero")
        if max_expansion_pixels <= 0:
            raise ValueError("max_expansion_pixels must be greater than zero")
        if not 0 < minimum_area_ratio <= 1:
            raise ValueError("minimum_area_ratio must be in the interval (0, 1]")

        self.solver = solver
        self.expansion_step_pixels = int(expansion_step_pixels)
        self.max_expansion_pixels = int(max_expansion_pixels)
        self.minimum_area_ratio = float(minimum_area_ratio)
        self.minimum_shared_wall_pixels = float(minimum_shared_wall_pixels)

    def optimize(
        self,
        detection_result: dict[str, Any],
        target_room: int | str,
        minimum_area_pixels: dict[int, float] | None = None,
        minimum_area_square_metres: dict[int, float] | None = None,
        pixels_per_metre: float | None = None,
    ) -> OptimizationResult:
        boundary = extract_boundary_polygon(detection_result)
        detected_rooms = extract_room_polygons(detection_result, boundary)
        target_id = resolve_target_room(detected_rooms, target_room)
        minimums = self._build_minimum_areas(
            detected_rooms,
            target_id,
            minimum_area_pixels or {},
            minimum_area_square_metres or {},
            pixels_per_metre,
        )
        self._validate_initial_layout(detected_rooms, target_id, minimums)
        options = self._create_options(detected_rooms, target_id)

        if not options:
            rooms = {
                room_id: RoomGeometry(
                    room_id=room_id,
                    name=data["name"],
                    original_polygon=data["polygon"],
                    optimized_polygon=data["polygon"],
                    minimum_area_pixels=minimums.get(room_id, 0.0),
                )
                for room_id, data in detected_rooms.items()
            }
            return OptimizationResult(
                boundary=boundary,
                rooms=rooms,
                target_room_id=target_id,
                target_room_name=detected_rooms[target_id]["name"],
                selected_options={},
                solve_result="no-adjacent-expansion-options",
            )

        selected, solve_result = self._solve_with_ampl(options, minimums)
        optimized_polygons = {
            room_id: data["polygon"]
            for room_id, data in detected_rooms.items()
        }
        target_parts = [detected_rooms[target_id]["polygon"]]

        for neighbor_id, option in selected.items():
            optimized_polygons[neighbor_id] = option.remaining_polygon
            if option.transfer_polygon is not None and not option.transfer_polygon.is_empty:
                target_parts.append(option.transfer_polygon)

        target_polygon = polygon_only(unary_union(target_parts))
        if target_polygon is None:
            raise RuntimeError("The optimized target room is not a single connected polygon")

        target_polygon = polygon_only(target_polygon.intersection(boundary))
        if target_polygon is None:
            raise RuntimeError("The optimized target room became invalid after boundary clipping")

        optimized_polygons[target_id] = target_polygon

        rooms = {
            room_id: RoomGeometry(
                room_id=room_id,
                name=data["name"],
                original_polygon=data["polygon"],
                optimized_polygon=optimized_polygons[room_id],
                minimum_area_pixels=minimums.get(room_id, 0.0),
            )
            for room_id, data in detected_rooms.items()
        }

        return OptimizationResult(
            boundary=boundary,
            rooms=rooms,
            target_room_id=target_id,
            target_room_name=detected_rooms[target_id]["name"],
            selected_options=selected,
            solve_result=solve_result,
        )

    def _build_minimum_areas(
        self,
        rooms: dict[int, dict[str, Any]],
        target_id: int,
        minimum_area_pixels: dict[int, float],
        minimum_area_square_metres: dict[int, float],
        pixels_per_metre: float | None,
    ) -> dict[int, float]:
        if minimum_area_square_metres and (pixels_per_metre is None or pixels_per_metre <= 0):
            raise ValueError("pixels_per_metre must be provided when minimum areas are given in square metres")

        minimums: dict[int, float] = {}
        for room_id, data in rooms.items():
            if room_id == target_id:
                minimums[room_id] = 0.0
                continue

            original_area = float(data["polygon"].area)
            value = original_area * self.minimum_area_ratio

            if room_id in minimum_area_square_metres:
                value = square_metres_to_pixel_area(
                    minimum_area_square_metres[room_id],
                    float(pixels_per_metre),
                )

            if room_id in minimum_area_pixels:
                value = float(minimum_area_pixels[room_id])

            minimums[room_id] = float(value)

        return minimums

    def _validate_initial_layout(
        self,
        rooms: dict[int, dict[str, Any]],
        target_id: int,
        minimums: dict[int, float],
    ) -> None:
        room_ids = sorted(rooms)
        for room_id in room_ids:
            if room_id == target_id:
                continue
            current_area = float(rooms[room_id]["polygon"].area)
            if current_area + 1e-6 < minimums[room_id]:
                raise ValueError(
                    f"Room {room_id} starts below its minimum area: "
                    f"current={current_area:.2f}px², minimum={minimums[room_id]:.2f}px²"
                )

        for first_index, first_id in enumerate(room_ids):
            first = rooms[first_id]["polygon"]
            for second_id in room_ids[first_index + 1:]:
                second = rooms[second_id]["polygon"]
                overlap = first.intersection(second).area
                if overlap > 1.0:
                    raise ValueError(
                        f"Rooms {first_id} and {second_id} overlap by {overlap:.2f}px² before optimization"
                    )

    def _create_options(
        self,
        rooms: dict[int, dict[str, Any]],
        target_id: int,
    ) -> list[ExpansionOption]:
        target = rooms[target_id]["polygon"]
        all_options: list[ExpansionOption] = []
        next_option_id = 1

        for neighbor_id, data in rooms.items():
            if neighbor_id == target_id:
                continue

            neighbor = data["polygon"]
            shared_length = float(target.boundary.intersection(neighbor.boundary).length)
            if shared_length < self.minimum_shared_wall_pixels:
                continue

            neighbor_options: list[ExpansionOption] = [
                ExpansionOption(
                    option_id=next_option_id,
                    neighbor_id=neighbor_id,
                    depth_pixels=0,
                    transfer_polygon=None,
                    remaining_polygon=neighbor,
                    gain_pixels=0.0,
                    remaining_area_pixels=float(neighbor.area),
                )
            ]
            next_option_id += 1
            last_gain = 0.0

            for depth in range(
                self.expansion_step_pixels,
                self.max_expansion_pixels + self.expansion_step_pixels,
                self.expansion_step_pixels,
            ):
                expanded = target.buffer(depth, join_style=2)
                transfer = polygon_only(expanded.intersection(neighbor))

                if transfer is None or transfer.area <= 0.5:
                    continue

                combined = polygon_only(target.union(transfer))
                if combined is None:
                    continue

                remaining = polygon_only(neighbor.difference(transfer))
                if remaining is None or remaining.area <= 0.5:
                    continue

                if len(remaining.interiors) > 0:
                    continue

                gain = float(transfer.area)
                if gain <= last_gain + 0.5:
                    continue

                neighbor_options.append(
                    ExpansionOption(
                        option_id=next_option_id,
                        neighbor_id=neighbor_id,
                        depth_pixels=depth,
                        transfer_polygon=transfer,
                        remaining_polygon=remaining,
                        gain_pixels=gain,
                        remaining_area_pixels=float(remaining.area),
                    )
                )
                next_option_id += 1
                last_gain = gain

                if remaining.area <= 1.0:
                    break

            if len(neighbor_options) > 1:
                all_options.extend(neighbor_options)

        return all_options

    def _solve_with_ampl(
        self,
        options: list[ExpansionOption],
        minimums: dict[int, float],
    ) -> tuple[dict[int, ExpansionOption], str]:
        neighbors = sorted({option.neighbor_id for option in options})
        by_id = {option.option_id: option for option in options}

        try:
            ampl = AMPL(modules.load())
        except Exception:
            ampl = AMPL()

        ampl.eval(
            """
            set N;
            set O;
            param owner {O} integer;
            param gain {O} >= 0;
            param remaining {O} >= 0;
            param depth {O} >= 0;
            param min_area {N} >= 0;
            var choose {O} binary;
            maximize TargetRoomAreaGain:
                sum {o in O} (gain[o] - 0.000001 * depth[o]) * choose[o];
            subject to ChooseOneOption {n in N}:
                sum {o in O: owner[o] = n} choose[o] = 1;
            subject to KeepMinimumArea {n in N}:
                sum {o in O: owner[o] = n} remaining[o] * choose[o] >= min_area[n];
            """
        )

        data_lines = [
            "data;",
            "set N := " + " ".join(str(value) for value in neighbors) + ";",
            "set O := " + " ".join(str(option.option_id) for option in options) + ";",
            "param owner :=",
        ]
        data_lines.extend(f"{option.option_id} {option.neighbor_id}" for option in options)
        data_lines.append(";")
        data_lines.append("param gain :=")
        data_lines.extend(f"{option.option_id} {option.gain_pixels:.10f}" for option in options)
        data_lines.append(";")
        data_lines.append("param remaining :=")
        data_lines.extend(f"{option.option_id} {option.remaining_area_pixels:.10f}" for option in options)
        data_lines.append(";")
        data_lines.append("param depth :=")
        data_lines.extend(f"{option.option_id} {option.depth_pixels}" for option in options)
        data_lines.append(";")
        data_lines.append("param min_area :=")
        data_lines.extend(f"{neighbor_id} {minimums[neighbor_id]:.10f}" for neighbor_id in neighbors)
        data_lines.append(";")

        ampl.eval("\n".join(data_lines))
        ampl.option["solver"] = self.solver
        ampl.solve()

        solve_result = str(ampl.get_value("solve_result"))
        if "solved" not in solve_result.lower():
            raise RuntimeError(f"AMPL could not solve the optimization model: {solve_result}")

        selected: dict[int, ExpansionOption] = {}
        for option_id, option in by_id.items():
            if float(ampl.get_value(f"choose[{option_id}]")) > 0.5:
                selected[option.neighbor_id] = option

        return selected, solve_result


def extract_boundary_polygon(detection_result: dict[str, Any]) -> Polygon:
    boundary_data = detection_result.get("buildingBoundary") or {}
    points = boundary_data.get("polygon")
    if not points:
        points = boundary_data.get("usablePolygon")
    if not points:
        raise ValueError("No usable building boundary polygon was returned by detection")

    polygon = points_to_polygon(points)
    if polygon is None:
        raise ValueError("The detected building boundary is not a valid single polygon")
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

        polygon = polygon_only(polygon.intersection(boundary))
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


def resolve_target_room(
    rooms: dict[int, dict[str, Any]],
    target_room: int | str,
) -> int:
    if isinstance(target_room, int):
        if target_room not in rooms:
            raise ValueError(f"Target room id {target_room} does not exist")
        return target_room

    value = str(target_room).strip()
    if value.isdigit():
        room_id = int(value)
        if room_id not in rooms:
            raise ValueError(f"Target room id {room_id} does not exist")
        return room_id

    matches = [
        room_id
        for room_id, data in rooms.items()
        if data["name"].strip().lower() == value.lower()
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(f"More than one room is named '{value}'. Use the room id instead")

    partial_matches = [
        room_id
        for room_id, data in rooms.items()
        if value.lower() in data["name"].strip().lower()
    ]
    if len(partial_matches) == 1:
        return partial_matches[0]

    raise ValueError(f"Could not find a unique target room matching '{value}'")


def points_to_polygon(points: list[dict[str, Any]]) -> Polygon | None:
    if len(points) < 3:
        return None
    polygon = Polygon([(float(point["x"]), float(point["y"])) for point in points])
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    return polygon_only(polygon)


def polygon_only(geometry) -> Polygon | None:
    if geometry is None or geometry.is_empty:
        return None
    if isinstance(geometry, Polygon):
        return geometry
    if isinstance(geometry, MultiPolygon):
        if len(geometry.geoms) == 1:
            return geometry.geoms[0]
        return None
    if isinstance(geometry, GeometryCollection):
        polygons = [part for part in geometry.geoms if isinstance(part, Polygon) and not part.is_empty]
        if len(polygons) == 1:
            return polygons[0]
        if len(polygons) > 1:
            merged = unary_union(polygons)
            if isinstance(merged, Polygon):
                return merged
    return None


def polygon_to_points(polygon: Polygon) -> list[dict[str, float]]:
    coordinates = list(polygon.exterior.coords)
    if len(coordinates) > 1 and coordinates[0] == coordinates[-1]:
        coordinates = coordinates[:-1]
    return [{"x": float(x), "y": float(y)} for x, y in coordinates]


def pixels_per_metre_from_measurement(
    start: tuple[float, float],
    end: tuple[float, float],
    actual_distance_metres: float,
) -> float:
    if actual_distance_metres <= 0:
        raise ValueError("actual_distance_metres must be greater than zero")
    pixel_distance = hypot(end[0] - start[0], end[1] - start[1])
    if pixel_distance <= 0:
        raise ValueError("The measurement points must be different")
    return pixel_distance / actual_distance_metres


def square_metres_to_pixel_area(
    area_square_metres: float,
    pixels_per_metre: float,
) -> float:
    if area_square_metres < 0:
        raise ValueError("area_square_metres cannot be negative")
    if pixels_per_metre <= 0:
        raise ValueError("pixels_per_metre must be greater than zero")
    return area_square_metres * pixels_per_metre * pixels_per_metre
