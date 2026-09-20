from __future__ import annotations

import sys
from pathlib import Path

from shapely.geometry import Polygon
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from optimization.ampl_room_optimizer import (
    AmplRoomOptimizer,
    points_to_polygon,
    polygon_holes_to_points,
    polygon_to_points,
)


def _points(*coordinates: tuple[float, float]):
    return [{"x": x, "y": y} for x, y in coordinates]


def _three_room_chain():
    return {
        "buildingBoundary": {
            "polygon": _points((0, 0), (300, 0), (300, 100), (0, 100)),
        },
        "rooms": [
            {
                "id": 1,
                "name": "Distant room",
                "polygon": _points((0, 0), (100, 0), (100, 100), (0, 100)),
            },
            {
                "id": 2,
                "name": "Intermediate room",
                "polygon": _points((100, 0), (200, 0), (200, 100), (100, 100)),
            },
            {
                "id": 3,
                "name": "Target room",
                "polygon": _points((200, 0), (300, 0), (300, 100), (200, 100)),
            },
        ],
    }


def test_global_model_propagates_change_through_non_target_room():
    optimizer = AmplRoomOptimizer(
        solver="highs",
        expansion_step_pixels=10,
        max_expansion_pixels=80,
        minimum_area_ratio=0.60,
        minimum_shared_wall_pixels=5,
    )

    result = optimizer.optimize(_three_room_chain(), target_room=3)

    assert set(result.rooms) == {1, 2, 3}
    assert result.rooms[1].optimized_area_pixels < result.rooms[1].original_area_pixels
    assert result.rooms[3].optimized_area_pixels >= 17_999
    assert any(
        option.donor_id == 1 and option.receiver_id == 2
        for option in result.selected_options.values()
    )
    assert any(
        option.donor_id == 2 and option.receiver_id == 3
        for option in result.selected_options.values()
    )

    for room in result.rooms.values():
        assert room.optimized_area_pixels + 1e-6 >= room.minimum_area_pixels
        assert not room.optimized_polygon.interiors

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


def test_polygon_json_preserves_interior_rings():
    polygon = Polygon(
        [(0, 0), (10, 0), (10, 10), (0, 10)],
        holes=[[(3, 3), (7, 3), (7, 7), (3, 7)]],
    )

    restored = points_to_polygon(
        polygon_to_points(polygon),
        polygon_holes_to_points(polygon),
    )

    assert restored is not None
    assert restored.equals(polygon)
    assert len(restored.interiors) == 1