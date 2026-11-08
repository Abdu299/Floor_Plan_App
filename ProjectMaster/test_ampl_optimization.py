from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from optimization.ampl_room_optimizer import AmplRoomOptimizer
from optimization.global_placement_optimizer import GlobalPlacementOptimizer
from optimization.room_partition import RoomPartitionBuilder
from optimization.shared_wall_optimizer import SharedWallPushOptimizer
from optimization.ampl_room_optimizer import extract_boundary_polygon, extract_room_polygons, resolve_target_room


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--target-room", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("optimization_test"))
    parser.add_argument(
        "--optimizer",
        choices=("push", "placement", "wall"),
        default="push",
        help=(
            "push moves shared walls subject to fixtures and minimum room areas; "
            "placement preserves room shapes; wall uses the older strip-transfer model"
        ),
    )
    parser.add_argument("--min-ratio", type=float, default=0.60)
    parser.add_argument("--step", type=int, default=5)
    parser.add_argument("--max-expansion", type=int, default=250)
    parser.add_argument("--placement-step", type=int, default=20)
    parser.add_argument("--max-movement", type=int, default=120)
    parser.add_argument("--scale-levels", type=int, default=5)
    parser.add_argument("--partition-gap", type=float)
    parser.add_argument("--pixels-per-metre", type=float)
    parser.add_argument("--min-area-m2", action="append", default=[])
    parser.add_argument("--detection-conf", type=float, default=0.4)
    parser.add_argument("--room-conf", type=float, default=0.4)
    parser.add_argument("--object-conf", type=float, default=0.3)
    parser.add_argument("--detections-json", type=Path, help="Reuse saved detection JSON and skip model loading")
    parser.add_argument("--constraints-only", action="store_true", help="For push: save constraints overlay/JSON without solving")
    parser.add_argument("--push-step", type=float, default=40.0, help="Maximum grid spacing in image pixels; smaller is finer/slower")
    parser.add_argument("--fixture-margin", type=float, default=5.0, help="Required wall length beyond each end of a fixture, pixels")
    parser.add_argument("--fixture-gap", type=float, default=5.0)
    parser.add_argument("--fixture-overrides", type=Path, help="JSON mapping door:ID/opening:ID/window:ID to overrides")
    parser.add_argument("--fixture-map-tolerance", type=float, default=30.0)
    parser.add_argument("--window-policy", choices=("catalog","preserve"), default="catalog")
    parser.add_argument("--window-catalog", type=Path)
    parser.add_argument("--window-resize-penalty", type=float, default=0.005, help="Area-fraction cost for replacing one preferred window with the smallest option")
    parser.add_argument("--push-backend", choices=("auto","ampl","scipy"), default="auto")
    parser.add_argument("--push-time-limit", type=float, default=180.0)
    parser.add_argument("--push-mip-gap", type=float, default=0.001)
    parser.add_argument("--push-max-cells", type=int, default=12000)
    parser.add_argument("--fixture-position",choices=("center","relative"),default="center",help="Center fixtures within their available host walls, or preserve original fractional positions")
    parser.add_argument("--max-target-growth",type=float,help="Cap target area growth, e.g. 0.20 means at most +20%%; other constraints still apply")
    return parser.parse_args()


def parse_min_area_values(values: list[str]) -> dict[int, float]:
    result: dict[int, float] = {}

    for value in values:
        if "=" not in value:
            raise ValueError("--min-area-m2 must use ROOM_ID=AREA, for example 2=7.5")

        room_id_text, area_text = value.split("=", 1)
        room_id = int(room_id_text.strip())
        area = float(area_text.strip())

        if area <= 0:
            raise ValueError("Minimum room area must be greater than zero")

        result[room_id] = area

    return result


def polygon_points(points):
    array = np.array(
        [
            [
                int(round(point["x"])),
                int(round(point["y"])),
            ]
            for point in points
        ],
        dtype=np.int32,
    )

    return array.reshape((-1, 1, 2))


def shapely_ring_points(ring):
    coordinates = list(ring.coords)
    return np.array(
        [
            [
                int(round(x)),
                int(round(y)),
            ]
            for x, y in coordinates
        ],
        dtype=np.int32,
    ).reshape((-1, 1, 2))


def room_color(room_id: int):
    palette = [
        (214, 239, 255),
        (219, 255, 221),
        (255, 229, 214),
        (237, 219, 255),
        (255, 245, 204),
        (219, 244, 245),
        (235, 235, 235),
        (229, 219, 255),
    ]

    return palette[(room_id - 1) % len(palette)]


def boundary_points(result):
    boundary = result.get("buildingBoundary") or {}
    points = boundary.get("polygon")

    if not points:
        points = boundary.get("usablePolygon")

    if not points:
        raise ValueError("No usable building boundary was returned")

    return points


def draw_detected_layout(original, result, target_room_id):
    output = original.copy()
    boundary = polygon_points(boundary_points(result))

    cv2.polylines(
        output,
        [boundary],
        True,
        (0, 0, 0),
        5,
        cv2.LINE_AA,
    )

    for room in result.get("rooms", []):
        polygon = polygon_points(room["polygon"])
        room_id = int(room["id"])
        color = (0, 0, 255) if room_id == target_room_id else (0, 150, 0)

        cv2.polylines(
            output,
            [polygon],
            True,
            color,
            3,
            cv2.LINE_AA,
        )

        centroid = room.get("centroid") or {}
        x = int(round(float(centroid.get("x", 0))))
        y = int(round(float(centroid.get("y", 0))))
        label = f"{room_id}. {room.get('name') or 'Room'}"

        cv2.putText(
            output,
            label,
            (x - 40, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            2,
            cv2.LINE_AA,
        )

    return output


def draw_partition_layout(shape, result, target_room_id):
    height, width = shape[:2]
    output = np.full((height, width, 3), 255, dtype=np.uint8)
    boundary = polygon_points(boundary_points(result))

    cv2.fillPoly(
        output,
        [boundary],
        (245, 245, 245),
        cv2.LINE_AA,
    )

    for room in result.get("rooms", []):
        polygon = polygon_points(room["polygon"])
        room_id = int(room["id"])
        color = room_color(room_id)

        cv2.fillPoly(
            output,
            [polygon],
            color,
            cv2.LINE_AA,
        )

        border = (0, 0, 255) if room_id == target_room_id else (40, 40, 40)
        thickness = 4 if room_id == target_room_id else 2

        cv2.polylines(
            output,
            [polygon],
            True,
            border,
            thickness,
            cv2.LINE_AA,
        )

        centroid = room.get("centroid") or {}
        x = int(round(float(centroid.get("x", 0))))
        y = int(round(float(centroid.get("y", 0))))
        label = f"{room_id}. {room.get('name') or 'Room'}"

        cv2.putText(
            output,
            label,
            (x - 45, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (20, 20, 20),
            2,
            cv2.LINE_AA,
        )

    cv2.polylines(
        output,
        [boundary],
        True,
        (0, 0, 0),
        5,
        cv2.LINE_AA,
    )

    return output


def draw_optimized_layout(shape, optimization_result):
    height, width = shape[:2]
    output = np.full((height, width, 3), 255, dtype=np.uint8)
    boundary = shapely_ring_points(optimization_result.boundary.exterior)

    cv2.fillPoly(
        output,
        [boundary],
        (245, 245, 245),
        cv2.LINE_AA,
    )

    for room_id in sorted(optimization_result.rooms):
        room = optimization_result.rooms[room_id]
        polygon = shapely_ring_points(room.optimized_polygon.exterior)
        color = room_color(room_id)

        room_mask = np.zeros((height, width), dtype=np.uint8)
        cv2.fillPoly(
            room_mask,
            [polygon],
            255,
            cv2.LINE_AA,
        )
        hole_polygons = [
            shapely_ring_points(ring)
            for ring in room.optimized_polygon.interiors
        ]
        if hole_polygons:
            cv2.fillPoly(room_mask, hole_polygons, 0, cv2.LINE_AA)
        output[room_mask > 0] = color

        border = (
            (0, 0, 255)
            if room_id == optimization_result.target_room_id
            else (40, 40, 40)
        )

        thickness = 4 if room_id == optimization_result.target_room_id else 2

        cv2.polylines(
            output,
            [polygon],
            True,
            border,
            thickness,
            cv2.LINE_AA,
        )
        if hole_polygons:
            cv2.polylines(
                output,
                hole_polygons,
                True,
                border,
                thickness,
                cv2.LINE_AA,
            )

        point = room.optimized_polygon.representative_point()
        label = f"{room.room_id}. {room.name}"

        cv2.putText(
            output,
            label,
            (
                int(round(point.x)) - 45,
                int(round(point.y)),
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (20, 20, 20),
            2,
            cv2.LINE_AA,
        )

    cv2.polylines(
        output,
        [boundary],
        True,
        (0, 0, 0),
        5,
        cv2.LINE_AA,
    )

    return output


def draw_fixture_lines(image, fixtures, original=False):
    colors = {"door":(0,0,210),"opening":(0,140,255),"window":(220,70,0)}
    for fixture in fixtures:
        axis = fixture["axis"]
        normal = fixture["wallCoordinate"]
        start = fixture["originalStartPixels"] if original else fixture["optimizedStartPixels"]
        width = fixture["originalWidthPixels"] if original else fixture["widthPixels"]
        point_a = (start,normal) if axis=="x" else (normal,start)
        point_b = (start+width,normal) if axis=="x" else (normal,start+width)
        path = [point_a,point_b]
        if not original and fixture.get("line"):
            path = [(point["x"],point["y"]) for point in fixture["line"]]
        elif original and fixture.get("hostBoundaryProfile"):
            from shapely.geometry import LineString,box
            from optimization.push_constraints import line_components
            source = LineString([(point["x"],point["y"]) for point in fixture["hostBoundaryProfile"]])
            bounds = source.bounds
            clip = box(start,bounds[1]-1,start+width,bounds[3]+1) if axis=="x" else box(bounds[0]-1,start,bounds[2]+1,start+width)
            along = 0 if axis=="x" else 1
            for piece in line_components(source.intersection(clip)):
                if piece.bounds[along]<=start+1e-5 and piece.bounds[along+2]>=start+width-1e-5:
                    path = list(piece.coords)
                    if path[0][along]>path[-1][along]: path.reverse()
                    break
        point_a,point_b = path[0],path[-1]
        a,b = [(int(round(x)),int(round(y))) for x,y in (point_a,point_b)]
        color = colors[fixture["kind"]]
        margin = fixture.get("marginEachEndPixels",0)
        padded_a = (int(round(start-margin)),int(round(normal))) if axis=="x" else (int(round(normal)),int(round(start-margin)))
        padded_b = (int(round(start+width+margin)),int(round(normal))) if axis=="x" else (int(round(normal)),int(round(start+width+margin)))
        cv2.line(image,padded_a,padded_b,(140,140,140),2,cv2.LINE_AA)
        path_array = np.rint(np.asarray(path,dtype=float)).astype(np.int32).reshape((-1,1,2))
        cv2.polylines(image,[path_array],False,(255,255,255),10,cv2.LINE_AA)
        cv2.polylines(image,[path_array],False,color,5,cv2.LINE_AA)
        for x,y in (a,b):
            cv2.circle(image,(x,y),4,color,-1,cv2.LINE_AA)
        label = f"{fixture['id']} {width:.1f}px"
        if not original and fixture.get("selectedSize")!="original":
            label += f" {fixture.get('selectedSize','')}"
        (text_width,text_height),_ = cv2.getTextSize(label,cv2.FONT_HERSHEY_SIMPLEX,.45,1)
        label_x = max(2,min(a[0]+5,image.shape[1]-text_width-3))
        label_y = max(text_height+3,min(a[1]-8,image.shape[0]-3))
        cv2.putText(image,label,(label_x,label_y),cv2.FONT_HERSHEY_SIMPLEX,.45,color,1,cv2.LINE_AA)
    return image


def main():
    args = parse_args()
    image_path = args.image.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    original = cv2.imread(str(image_path))

    if original is None:
        raise SystemExit(f"Could not read image: {image_path}")

    if args.constraints_only and args.optimizer != "push":
        raise SystemExit("--constraints-only applies to --optimizer push")
    if args.detections_json:
        detected_result = json.loads(args.detections_json.read_text())
        if "floorPlan" in detected_result:
            detected_result = detected_result["floorPlan"]
        dimensions = detected_result.get("image",{})
        if dimensions.get("widthPixels",original.shape[1]) != original.shape[1] or dimensions.get("heightPixels",original.shape[0]) != original.shape[0]:
            raise SystemExit("Cached detection dimensions do not match this image. Use detection JSON for this exact image size.")
    else:
        from detection_pipeline import DetectionPipeline
        pipeline = DetectionPipeline(
            detection_conf=args.detection_conf,
            room_conf=args.room_conf,
            object_conf=args.object_conf,
        )
        detected_result, _ = pipeline.analyze_floor_plan(image_path=str(image_path))
    (output_dir/"00_detection_result.json").write_text(json.dumps(detected_result,indent=2))

    partition_builder = RoomPartitionBuilder(
        max_fill_distance_pixels=args.partition_gap,
    )

    partition_result = partition_builder.build(
        detection_result=detected_result,
        image_shape=original.shape,
    )

    normalized_result = partition_result.detection_result
    min_areas_m2 = parse_min_area_values(args.min_area_m2)

    if args.optimizer == "push":
        optimizer = SharedWallPushOptimizer(
            solver="highs",
            minimum_area_ratio=args.min_ratio,
            grid_step_pixels=args.push_step,
            fixture_margin_pixels=args.fixture_margin,
            fixture_gap_pixels=args.fixture_gap,
            mapping_tolerance_pixels=args.fixture_map_tolerance,
            fixture_overrides=json.loads(args.fixture_overrides.read_text()) if args.fixture_overrides else None,
            window_policy=args.window_policy,
            window_catalog_path=args.window_catalog,
            window_resize_penalty=args.window_resize_penalty,
            backend=args.push_backend,
            time_limit_seconds=args.push_time_limit,
            mip_relative_gap=args.push_mip_gap,
            max_grid_cells=args.push_max_cells,
            fixture_position=args.fixture_position,
            maximum_target_growth=args.max_target_growth,
        )
        report = optimizer.describe_constraints(normalized_result,args.pixels_per_metre)
        (output_dir/"push_constraints.json").write_text(json.dumps(report,indent=2))
        target_id = resolve_target_room(extract_room_polygons(normalized_result,extract_boundary_polygon(normalized_result)),args.target_room)
        overlay = draw_detected_layout(original,normalized_result,target_id)
        draw_fixture_lines(overlay,report["fixtures"],original=True)
        cv2.imwrite(str(output_dir/"04_push_constraints.png"),overlay)
        if args.constraints_only:
            cv2.imwrite(str(output_dir/"02_normalized_partition.png"),draw_partition_layout(original.shape,normalized_result,target_id))
            (output_dir/"02_normalized_partition.json").write_text(json.dumps({"partition":partition_result.to_dict(),"floorPlan":normalized_result},indent=2))
            print(f"Constraints saved to {output_dir}. Review all fixture widths/room assignments before solving.")
            return
    elif args.optimizer == "placement":
        optimizer = GlobalPlacementOptimizer(
            solver="highs",
            minimum_area_ratio=args.min_ratio,
            placement_step_pixels=args.placement_step,
            max_movement_pixels=args.max_movement,
            scale_level_count=args.scale_levels,
        )
    else:
        optimizer = AmplRoomOptimizer(
            solver="highs",
            expansion_step_pixels=args.step,
            max_expansion_pixels=args.max_expansion,
            minimum_area_ratio=args.min_ratio,
        )

    optimization_result = optimizer.optimize(
        detection_result=normalized_result,
        target_room=args.target_room,
        minimum_area_square_metres=min_areas_m2,
        pixels_per_metre=args.pixels_per_metre,
    )

    detected_image = draw_detected_layout(
        original,
        detected_result,
        optimization_result.target_room_id,
    )

    normalized_image = draw_partition_layout(
        original.shape,
        normalized_result,
        optimization_result.target_room_id,
    )

    optimized_image = draw_optimized_layout(
        original.shape,
        optimization_result,
    )
    if args.optimizer == "push":
        draw_fixture_lines(optimized_image,optimization_result.fixtures)

    detected_path = output_dir / "01_detected_layout.png"
    normalized_path = output_dir / "02_normalized_partition.png"
    optimized_path = output_dir / "03_optimized_layout.png"
    partition_json_path = output_dir / "02_normalized_partition.json"
    optimization_json_path = output_dir / "optimization_result.json"

    cv2.imwrite(str(detected_path), detected_image)
    cv2.imwrite(str(normalized_path), normalized_image)
    cv2.imwrite(str(optimized_path), optimized_image)

    with partition_json_path.open("w", encoding="utf-8") as file:
        json.dump(
            {
                "partition": partition_result.to_dict(),
                "floorPlan": normalized_result,
            },
            file,
            indent=2,
        )

    with optimization_json_path.open("w", encoding="utf-8") as file:
        json.dump(
            optimization_result.to_dict(),
            file,
            indent=2,
        )

    print(
        f"Target room: {optimization_result.target_room_id} - "
        f"{optimization_result.target_room_name}"
    )
    print(f"Partition fill distance: {partition_result.max_fill_distance_pixels:.2f} px")
    print(
        f"Estimated wall thickness: "
        f"{partition_result.estimated_wall_thickness_pixels:.2f} px"
    )
    print(f"Initial unassigned pixels: {partition_result.initial_unassigned_pixels}")
    print(f"Filled gap pixels: {partition_result.filled_pixels}")
    print(f"Remaining unassigned pixels: {partition_result.remaining_unassigned_pixels}")
    print(f"Original overlap pixels: {partition_result.overlap_pixels}")
    print()
    print(f"Optimization result: {optimization_result.solve_result}")
    if args.optimizer == "push":
        print("Solver details:",json.dumps(optimization_result.solver_details))
        for fixture in optimization_result.fixtures:
            print(f"  {fixture['id']}: {fixture['originalWidthPixels']:.2f} -> {fixture['widthPixels']:.2f}px, size={fixture['selectedSize']}, rooms={fixture['roomIds']}")
    print(
        f"Normalized target area: "
        f"{optimization_result.target_original_area_pixels:.2f} px²"
    )
    print(
        f"Optimized target area: "
        f"{optimization_result.target_optimized_area_pixels:.2f} px²"
    )
    print(f"Target gain: {optimization_result.target_gain_pixels:.2f} px²")
    print()

    for room_id in sorted(optimization_result.rooms):
        room = optimization_result.rooms[room_id]
        print(
            f"Room {room_id} - {room.name}: "
            f"{room.original_area_pixels:.2f} -> "
            f"{room.optimized_area_pixels:.2f} px², "
            f"minimum {room.minimum_area_pixels:.2f} px²"
        )

    selected_placements = getattr(optimization_result, "selected_placements", {})
    if selected_placements:
        print()
        print("Selected topology-preserving room placements:")
        for room_id, candidate in sorted(selected_placements.items()):
            print(
                f"  Room {room_id}: area ratio {candidate.area_ratio:.4f}, "
                f"x-scale {candidate.scale_x:.4f}, "
                f"y-scale {candidate.scale_y:.4f}, "
                f"movement {candidate.movement_pixels:.2f}px"
            )

    selected_options = getattr(optimization_result, "selected_options", {})
    if selected_options:
        print()
        print("Selected coordinated wall transfers:")
        for option in sorted(
            selected_options.values(),
            key=lambda value: value.edge_id,
        ):
            print(
                f"  Room {option.donor_id} -> Room {option.receiver_id}: "
                f"{option.transfer_area_pixels:.2f} px² "
                f"(depth {option.depth_pixels}px)"
            )

    print()
    print(f"Detected layout: {detected_path}")
    print(f"Normalized partition: {normalized_path}")
    print(f"Optimized layout: {optimized_path}")
    print(f"Partition JSON: {partition_json_path}")
    print(f"Optimization JSON: {optimization_json_path}")


if __name__ == "__main__":
    main()
