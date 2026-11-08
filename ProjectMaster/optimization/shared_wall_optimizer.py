from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from functools import lru_cache
from math import isfinite
from typing import Any

from amplpy import AMPL, modules
from shapely.geometry import Polygon, box
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
class SliceNode:
    room_ids: tuple[int, ...]
    axis: str | None = None
    first: "SliceNode | None" = None
    second: "SliceNode | None" = None
    original_cut: float | None = None
    optimized_cut: float | None = None

    @property
    def is_leaf(self) -> bool:
        return self.axis is None

    def to_dict(self) -> dict[str, Any]:
        if self.is_leaf:
            return {"roomId": self.room_ids[0]}
        return {
            "axis": self.axis,
            "roomIds": list(self.room_ids),
            "originalCut": self.original_cut,
            "optimizedCut": self.optimized_cut,
            "first": self.first.to_dict() if self.first else None,
            "second": self.second.to_dict() if self.second else None,
        }


@dataclass
class SharedWallResult:
    boundary: Polygon
    rooms: dict[int, RoomGeometry]
    target_room_id: int
    target_room_name: str
    solve_result: str
    slice_tree: SliceNode | None
    cut_detection_tolerance_pixels: float
    layout_was_rectangularized: bool
    fixtures: list[dict[str, Any]] = field(default_factory=list)
    layout_constraints: dict[str, Any] = field(default_factory=dict)
    solver_details: dict[str, Any] = field(default_factory=dict)

    @property
    def target_original_area_pixels(self) -> float:
        return self.rooms[self.target_room_id].original_area_pixels

    @property
    def target_optimized_area_pixels(self) -> float:
        return self.rooms[self.target_room_id].optimized_area_pixels

    @property
    def target_gain_pixels(self) -> float:
        return self.target_optimized_area_pixels - self.target_original_area_pixels

    @property
    def selected_placements(self) -> dict[int, Any]:
        return {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "optimizer": "coordinated-shared-wall-push",
            "targetRoomId": self.target_room_id,
            "targetRoomName": self.target_room_name,
            "solveResult": self.solve_result,
            "targetOriginalAreaPixels": self.target_original_area_pixels,
            "targetOptimizedAreaPixels": self.target_optimized_area_pixels,
            "targetGainPixels": self.target_gain_pixels,
            "cutDetectionTolerancePixels": self.cut_detection_tolerance_pixels,
            "layoutWasRectangularized": self.layout_was_rectangularized,
            "fixtures": self.fixtures,
            "layoutConstraints": self.layout_constraints,
            "solverDetails": self.solver_details,
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
            "sliceTree": self.slice_tree.to_dict() if self.slice_tree is not None else None,
            "selectedPlacements": [],
            "selectedWallTransfers": [],
            "selectedExpansions": [],
        }


class SharedWallPushOptimizer:
    """Optimize shared cuts subject to room minima and fixture geometry.

    Grid positions are chosen jointly in a linear mixed-integer model. Other
    rooms may remain above minimum when required to retain doors/openings.
    Window replacements come from a calibrated configurable catalogue.
    The old area-only helper remains for reference and is not called.
    """

    def __init__(
        self,
        solver: str = "highs",
        minimum_area_ratio: float = 0.60,
        cut_detection_tolerance_pixels: float = 8.0,
        area_tolerance_pixels: float = 2.0,
        grid_step_pixels: float = 40.0,
        fixture_margin_pixels: float = 5.0,
        fixture_gap_pixels: float = 5.0,
        mapping_tolerance_pixels: float = 30.0,
        alignment_tolerance_pixels: float = 1.0,
        geometry_tolerance_pixels: float = 0.05,
        window_policy: str = "catalog",
        window_catalog_path: str | Path | None = None,
        fixture_overrides: dict[str, Any] | None = None,
        window_resize_penalty: float = 0.005,
        backend: str = "auto",
        time_limit_seconds: float = 60.0,
        mip_relative_gap: float = 0.001,
        max_grid_cells: int = 12000,
        max_invalid_solutions: int = 20,
        fixture_position: str = "center",
        maximum_target_growth: float | None = None,
    ):
        if not 0 < minimum_area_ratio <= 1:
            raise ValueError("minimum_area_ratio must be in the interval (0, 1]")
        if cut_detection_tolerance_pixels < 0:
            raise ValueError("cut_detection_tolerance_pixels cannot be negative")
        if area_tolerance_pixels <= 0:
            raise ValueError("area_tolerance_pixels must be greater than zero")

        self.solver = solver
        self.minimum_area_ratio = float(minimum_area_ratio)
        self.cut_detection_tolerance_pixels = float(
            cut_detection_tolerance_pixels
        )
        self.area_tolerance_pixels = float(area_tolerance_pixels)
        from .push_constraints import positive
        if solver != "highs":
            raise ValueError("Constrained push currently supports HiGHS only")
        if window_policy not in {"catalog", "preserve"}:
            raise ValueError("window_policy must be catalog or preserve")
        if backend not in {"auto", "ampl", "scipy"}:
            raise ValueError("backend must be auto, ampl, or scipy")
        if fixture_position not in {"center","relative"}:
            raise ValueError("fixture_position must be center or relative")
        self.fixture_position = fixture_position
        self.maximum_target_growth = None if maximum_target_growth is None else positive(maximum_target_growth,"maximum_target_growth",True)
        self.grid_step_pixels = positive(grid_step_pixels,"grid_step_pixels")
        self.fixture_margin_pixels = positive(fixture_margin_pixels,"fixture_margin_pixels",True)
        self.fixture_gap_pixels = positive(fixture_gap_pixels,"fixture_gap_pixels",True)
        self.mapping_tolerance_pixels = positive(mapping_tolerance_pixels,"mapping_tolerance_pixels")
        self.alignment_tolerance_pixels = positive(alignment_tolerance_pixels,"alignment_tolerance_pixels",True)
        self.geometry_tolerance_pixels = positive(geometry_tolerance_pixels,"geometry_tolerance_pixels")
        self.time_limit_seconds = positive(time_limit_seconds,"time_limit_seconds")
        self.window_resize_penalty = positive(window_resize_penalty,"window_resize_penalty",True)
        self.mip_relative_gap = positive(mip_relative_gap,"mip_relative_gap",True)
        if int(max_grid_cells) < 1 or int(max_invalid_solutions) < 0:
            raise ValueError("Invalid grid cell limit or retry limit")
        self.max_grid_cells = int(max_grid_cells)
        self.max_invalid_solutions = int(max_invalid_solutions)
        self.window_policy = window_policy
        self.window_catalog_path = Path(window_catalog_path) if window_catalog_path else Path(__file__).with_name("window_catalog.json")
        self.fixture_overrides = fixture_overrides or {}
        self.backend = backend

    def optimize(
        self,
        detection_result: dict[str, Any],
        target_room: int | str,
        minimum_area_pixels: dict[int, float] | None = None,
        minimum_area_square_metres: dict[int, float] | None = None,
        pixels_per_metre: float | None = None,
    ) -> SharedWallResult:
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
        from .push_constraints import solve_push,preserve_zero_growth
        if self.maximum_target_growth==0:
            solution=preserve_zero_growth(self,detection_result,boundary,rooms,target_id,minimums,pixels_per_metre)
            tree=None
            used_cut_tolerance=0.0
        else:
            tree, used_cut_tolerance = self._infer_or_rectangularize_slice_tree(
                rooms=rooms,
                boundary=boundary,
            )
            solution = solve_push(self, detection_result, boundary, rooms, target_id,
                                  minimums, tree, pixels_per_metre)
        optimized_polygons = solution["polygons"]
        def updated_tree(node, key="root"):
            if node.is_leaf:
                return node
            return replace(node, optimized_cut=solution["cuts"][key],
                           first=updated_tree(node.first,key+"L"),
                           second=updated_tree(node.second,key+"R"))
        optimized_tree = updated_tree(tree) if solution["cuts"] is not None else None
        if optimized_tree is None:
            used_cut_tolerance=0.0
        solve_result = solution["details"]["status"] + " (" + solution["details"]["backend"] + ")"
        self._validate_partition(
            boundary=boundary,
            rooms=rooms,
            target_id=target_id,
            minimums=minimums,
            optimized=optimized_polygons,
        )

        room_results = {
            room_id: RoomGeometry(
                room_id=room_id,
                name=data["name"],
                original_polygon=data["polygon"],
                optimized_polygon=optimized_polygons[room_id],
                minimum_area_pixels=minimums[room_id],
            )
            for room_id, data in rooms.items()
        }
        return SharedWallResult(
            boundary=boundary,
            rooms=room_results,
            target_room_id=target_id,
            target_room_name=rooms[target_id]["name"],
            solve_result=solve_result,
            slice_tree=optimized_tree,
            cut_detection_tolerance_pixels=used_cut_tolerance,
            layout_was_rectangularized=(
                used_cut_tolerance > self.cut_detection_tolerance_pixels + 1e-9
            ),
            fixtures=solution["fixtures"],
            layout_constraints=solution["constraints"],
            solver_details=solution["details"],
        )

    def describe_constraints(self, detection_result, pixels_per_metre=None):
        """Inspect automatically associated fixtures without running a solver."""
        from .push_constraints import collect_fixtures, graph_report
        boundary = extract_boundary_polygon(detection_result)
        rooms = extract_room_polygons(detection_result,boundary)
        if self.maximum_target_growth==0:
            from .push_constraints import attach_original_shared_profiles
            fixtures=collect_fixtures(detection_result,rooms,boundary,None,self,pixels_per_metre)
            attach_original_shared_profiles(fixtures,rooms,self)
            report={"fixtures":[fixture.to_dict() for fixture in fixtures],"sharedCuts":[],
                    "roomGeometryPolicy":"preserve-normalized-polygons-exactly"}
        else:
            tree,_ = self._infer_or_rectangularize_slice_tree(rooms,boundary)
            fixtures = collect_fixtures(detection_result,rooms,boundary,tree,self,pixels_per_metre)
            report = graph_report(fixtures,tree)
        report["controls"] = {"fixturePosition":self.fixture_position,
                              "minimumAreaRatio":self.minimum_area_ratio,
                              "maximumTargetGrowth":self.maximum_target_growth}
        return report

    def _infer_or_rectangularize_slice_tree(
        self,
        rooms: dict[int, dict[str, Any]],
        boundary: Polygon,
    ) -> tuple[SliceNode, float]:
        try:
            return (
                self._infer_slice_tree(
                    rooms,
                    tolerance_pixels=self.cut_detection_tolerance_pixels,
                ),
                self.cut_detection_tolerance_pixels,
            )
        except ValueError as original_error:
            minimum_x, minimum_y, maximum_x, maximum_y = boundary.bounds
            maximum_rectangularization_tolerance = max(
                self.cut_detection_tolerance_pixels,
                min(maximum_x - minimum_x, maximum_y - minimum_y) * 0.10,
            )
            if maximum_rectangularization_tolerance <= (
                self.cut_detection_tolerance_pixels + 1e-9
            ):
                raise original_error

            try:
                return (
                    self._infer_slice_tree(
                        rooms,
                        tolerance_pixels=maximum_rectangularization_tolerance,
                    ),
                    float(maximum_rectangularization_tolerance),
                )
            except ValueError:
                raise ValueError(
                    "The normalized layout cannot be converted to a coordinated "
                    "shared-wall partition, even after controlled "
                    "rectangularization. Use --optimizer placement for this "
                    "layout."
                ) from original_error

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

        result: dict[int, float] = {}
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
            if not isfinite(value) or value <= 0:
                raise ValueError(f"Room {room_id} has a non-positive minimum area")
            result[room_id] = float(value)
        return result

    def _infer_slice_tree(
        self,
        rooms: dict[int, dict[str, Any]],
        tolerance_pixels: float | None = None,
    ) -> SliceNode:
        tolerance = (
            self.cut_detection_tolerance_pixels
            if tolerance_pixels is None
            else float(tolerance_pixels)
        )

        @lru_cache(maxsize=None)
        def build(room_ids: tuple[int, ...]) -> SliceNode:
            room_ids = tuple(sorted(room_ids))
            if len(room_ids) == 1:
                return SliceNode(room_ids=room_ids)

            options: list[tuple[tuple[float, int, float], SliceNode]] = []
            for axis in ("x", "y"):
                centroid_coordinate = (
                    (lambda room_id: rooms[room_id]["polygon"].centroid.x)
                    if axis == "x"
                    else (lambda room_id: rooms[room_id]["polygon"].centroid.y)
                )
                ordered = sorted(room_ids, key=centroid_coordinate)
                minimum_index = 0 if axis == "x" else 1
                maximum_index = 2 if axis == "x" else 3

                for split_index in range(1, len(ordered)):
                    first_ids = tuple(sorted(ordered[:split_index]))
                    second_ids = tuple(sorted(ordered[split_index:]))
                    first_maximum = max(
                        rooms[room_id]["polygon"].bounds[maximum_index]
                        for room_id in first_ids
                    )
                    second_minimum = min(
                        rooms[room_id]["polygon"].bounds[minimum_index]
                        for room_id in second_ids
                    )
                    separation_error = first_maximum - second_minimum
                    if separation_error > tolerance:
                        continue

                    try:
                        first_node = build(first_ids)
                        second_node = build(second_ids)
                    except ValueError:
                        continue

                    cut = (first_maximum + second_minimum) / 2.0
                    balance = abs(len(first_ids) - len(second_ids))
                    score = (abs(separation_error), balance, cut)
                    options.append(
                        (
                            score,
                            SliceNode(
                                room_ids=room_ids,
                                axis=axis,
                                first=first_node,
                                second=second_node,
                                original_cut=float(cut),
                            ),
                        )
                    )

            if not options:
                raise ValueError(
                    "The normalized layout is not a slicing floor plan. "
                    "The coordinated push optimizer requires recursively "
                    "separable horizontal or vertical room groups."
                )
            return min(options, key=lambda item: item[0])[1]

        return build(tuple(sorted(rooms)))

    def _solve_areas_with_ampl(
        self,
        rooms: dict[int, dict[str, Any]],
        boundary: Polygon,
        target_id: int,
        minimums: dict[int, float],
    ) -> tuple[dict[int, float], str]:
        try:
            ampl = AMPL(modules.load())
        except Exception:
            ampl = AMPL()

        ampl.eval(
            """
            set R;
            param target_room symbolic in R;
            param minimum_area {R} > 0;
            param building_area > 0;

            var room_area {r in R} >= minimum_area[r];

            subject to CompletePartition:
                sum {r in R} room_area[r] = building_area;

            maximize SelectedRoomArea:
                room_area[target_room];
            """
        )
        room_ids = sorted(rooms)
        data = [
            "data;",
            "set R := " + " ".join(str(room_id) for room_id in room_ids) + ";",
            f"param target_room := {target_id};",
            f"param building_area := {float(boundary.area):.10f};",
            "param minimum_area :=",
        ]
        data.extend(
            f"{room_id} {minimums[room_id]:.10f}" for room_id in room_ids
        )
        data.append(";")
        ampl.eval("\n".join(data))
        ampl.option["solver"] = self.solver
        ampl.solve()
        solve_result = str(ampl.get_value("solve_result"))
        if "solved" not in solve_result.lower():
            raise RuntimeError(
                f"AMPL could not solve the shared-wall area model: {solve_result}"
            )

        return (
            {
                room_id: float(ampl.get_value(f"room_area[{room_id}]"))
                for room_id in room_ids
            },
            solve_result,
        )

    def _realize_tree(
        self,
        tree: SliceNode,
        boundary: Polygon,
        desired_areas: dict[int, float],
    ) -> tuple[dict[int, Polygon], SliceNode]:
        result: dict[int, Polygon] = {}

        def subtree_area(node: SliceNode) -> float:
            return sum(desired_areas[room_id] for room_id in node.room_ids)

        def assign(node: SliceNode, region: Polygon) -> SliceNode:
            if node.is_leaf:
                result[node.room_ids[0]] = region
                return node

            first_region, second_region, optimized_cut = self._cut_region(
                region=region,
                axis=node.axis,
                desired_first_area=subtree_area(node.first),
            )
            optimized_first = assign(node.first, first_region)
            optimized_second = assign(node.second, second_region)
            return SliceNode(
                room_ids=node.room_ids,
                axis=node.axis,
                first=optimized_first,
                second=optimized_second,
                original_cut=node.original_cut,
                optimized_cut=optimized_cut,
            )

        optimized_tree = assign(tree, boundary)
        return result, optimized_tree

    def _cut_region(
        self,
        region: Polygon,
        axis: str,
        desired_first_area: float,
    ) -> tuple[Polygon, Polygon, float]:
        minimum_x, minimum_y, maximum_x, maximum_y = region.bounds
        lower = minimum_x if axis == "x" else minimum_y
        upper = maximum_x if axis == "x" else maximum_y
        padding = max(maximum_x - minimum_x, maximum_y - minimum_y) + 100.0

        for _ in range(80):
            cut = (lower + upper) / 2.0
            first_half = (
                box(
                    minimum_x - padding,
                    minimum_y - padding,
                    cut,
                    maximum_y + padding,
                )
                if axis == "x"
                else box(
                    minimum_x - padding,
                    minimum_y - padding,
                    maximum_x + padding,
                    cut,
                )
            )
            first_area = region.intersection(first_half).area
            if first_area < desired_first_area:
                lower = cut
            else:
                upper = cut

        cut = (lower + upper) / 2.0
        first_half = (
            box(
                minimum_x - padding,
                minimum_y - padding,
                cut,
                maximum_y + padding,
            )
            if axis == "x"
            else box(
                minimum_x - padding,
                minimum_y - padding,
                maximum_x + padding,
                cut,
            )
        )
        first = polygon_only(region.intersection(first_half))
        second = polygon_only(region.difference(first_half))
        if first is None or second is None:
            raise RuntimeError(
                f"The {axis}-axis shared-wall cut at {cut:.2f}px made a "
                "disconnected room group"
            )
        return first, second, float(cut)

    def _validate_partition(
        self,
        boundary: Polygon,
        rooms: dict[int, dict[str, Any]],
        target_id: int,
        minimums: dict[int, float],
        optimized: dict[int, Polygon],
    ) -> None:
        if set(optimized) != set(rooms):
            raise RuntimeError("Not every room was produced by the slicing tree")

        for room_id, polygon in optimized.items():
            if not polygon.is_valid or polygon.interiors:
                raise RuntimeError(f"Room {room_id} has invalid optimized geometry")
            if polygon.area + self.area_tolerance_pixels < minimums[room_id]:
                raise RuntimeError(
                    f"Room {room_id} is below its minimum area by "
                    f"{minimums[room_id] - polygon.area:.2f}px²"
                )

        room_ids = sorted(optimized)
        for index, first_id in enumerate(room_ids):
            for second_id in room_ids[index + 1 :]:
                overlap = optimized[first_id].intersection(
                    optimized[second_id]
                ).area
                if overlap > GEOMETRY_TOLERANCE_PIXELS:
                    raise RuntimeError(
                        f"Rooms {first_id} and {second_id} overlap by "
                        f"{overlap:.2f}px²"
                    )

        coverage = unary_union(list(optimized.values()))
        changed_area = coverage.symmetric_difference(boundary).area
        if changed_area > self.area_tolerance_pixels:
            raise RuntimeError(
                f"The coordinated partition changed building coverage by "
                f"{changed_area:.2f}px²"
            )
        if optimized[target_id].area + self.area_tolerance_pixels < (
            rooms[target_id]["polygon"].area
        ):
            raise RuntimeError("The selected room became smaller than its original area")
