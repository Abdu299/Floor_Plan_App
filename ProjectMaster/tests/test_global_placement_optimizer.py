from __future__ import annotations

import sys
from math import sqrt
from pathlib import Path

from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from optimization.global_placement_optimizer import GlobalPlacementOptimizer


def _points(*coordinates: tuple[float, float]):
    return [{"x": x, "y": y} for x, y in coordinates]


def _four_room_layout():
    return {
        "buildingBoundary": {
            "polygon": _points((0, 0), (200, 0), (200, 200), (0, 200)),
        },
        "rooms": [
            {
                "id": 1,
                "name": "Top left",
                "polygon": _points((0, 0), (100, 0), (100, 100), (0, 100)),
            },
            {
                "id": 2,
                "name": "Top right",
                "polygon": _points((100, 0), (200, 0), (200, 100), (100, 100)),
            },
            {
                "id": 3,
                "name": "Bottom left",
                "polygon": _points((0, 100), (100, 100), (100, 200), (0, 200)),
            },
            {
                "id": 4,
                "name": "Target",
                "polygon": _points((100, 100), (200, 100), (200, 200), (100, 200)),
            },
        ],
    }


def test_global_placement_scales_whole_rooms_and_assigns_residual_to_target():
    optimizer = GlobalPlacementOptimizer(
        solver="highs",
        minimum_area_ratio=0.60,
        placement_step_pixels=10,
        max_movement_pixels=50,
        scale_level_count=3,
    )

    result = optimizer.optimize(_four_room_layout(), target_room=4)

    assert set(result.rooms) == {1, 2, 3, 4}
    assert set(result.selected_placements) == {1, 2, 3}

    for room_id in (1, 2, 3):
        room = result.rooms[room_id]
        candidate = result.selected_placements[room_id]
        assert abs(room.optimized_area_pixels / room.original_area_pixels - 0.60) < 1e-6
        assert abs(candidate.scale_factor - sqrt(0.60)) < 1e-6
        assert not room.optimized_polygon.interiors

    assert result.rooms[4].optimized_area_pixels > result.rooms[4].original_area_pixels
    assert not result.rooms[4].optimized_polygon.interiors

    union = unary_union(
        [room.optimized_polygon for room in result.rooms.values()]
    )
    assert union.symmetric_difference(result.boundary).area <= 1.0

    room_ids = sorted(result.rooms)
    for index, first_id in enumerate(room_ids):
        for second_id in room_ids[index + 1 :]:
            overlap = result.rooms[first_id].optimized_polygon.intersection(
                result.rooms[second_id].optimized_polygon
            ).area
            assert overlap <= 1.0
