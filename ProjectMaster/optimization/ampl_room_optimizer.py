from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from typing import Any, Iterable

from amplpy import AMPL, modules
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon
from shapely.ops import unary_union


GEOMETRY_TOLERANCE_PIXELS = 1.0


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
    """One discrete movement of a shared wall."""

    option_id: int
    edge_id: int
    donor_id: int | None
    receiver_id: int | None
    depth_pixels: int
    transfer_polygon: Polygon | None
    transfer_area_pixels: float

    @property
    def is_noop(self) -> bool:
        return self.transfer_polygon is None or self.transfer_area_pixels <= 0.0


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
        transfers = [
            {
                "edgeId": option.edge_id,
                "donorRoomId": option.donor_id,
                "receiverRoomId": option.receiver_id,
                "depthPixels": option.depth_pixels,
                "areaPixels": option.transfer_area_pixels,
            }
            for option in sorted(
                self.selected_options.values(),
                key=lambda value: (value.edge_id, value.option_id),
            )
        ]

        return {
            "targetRoomId": self.target_room_id,
            "targetRoomName": self.target_room_name,
            "solveResult": self.solve_result,
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
            "selectedWallTransfers": transfers,
            # Keep the old key while callers migrate to selectedWallTransfers.
            "selectedExpansions": transfers,
        }


class AmplRoomOptimizer:
    """Globally optimize a normalized room partition.

    Choices are created for every shared wall. AMPL balances all room areas
    simultaneously, so a distant room can give space to an intermediate room
    while that room gives space to the target.
    """

    def __init__(
        self,
        solver: str = "highs",
        expansion_step_pixels: int = 5,
        max_expansion_pixels: int = 250,
        minimum_area_ratio: float = 0.60,
        minimum_shared_wall_pixels: float = 8.0,
        maximum_depth_to_wall_ratio: float = 1.0,
        max_invalid_solutions: int = 100,
    ):
        if expansion_step_pixels <= 0:
            raise ValueError("expansion_step_pixels must be greater than zero")
        if max_expansion_pixels <= 0:
            raise ValueError("max_expansion_pixels must be greater than zero")
        if not 0 < minimum_area_ratio <= 1:
            raise ValueError("minimum_area_ratio must be in the interval (0, 1]")
        if max_invalid_solutions < 0:
            raise ValueError("max_invalid_solutions cannot be negative")
        if maximum_depth_to_wall_ratio <= 0:
            raise ValueError("maximum_depth_to_wall_ratio must be greater than zero")

        self.solver = solver
        self.expansion_step_pixels = int(expansion_step_pixels)
        self.max_expansion_pixels = int(max_expansion_pixels)
        self.minimum_area_ratio = float(minimum_area_ratio)
        self.minimum_shared_wall_pixels = float(minimum_shared_wall_pixels)
        self.maximum_depth_to_wall_ratio = float(maximum_depth_to_wall_ratio)
        self.max_invalid_solutions = int(max_invalid_solutions)

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
        self._validate_initial_layout(detected_rooms, minimums)

        options = self._create_options(detected_rooms, target_id)
        if not options:
            return self._unchanged_result(
                boundary,
                detected_rooms,
                target_id,
                minimums,
                "no-shared-wall-transfer-options",
            )

        forbidden_selections: list[set[int]] = []
        last_invalid_reason = ""

        for _ in range(self.max_invalid_solutions + 1):
            selected_all, solve_result = self._solve_with_ampl(
                options=options,
                rooms=detected_rooms,
                target_id=target_id,
                minimums=minimums,
                forbidden_selections=forbidden_selections,
            )
            selected_transfers = [
                option for option in selected_all if not option.is_noop
            ]
            optimized_polygons, invalid_reason = self._apply_and_validate_transfers(
                rooms=detected_rooms,
                boundary=boundary,
                minimums=minimums,
                selected=selected_transfers,
            )

            if optimized_polygons is not None:
                room_results = {
                    room_id: RoomGeometry(
                        room_id=room_id,
                        name=data["name"],
                        original_polygon=data["polygon"],
                        optimized_polygon=optimized_polygons[room_id],
                        minimum_area_pixels=minimums[room_id],
                    )
                    for room_id, data in detected_rooms.items()
                }
                return OptimizationResult(
                    boundary=boundary,
                    rooms=room_results,
                    target_room_id=target_id,
                    target_room_name=detected_rooms[target_id]["name"],
                    selected_options={
                        option.edge_id: option for option in selected_transfers
                    },
                    solve_result=solve_result,
                )

            last_invalid_reason = invalid_reason or "invalid geometry"
            chosen_ids = {option.option_id for option in selected_all}
            if not chosen_ids:
                break
            forbidden_selections.append(chosen_ids)

        raise RuntimeError(
            "AMPL found area-feasible solutions, but none produced a valid "
            f"connected partition after {len(forbidden_selections)} retries. "
            f"Last reason: {last_invalid_reason}"
        )

    def _unchanged_result(
        self,
        boundary: Polygon,
        rooms: dict[int, dict[str, Any]],
        target_id: int,
        minimums: dict[int, float],
        solve_result: str,
    ) -> OptimizationResult:
        room_results = {
            room_id: RoomGeometry(
                room_id=room_id,
                name=data["name"],
                original_polygon=data["polygon"],
                optimized_polygon=data["polygon"],
                minimum_area_pixels=minimums[room_id],
            )
            for room_id, data in rooms.items()
        }
        return OptimizationResult(
            boundary=boundary,
            rooms=room_results,
            target_room_id=target_id,
            target_room_name=rooms[target_id]["name"],
            selected_options={},
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
        if minimum_area_square_metres and (
            pixels_per_metre is None or pixels_per_metre <= 0
        ):
            raise ValueError(
                "pixels_per_metre must be provided when minimum areas are given in square metres"
            )

        minimums: dict[int, float] = {}
        for room_id, data in rooms.items():
            original_area = float(data["polygon"].area)
            value = (
                original_area
                if room_id == target_id
                else original_area * self.minimum_area_ratio
            )

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
        minimums: dict[int, float],
    ) -> None:
        room_ids = sorted(rooms)
        for room_id in room_ids:
            current_area = float(rooms[room_id]["polygon"].area)
            if current_area + 1e-6 < minimums[room_id]:
                raise ValueError(
                    f"Room {room_id} starts below its minimum area: "
                    f"current={current_area:.2f}px², minimum={minimums[room_id]:.2f}px²"
                )

        for first_index, first_id in enumerate(room_ids):
            first = rooms[first_id]["polygon"]
            for second_id in room_ids[first_index + 1 :]:
                second = rooms[second_id]["polygon"]
                overlap = first.intersection(second).area
                if overlap > GEOMETRY_TOLERANCE_PIXELS:
                    raise ValueError(
                        f"Rooms {first_id} and {second_id} overlap by "
                        f"{overlap:.2f}px² before optimization"
                    )

    def _create_options(
        self,
        rooms: dict[int, dict[str, Any]],
        target_id: int,
    ) -> list[ExpansionOption]:
        """Create discrete moves for every shared wall, not only the target."""

        room_ids = sorted(rooms)
        all_options: list[ExpansionOption] = []
        next_option_id = 1
        next_edge_id = 1

        for index, first_id in enumerate(room_ids):
            for second_id in room_ids[index + 1 :]:
                first = rooms[first_id]["polygon"]
                second = rooms[second_id]["polygon"]
                shared_boundary = first.boundary.intersection(second.boundary)
                shared_length = float(shared_boundary.length)

                if shared_length < self.minimum_shared_wall_pixels:
                    continue

                edge_options: list[ExpansionOption] = []
                for receiver_id, donor_id in (
                    (first_id, second_id),
                    (second_id, first_id),
                ):
                    if donor_id == target_id:
                        continue

                    receiver = rooms[receiver_id]["polygon"]
                    donor = rooms[donor_id]["polygon"]
                    last_area = 0.0

                    for depth in range(
                        self.expansion_step_pixels,
                        self.max_expansion_pixels + self.expansion_step_pixels,
                        self.expansion_step_pixels,
                    ):
                        # A wall should not move farther than its own useful
                        # length. Without this guard, maximizing area creates
                        # long, narrow fingers through short door-sized walls.
                        if depth > shared_length * self.maximum_depth_to_wall_ratio:
                            break
                        transfer = self._make_transfer_polygon(
                            receiver=receiver,
                            donor=donor,
                            shared_boundary=shared_boundary,
                            depth=depth,
                        )
                        if transfer is None:
                            continue

                        area = float(transfer.area)
                        if area <= last_area + 0.5:
                            continue

                        remaining = polygon_only(donor.difference(transfer))
                        grown = polygon_only(receiver.union(transfer))
                        if remaining is None or grown is None:
                            continue
                        if remaining.area <= GEOMETRY_TOLERANCE_PIXELS:
                            continue
                        if remaining.interiors or grown.interiors:
                            continue

                        edge_options.append(
                            ExpansionOption(
                                option_id=next_option_id,
                                edge_id=next_edge_id,
                                donor_id=donor_id,
                                receiver_id=receiver_id,
                                depth_pixels=depth,
                                transfer_polygon=transfer,
                                transfer_area_pixels=area,
                            )
                        )
                        next_option_id += 1
                        last_area = area

                if not edge_options:
                    continue

                all_options.append(
                    ExpansionOption(
                        option_id=next_option_id,
                        edge_id=next_edge_id,
                        donor_id=None,
                        receiver_id=None,
                        depth_pixels=0,
                        transfer_polygon=None,
                        transfer_area_pixels=0.0,
                    )
                )
                next_option_id += 1
                all_options.extend(edge_options)
                next_edge_id += 1

        return all_options

    @staticmethod
    def _make_transfer_polygon(
        receiver: Polygon,
        donor: Polygon,
        shared_boundary,
        depth: int,
    ) -> Polygon | None:
        wall_corridor = shared_boundary.buffer(
            float(depth) + 0.5,
            cap_style=2,
            join_style=2,
        )
        expanded_receiver = receiver.buffer(float(depth), join_style=2)
        transfer = polygon_only(
            donor.intersection(expanded_receiver).intersection(wall_corridor)
        )
        if transfer is None or transfer.area <= 0.5:
            return None
        return transfer

    def _solve_with_ampl(
        self,
        options: list[ExpansionOption],
        rooms: dict[int, dict[str, Any]],
        target_id: int,
        minimums: dict[int, float],
        forbidden_selections: list[set[int]],
    ) -> tuple[list[ExpansionOption], str]:
        room_ids = sorted(rooms)
        edge_ids = sorted({option.edge_id for option in options})
        by_id = {option.option_id: option for option in options}

        try:
            ampl = AMPL(modules.load())
        except Exception:
            ampl = AMPL()

        ampl.eval(
            """
            set R;
            set E;
            set O;
            param edge {O} integer;
            param donor {O} integer default 0;
            param receiver {O} integer default 0;
            param amount {O} >= 0;
            param depth {O} >= 0;
            param original_area {R} >= 0;
            param min_area {R} >= 0;
            param target_room integer;

            var choose {O} binary;
            var final_area {R} >= 0;

            subject to ChooseOneOptionPerWall {e in E}:
                sum {o in O: edge[o] = e} choose[o] = 1;

            subject to AreaBalance {r in R}:
                final_area[r] = original_area[r]
                    + sum {o in O: receiver[o] = r} amount[o] * choose[o]
                    - sum {o in O: donor[o] = r} amount[o] * choose[o];

            subject to KeepEveryRoom {r in R}:
                final_area[r] >= min_area[r];

            subject to AtMostOneOutgoingWall {r in R}:
                sum {o in O: donor[o] = r and amount[o] > 0} choose[o] <= 1;

            maximize TargetRoomArea:
                final_area[target_room]
                - 0.000000001 * sum {o in O} amount[o] * choose[o];
            """
        )

        data_lines = [
            "data;",
            "set R := " + " ".join(str(value) for value in room_ids) + ";",
            "set E := " + " ".join(str(value) for value in edge_ids) + ";",
            "set O := " + " ".join(str(option.option_id) for option in options) + ";",
            f"param target_room := {target_id};",
        ]

        for parameter, values in (
            ("edge", ((o.option_id, o.edge_id) for o in options)),
            ("donor", ((o.option_id, o.donor_id or 0) for o in options)),
            ("receiver", ((o.option_id, o.receiver_id or 0) for o in options)),
        ):
            data_lines.append(f"param {parameter} :=")
            data_lines.extend(f"{key} {int(value)}" for key, value in values)
            data_lines.append(";")

        for parameter, values in (
            ("amount", ((o.option_id, o.transfer_area_pixels) for o in options)),
            ("depth", ((o.option_id, o.depth_pixels) for o in options)),
            (
                "original_area",
                ((room_id, rooms[room_id]["polygon"].area) for room_id in room_ids),
            ),
            ("min_area", ((room_id, minimums[room_id]) for room_id in room_ids)),
        ):
            data_lines.append(f"param {parameter} :=")
            data_lines.extend(f"{key} {float(value):.10f}" for key, value in values)
            data_lines.append(";")

        ampl.eval("\n".join(data_lines))

        for cut_index, selection in enumerate(forbidden_selections, start=1):
            terms = " + ".join(
                f"choose[{option_id}]" for option_id in sorted(selection)
            )
            ampl.eval(
                f"subject to InvalidGeometryCut{cut_index}: "
                f"{terms} <= {len(selection) - 1};"
            )

        ampl.option["solver"] = self.solver
        ampl.solve()

        solve_result = str(ampl.get_value("solve_result"))
        if "solved" not in solve_result.lower():
            raise RuntimeError(
                f"AMPL could not solve the global optimization model: {solve_result}"
            )

        selected = [
            option
            for option_id, option in by_id.items()
            if float(ampl.get_value(f"choose[{option_id}]")) > 0.5
        ]
        return selected, solve_result

    def _apply_and_validate_transfers(
        self,
        rooms: dict[int, dict[str, Any]],
        boundary: Polygon,
        minimums: dict[int, float],
        selected: list[ExpansionOption],
    ) -> tuple[dict[int, Polygon] | None, str | None]:
        incoming: dict[int, list[Polygon]] = {room_id: [] for room_id in rooms}
        outgoing: dict[int, list[Polygon]] = {room_id: [] for room_id in rooms}

        for option in selected:
            if (
                option.transfer_polygon is None
                or option.donor_id is None
                or option.receiver_id is None
            ):
                continue
            outgoing[option.donor_id].append(option.transfer_polygon)
            incoming[option.receiver_id].append(option.transfer_polygon)

        optimized: dict[int, Polygon] = {}
        for room_id, data in rooms.items():
            geometry = data["polygon"]
            if outgoing[room_id]:
                geometry = geometry.difference(unary_union(outgoing[room_id]))
            if incoming[room_id]:
                geometry = unary_union([geometry, *incoming[room_id]])

            polygon = polygon_only(geometry)
            if polygon is None:
                return None, f"room {room_id} became disconnected or empty"
            if polygon.interiors:
                return None, f"room {room_id} would contain an interior hole"
            if polygon.area + 1e-6 < minimums[room_id]:
                return (
                    None,
                    f"room {room_id} fell below its minimum area after reconstruction",
                )
            if polygon.difference(boundary).area > GEOMETRY_TOLERANCE_PIXELS:
                return None, f"room {room_id} moved outside the building boundary"

            optimized[room_id] = polygon

        room_ids = sorted(optimized)
        for index, first_id in enumerate(room_ids):
            for second_id in room_ids[index + 1 :]:
                overlap = optimized[first_id].intersection(optimized[second_id]).area
                if overlap > GEOMETRY_TOLERANCE_PIXELS:
                    return (
                        None,
                        f"rooms {first_id} and {second_id} overlap by {overlap:.2f}px²",
                    )

        original_union = unary_union([data["polygon"] for data in rooms.values()])
        optimized_union = unary_union(list(optimized.values()))
        changed_coverage = original_union.symmetric_difference(optimized_union).area
        if changed_coverage > GEOMETRY_TOLERANCE_PIXELS:
            return (
                None,
                f"partition coverage changed by {changed_coverage:.2f}px²",
            )

        return optimized, None


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
        polygon = points_to_polygon(room.get("polygon") or [], room.get("holes") or [])
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


def points_to_polygon(
    points: list[dict[str, Any]],
    holes: Iterable[list[dict[str, Any]]] | None = None,
) -> Polygon | None:
    if len(points) < 3:
        return None
    shell = [(float(point["x"]), float(point["y"])) for point in points]
    hole_coordinates = [
        [(float(point["x"]), float(point["y"])) for point in ring]
        for ring in (holes or [])
        if len(ring) >= 3
    ]
    polygon = Polygon(shell, hole_coordinates)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    return polygon_only(polygon)


def polygon_only(geometry) -> Polygon | None:
    if geometry is None or geometry.is_empty:
        return None
    if isinstance(geometry, Polygon):
        return geometry
    if isinstance(geometry, MultiPolygon):
        nonempty = [part for part in geometry.geoms if not part.is_empty]
        if len(nonempty) == 1:
            return nonempty[0]
        return None
    if isinstance(geometry, GeometryCollection):
        polygons = [
            part for part in geometry.geoms if isinstance(part, Polygon) and not part.is_empty
        ]
        if len(polygons) == 1:
            return polygons[0]
        if len(polygons) > 1:
            merged = unary_union(polygons)
            if isinstance(merged, Polygon):
                return merged
    return None


def polygon_to_points(polygon: Polygon) -> list[dict[str, float]]:
    return coordinates_to_points(list(polygon.exterior.coords))


def polygon_holes_to_points(polygon: Polygon) -> list[list[dict[str, float]]]:
    return [coordinates_to_points(list(ring.coords)) for ring in polygon.interiors]


def coordinates_to_points(coordinates) -> list[dict[str, float]]:
    coordinates = list(coordinates)
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