import cv2
import numpy as np
from shapely.geometry import Polygon


class Opening:
    def __init__(self, opening_id, room1, room2, opening_poly):
        self.id = opening_id
        self.room1 = room1
        self.room2 = room2
        self.openingPoly = opening_poly


class opening_detect:
    def __init__(
        self,
        thick_lines_img,
        draw_image,
        rooms,
        doors=None,
        windows=None,
        min_opening_len=25,
        max_opening_len=180,
        wall_strip=10,
        corner_margin=12,
        support_len=10,
        exclude_distance=10,
        room_connect_distance=25,
        room_touch_distance=3,
        duplicate_distance=10,
    ):
        self.thick_lines_img = thick_lines_img
        self.draw_image = draw_image
        self.rooms = rooms or []
        self.doors = doors or []
        self.windows = windows or []

        self.min_opening_len = min_opening_len
        self.max_opening_len = max_opening_len
        self.wall_strip = wall_strip
        self.corner_margin = corner_margin
        self.support_len = support_len
        self.exclude_distance = exclude_distance
        self.room_connect_distance = room_connect_distance
        self.room_touch_distance = room_touch_distance
        self.duplicate_distance = duplicate_distance

        self.mask = self._load_mask(thick_lines_img)
        self.known_polys = self._collect_known_polys()

    def _load_mask(self, thick_lines_img):
        if isinstance(thick_lines_img, str):
            mask = cv2.imread(thick_lines_img, cv2.IMREAD_GRAYSCALE)
            if mask is None:
                raise ValueError(f"Could not read thick line image: {thick_lines_img}")
        else:
            mask = thick_lines_img.copy()
            if len(mask.shape) == 3:
                mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)

        _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
        return mask

    def bbox_to_polygon(self, x1, y1, x2, y2):
        return Polygon([
            (x1, y1),
            (x2, y1),
            (x2, y2),
            (x1, y2)
        ])

    def _get_poly(self, item):
        if item is None:
            return None

        # Already a shapely polygon
        if hasattr(item, "bounds") and hasattr(item, "intersects"):
            return item

        # Door/opening object, depending on your config class name
        for attr in ["door_poly", "doorPoly", "openingPoly", "poly", "roomPoly"]:
            if hasattr(item, attr):
                return getattr(item, attr)

        return None

    def _collect_known_polys(self):
        known = []

        for d in self.doors:
            p = self._get_poly(d)
            if p is not None:
                known.append(p)

        for w in self.windows:
            p = self._get_poly(w)
            if p is not None:
                known.append(p)

        return known

    def _is_known_door_or_window(self, poly):
        test_poly = poly.buffer(self.exclude_distance)

        for known in self.known_polys:
            if test_poly.intersects(known):
                return True

        return False

    def _close_small_false_runs(self, arr, max_len=5):
        """
        Fills tiny black breaks inside a wall line, so small wall noise
        does not become a fake opening.
        """
        arr = arr.copy()
        start = None

        for i, value in enumerate(arr):
            if not value and start is None:
                start = i

            if (value or i == len(arr) - 1) and start is not None:
                end = i if value else i + 1

                if end - start <= max_len:
                    arr[start:end] = True

                start = None

        return arr

    def _segments_from_gap_mask(self, gap_mask):
        segments = []
        start = None

        for i, is_gap in enumerate(gap_mask):
            if is_gap and start is None:
                start = i

            if (not is_gap or i == len(gap_mask) - 1) and start is not None:
                end = i if not is_gap else i + 1
                length = end - start

                if self.min_opening_len <= length <= self.max_opening_len:
                    segments.append((start, end))

                start = None

        return segments

    def _has_wall_support(self, wall_present, start, end):
        """
        A real opening should usually have wall before and after the gap.
        This removes long empty room edges that are not real walls.
        """
        left_start = max(0, start - self.support_len)
        left_end = start
        right_start = end
        right_end = min(len(wall_present), end + self.support_len)

        has_left_wall = np.any(wall_present[left_start:left_end])
        has_right_wall = np.any(wall_present[right_start:right_end])

        return has_left_wall and has_right_wall

    def _opening_candidates_on_horizontal_edge(self, y, x1, x2):
        h, w = self.mask.shape[:2]

        x1 = int(max(0, round(x1 + self.corner_margin)))
        x2 = int(min(w - 1, round(x2 - self.corner_margin)))
        y = int(round(y))

        if x2 <= x1:
            return []

        y1 = max(0, y - self.wall_strip)
        y2 = min(h, y + self.wall_strip + 1)

        roi = self.mask[y1:y2, x1:x2]
        if roi.size == 0:
            return []

        # Wall exists in this column if at least two white pixels are found in the strip
        wall_present = np.count_nonzero(roi > 0, axis=0) >= 2
        wall_present = self._close_small_false_runs(wall_present, max_len=5)
        gap_mask = np.logical_not(wall_present)

        candidates = []
        for start, end in self._segments_from_gap_mask(gap_mask):
            if not self._has_wall_support(wall_present, start, end):
                continue

            gx1 = x1 + start
            gx2 = x1 + end
            poly = self.bbox_to_polygon(
                gx1,
                y - self.wall_strip,
                gx2,
                y + self.wall_strip,
            )
            candidates.append(poly)

        return candidates

    def _opening_candidates_on_vertical_edge(self, x, y1, y2):
        h, w = self.mask.shape[:2]

        y1 = int(max(0, round(y1 + self.corner_margin)))
        y2 = int(min(h - 1, round(y2 - self.corner_margin)))
        x = int(round(x))

        if y2 <= y1:
            return []

        x1 = max(0, x - self.wall_strip)
        x2 = min(w, x + self.wall_strip + 1)

        roi = self.mask[y1:y2, x1:x2]
        if roi.size == 0:
            return []

        # Wall exists in this row if at least two white pixels are found in the strip
        wall_present = np.count_nonzero(roi > 0, axis=1) >= 2
        wall_present = self._close_small_false_runs(wall_present, max_len=5)
        gap_mask = np.logical_not(wall_present)

        candidates = []
        for start, end in self._segments_from_gap_mask(gap_mask):
            if not self._has_wall_support(wall_present, start, end):
                continue

            gy1 = y1 + start
            gy2 = y1 + end
            poly = self.bbox_to_polygon(
                x - self.wall_strip,
                gy1,
                x + self.wall_strip,
                gy2,
            )
            candidates.append(poly)

        return candidates

    def _rooms_touch(self, room1, room2):
        """
        Returns True only when the two room polygons touch each other,
        overlap at their borders, or are separated by a very small tolerance.

        A small tolerance is useful because detected room polygons are not always
        perfectly aligned pixel-for-pixel.
        """
        poly1 = room1.roomPoly
        poly2 = room2.roomPoly

        if poly1.is_empty or poly2.is_empty:
            return False

        if poly1.touches(poly2) or poly1.boundary.intersects(poly2.boundary):
            return True

        boundary_distance = poly1.boundary.distance(poly2.boundary)
        return boundary_distance <= self.room_touch_distance

    def _find_connected_rooms(self, opening_poly):
        """
        Finds a pair of rooms for the opening.

        The pair is accepted only when:
        1. Both rooms are close enough to the opening.
        2. The two room polygons touch each other, within room_touch_distance.
        3. The opening is close to the shared border area between the rooms.
        """
        best_pair = None
        best_score = float("inf")

        for i, room1 in enumerate(self.rooms):
            for room2 in self.rooms[i + 1:]:
                if not self._rooms_touch(room1, room2):
                    continue

                distance1 = room1.roomPoly.distance(opening_poly)
                distance2 = room2.roomPoly.distance(opening_poly)

                if distance1 > self.room_connect_distance:
                    continue
                if distance2 > self.room_connect_distance:
                    continue

                # Approximate the shared border. Buffering handles small detection
                # gaps between room polygons.
                shared_border_zone = (
                    room1.roomPoly.boundary.buffer(self.room_touch_distance)
                    .intersection(
                        room2.roomPoly.boundary.buffer(self.room_touch_distance)
                    )
                )

                if shared_border_zone.is_empty:
                    continue

                if opening_poly.distance(shared_border_zone) > self.room_connect_distance:
                    continue

                score = (
                    distance1
                    + distance2
                    + opening_poly.distance(shared_border_zone)
                )

                if score < best_score:
                    best_score = score
                    best_pair = (room1, room2)

        if best_pair is None:
            return None, None

        return best_pair

    def _is_duplicate(self, poly, openings):
        test_poly = poly.buffer(self.duplicate_distance)

        for op in openings:
            if test_poly.intersects(op.openingPoly):
                return True

        return False

    def _draw_opening(self, opening):
        x1, y1, x2, y2 = opening.openingPoly.bounds
        x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

        cv2.rectangle(
            self.draw_image,
            (x1, y1),
            (x2, y2),
            (0, 165, 255),
            2
        )

        cv2.putText(
            self.draw_image,
            f"O{opening.id}",
            (x1, max(0, y1 - 5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 165, 255),
            2,
            cv2.LINE_AA
        )

    def detect(self):
        openings = []
        opening_id = 0

        for room in self.rooms:
            minx, miny, maxx, maxy = room.roomPoly.bounds

            candidates = []

            # Top and bottom room edges
            candidates.extend(self._opening_candidates_on_horizontal_edge(miny, minx, maxx))
            candidates.extend(self._opening_candidates_on_horizontal_edge(maxy, minx, maxx))

            # Left and right room edges
            candidates.extend(self._opening_candidates_on_vertical_edge(minx, miny, maxy))
            candidates.extend(self._opening_candidates_on_vertical_edge(maxx, miny, maxy))

            for poly in candidates:
                if poly.is_empty:
                    continue

                if self._is_known_door_or_window(poly):
                    continue

                if self._is_duplicate(poly, openings):
                    continue

                room1, room2 = self._find_connected_rooms(poly)

                # Keep only openings that connect two touching rooms.
                if room1 is None or room2 is None:
                    continue

                opening_id += 1
                op = Opening(opening_id, room1, room2, poly)
                openings.append(op)
                self._draw_opening(op)

        return openings, self.draw_image