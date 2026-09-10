import math
import os
import tempfile

import cv2

from detections.room_detection import imageToRooms
from detections.objectDetect import object_detect
from detections.openingDetect_new import opening_detect
from detections.hybrid_boundary_detection import HybridBoundaryDetector

from configs.keep_only_thick_lines import keep_only_thick_lines
from configs.floorPlan import FloorPlan
from configs.mmdet_ImageToJson import CascadeDetector


class DetectionPipeline:

    def __init__(
        self,
        detection_conf=0.4,
        room_conf=0.4,
        object_conf=0.3
    ):
        """
        Loads the detection models once.

        The same DetectionPipeline object can then be reused
        for multiple floor-plan images.
        """

        self.detection_conf = detection_conf
        self.room_conf = room_conf
        self.object_conf = object_conf

        #print("Loading MMDetection model...")

        # Load Cascade/MMDetection only ONCE.
        self.cascade_detector = CascadeDetector(
            confidence_threshold=self.detection_conf
        )

        # Reuse the already loaded CascadeDetector.
        self.room_detector = imageToRooms(
            detector=self.cascade_detector,
            detection_conf=self.detection_conf,
            room_conf=self.room_conf
        )

        # The hybrid boundary detector has no heavy ML model of its own.
        # It combines the room polygons, thick-wall mask, and optional
        # door/window hints.
        self.boundary_detector = HybridBoundaryDetector()

        #print("Detection pipeline ready.")

    # ---------------------------------------------------------
    # Geometry helper methods
    # ---------------------------------------------------------

    @staticmethod
    def _polygon_to_points(poly):
        """
        Converts a Shapely polygon into JSON-compatible coordinates.

        Example:

        [
            {"x": 100, "y": 200},
            {"x": 400, "y": 200},
            {"x": 400, "y": 500},
            {"x": 100, "y": 500}
        ]
        """

        if poly is None:
            return []

        if poly.is_empty:
            return []

        # Just in case a MultiPolygon appears.
        if poly.geom_type == "MultiPolygon":
            poly = max(poly.geoms, key=lambda p: p.area)

        coordinates = list(poly.exterior.coords)

        # Shapely normally repeats the first coordinate at the end.
        # We do not need the duplicate for the frontend/database.
        if len(coordinates) > 1 and coordinates[0] == coordinates[-1]:
            coordinates = coordinates[:-1]

        return [
            {
                "x": float(x),
                "y": float(y)
            }
            for x, y in coordinates
        ]

    @staticmethod
    def _polygon_to_bbox(poly):
        """
        Converts a polygon into a bounding box.
        """

        if poly is None or poly.is_empty:
            return None

        x1, y1, x2, y2 = poly.bounds

        return {
            "x1": float(x1),
            "y1": float(y1),
            "x2": float(x2),
            "y2": float(y2)
        }

    @staticmethod
    def _get_object_polygon(obj):
        """
        Different detection classes currently use slightly
        different names for their polygon fields.

        This helper finds the polygon without forcing us to
        change those classes yet.
        """

        possible_attributes = [
            "roomPoly",
            "doorPoly",
            "door_poly",
            "openingPoly", 
            "poly"
        ]

        for attribute in possible_attributes:

            if hasattr(obj, attribute):
                return getattr(obj, attribute)

        return None

    @staticmethod
    def _empty_boundary_data(message):
        """
        Boundary detection must never destroy the rest of a successful
        floor-plan detection.

        Even if boundary reconstruction fails, the JSON contract remains
        stable and the frontend can still let the user draw/correct it.
        """
        return {
            "outerPolygon": [],
            "usablePolygon": [],

            # This describes the CURRENT geometry stored in this revision.
            # Revision 1 starts as AI-generated. The frontend/API can later
            # change this to "user" when the user edits the boundary.
            "source": "ai",
            "reviewStatus": "unreviewed",
            "isUserEdited": False,

            # AutomaticAssessment is provenance/quality information from the
            # detector. It does NOT make the boundary read-only.
            "automaticAssessment": {
                "valid": False,
                "requiresReview": True,
                "method": "hybrid",
                "candidateSource": "none",
                "message": str(message),

                "roomAreaCoverage": 0.0,
                "roomCentroidCoverage": 0.0,
                "wallSupport": 0.0,
                "selectedStructuralGapPixels": 0,
                "estimatedWallThicknessPixels": 0.0
            }
        }

    def _boundary_to_data(self, boundary_result):
        """
        Convert HybridBoundaryDetectionResult to the canonical JSON shape.

        IMPORTANT:
        - outerPolygon and usablePolygon are the actual geometry.
        - valid=False only means the automatic result is not trusted enough.
        - The user is allowed to edit the geometry whether valid is True
          or False.
        - Debug raster masks are deliberately NOT stored in JSON.
        """

        if boundary_result is None:
            return self._empty_boundary_data(
                "Boundary detector returned no result."
            )

        outer_polygon = self._polygon_to_points(
            boundary_result.outer_boundary
        )

        usable_polygon = self._polygon_to_points(
            boundary_result.usable_boundary
        )

        automatic_valid = bool(
            boundary_result.valid
        )

        # A result can be provisional (valid=False) and still contain useful
        # geometry. We preserve that geometry instead of throwing it away.
        return {
            "outerPolygon": outer_polygon,
            "usablePolygon": usable_polygon,

            "source": "ai",
            "reviewStatus": "unreviewed",
            "isUserEdited": False,

            "automaticAssessment": {
                "valid": automatic_valid,
                "requiresReview": not automatic_valid,
                "method": "hybrid",

                "candidateSource": str(
                    getattr(
                        boundary_result,
                        "candidate_source",
                        "unknown"
                    )
                ),

                "message": str(
                    getattr(
                        boundary_result,
                        "message",
                        ""
                    )
                ),

                "roomAreaCoverage": float(
                    getattr(
                        boundary_result,
                        "room_area_coverage",
                        0.0
                    )
                ),

                "roomCentroidCoverage": float(
                    getattr(
                        boundary_result,
                        "room_centroid_coverage",
                        0.0
                    )
                ),

                "wallSupport": float(
                    getattr(
                        boundary_result,
                        "wall_support",
                        0.0
                    )
                ),

                "selectedStructuralGapPixels": int(
                    getattr(
                        boundary_result,
                        "selected_structural_gap_px",
                        0
                    )
                ),

                "estimatedWallThicknessPixels": float(
                    getattr(
                        boundary_result,
                        "estimated_wall_thickness_px",
                        0.0
                    )
                )
            }
        }

    # ---------------------------------------------------------
    # Convert detection objects into structured data
    # ---------------------------------------------------------

    def _rooms_to_data(self, rooms):

        room_data = []

        for room in rooms:

            poly = room.roomPoly

            centroid = room.centroid

            room_data.append({
                "id": int(room.id),

                 

                "name": room.text,

                "polygon": self._polygon_to_points(poly),

                "centroid": {
                    "x": float(centroid[0]),
                    "y": float(centroid[1])
                },

                "areaPixels": float(poly.area),

                # Some current Room objects do not preserve
                # detection confidence yet.
                "confidence": float(  room.confidence),
            })

        return room_data

    def _doors_to_data(self, doors):

        door_data = []

        for door in doors:

            poly = self._get_object_polygon(door)

            door_data.append({
                "id": int(door.id),

                "polygon": self._polygon_to_points(poly),

                "bbox": self._polygon_to_bbox(poly),

                "room1": {
                    "id": int(door.room1.id),
                    "name": door.room1.text
                },

                # room2 can be None for an exterior door.
                # In the JSON response, Python None becomes JSON null.
                "room2": (
                    {
                        "id": int(door.room2.id),
                        "name": door.room2.text
                    }
                    if door.room2 is not None
                    else None
                ),

                "confidence": getattr(door, "confidence", None)
            })

        return door_data

    def _windows_to_data(self, windows):

        window_data = []

        for index, window in enumerate(windows, start=1):

            window_data.append({
                "id": index,

                "polygon": self._polygon_to_points(window),

                "bbox": self._polygon_to_bbox(window),

                
            })

        return window_data

    def _openings_to_data(self, openings):

        opening_data = []

        for opening in openings:

            poly = opening.openingPoly

            opening_data.append({
                "id": int(opening.id),

                "polygon": self._polygon_to_points(poly),

                "bbox": self._polygon_to_bbox(poly),

                "room1": {
                    "id": int(opening.room1.id),
                    "name": opening.room1.text
                },

                "room2": {
                    "id": int(opening.room2.id),
                    "name": opening.room2.text
                }
            })

        return opening_data

    # ---------------------------------------------------------
    # Main detection method
    # ---------------------------------------------------------

    def analyze_floor_plan(
        self,
        image_path,
        wall_output_path=None
    ):
        """
        Runs the entire floor-plan detection pipeline.

        Returns:

            result:
                JSON-compatible dictionary containing detected
                floor-plan information.

            annotated_image:
                OpenCV image containing the visual detections.
        """

        if not os.path.exists(image_path):
            raise FileNotFoundError(
                f"Image does not exist: {image_path}"
            )

        original_img = cv2.imread(image_path)

        if original_img is None:
            raise ValueError(
                f"Could not read image: {image_path}"
            )

        image_height, image_width = original_img.shape[:2]

        image_name = os.path.basename(image_path)

        # -----------------------------------------------------
        # 1. Detect rooms
        # -----------------------------------------------------

        rooms, img_print = self.room_detector.returnRoom(
            image_path
        )

        rooms = rooms or []

        # -----------------------------------------------------
        # 2. Detect doors and windows
        # -----------------------------------------------------

        detection_result = object_detect(
            "Door",
            original_img,
            img_print,
            self.object_conf,
            rooms,
            image_name,
            True
        ).detect()

        if detection_result is None:

            doors = []
            windows = []

        else:

            doors, img_print, windows = detection_result

            doors = doors or []
            windows = windows or []

        # -----------------------------------------------------
        # 3. Create thick wall mask
        # -----------------------------------------------------

        temporary_wall_file = False

        if wall_output_path is None:

            file_descriptor, wall_output_path = tempfile.mkstemp(
                suffix="_walls.png"
            )

            os.close(file_descriptor)

            temporary_wall_file = True

        wall_mask = keep_only_thick_lines(
            input_path=image_path,
            output_path=wall_output_path,
            threshold_value=120,
            min_thickness=8,
            min_area=500,
            min_length=40
        )

        # If no permanent wall output was requested,
        # remove the temporary image file.
        if temporary_wall_file:

            try:
                os.remove(wall_output_path)

            except OSError:
                pass

        # -----------------------------------------------------
        # 4. Detect building boundary
        # -----------------------------------------------------
        #
        # Boundary failure is intentionally NON-FATAL.
        #
        # The floor plan, rooms, doors and windows are still valuable even
        # when the boundary is uncertain. In that case we return a stable
        # buildingBoundary object with automaticAssessment.valid=False so the
        # frontend can show it for review/manual editing.
        # -----------------------------------------------------

        try:
            boundary_result = self.boundary_detector.detect(
                rooms=rooms,
                image_shape=original_img.shape,
                thick_wall_mask=wall_mask,
                doors=doors,
                windows=windows,
                mode="ai"
            )

            boundary_data = self._boundary_to_data(
                boundary_result
            )

        except Exception as boundary_error:
            boundary_data = self._empty_boundary_data(
                f"Boundary detection failed: {boundary_error}"
            )

        # -----------------------------------------------------
        # 5. Detect extra openings
        # -----------------------------------------------------

        openings, img_print = opening_detect(
            thick_lines_img=wall_mask,
            draw_image=img_print,
            rooms=rooms,
            doors=doors,
            windows=windows,
            min_opening_len=25,
            max_opening_len=180,
            wall_strip=10,
            corner_margin=12,
            support_len=10,
            exclude_distance=10,
            room_connect_distance=10,
            duplicate_distance=10
        ).detect()

        openings = openings or []

        # -----------------------------------------------------
        # 6. Create FloorPlan
        # -----------------------------------------------------

        floor_plan = FloorPlan(
            rooms,
            doors,
            windows,
            openings
        )

        # -----------------------------------------------------
        # 7. Convert Python objects to structured data
        # -----------------------------------------------------

        result = {

            "type": "floor_plan",

            "image": {
                "fileName": image_name,
                "widthPixels": int(image_width),
                "heightPixels": int(image_height)
            },

            "validation": {
                "valid": bool(floor_plan.valid),
                "hasBathroom": bool(floor_plan.has_bathroom),
                "hasKitchen": bool(floor_plan.has_kitchen)
            },

            "summary": {
                "rooms": len(rooms),
                "doors": len(doors),
                "windows": len(windows),
                "openings": len(openings)
            },

            "rooms": self._rooms_to_data(rooms),

            "doors": self._doors_to_data(doors),

            "windows": self._windows_to_data(windows),

            "openings": self._openings_to_data(openings),

            # Canonical structured building geometry.
            #
            # This is part of the floor-plan JSON, not just visualization.
            # It must be persisted with every revision because later analysis
            # and optimization depend on it.
            "buildingBoundary": boundary_data
        }

        return result, img_print