import math
import random
import time
import cv2
from shapely.geometry import Polygon
import numpy as np
import easyocr
import re
from shapely.geometry import Point
from configs.room import Room

from configs.mmdet_ImageToJson import CascadeDetector
import os


class imageToRooms:

    room_conf = 0.4
    detection_conf = 0.4

    def __init__(
        self,
        detector=None,
        detection_conf=None,
        room_conf=None,
        ocr=None,
        ocr_conf=0.45
    ):
        if detection_conf is not None:
            self.detection_conf = detection_conf

        if room_conf is not None:
            self.room_conf = room_conf

        # Load the local MMDetection model once.
        self.detector = detector or CascadeDetector(
            confidence_threshold=self.detection_conf
        )

        self.ocr_conf = ocr_conf

        # =====================================================
        # EASYOCR
        # =====================================================
        #
        # EasyOCR replaces Apple Vision.
        #
        # This removes the macOS-only Quartz/Vision dependency
        # and makes this OCR part compatible with Linux,
        # Windows and Docker.
        #
        # The reader is created once and reused.
        #
        # We use CPU mode for now because our first goal is
        # portability. GPU support can be added to Docker later.
        # =====================================================

        self.ocr = easyocr.Reader(
            ["en"],
            gpu=True
        )


    def get_detection_json(self, image_path):
        '''
        Runs the local Cascade MMDetection model and returns JSON data.
        This replaces the old FastAPI/requests call.
        '''

        return self.detector.predict_json(
            image_path,
            confidence_threshold=self.detection_conf
        )


    def calling_api(self, image_path, url=None):

        return self.get_detection_json(
            image_path
        )


    def rooms_in_plan(
        self,
        data,
        room_conf
    ):

        '''
        this method here takes json data and a confindanse float
        (between 0 and 1) as parameter.

        it returns a list of rooms that is sorted and filtered
        based on the confidanse number.
        '''

        rooms = data[
            "detectionResults"
        ].get(
            "rooms",
            []
        )

        # Filter + sort rooms by confidence
        rooms_filterd = []

        for rm in rooms:

            confidence = rm.get(
                "confidence",
                0
            )

            if confidence >= room_conf:

                rooms_filterd.append(
                    rm
                )

        rooms_filterd.sort(
            key=lambda rm:
                rm.get(
                    "confidence",
                    0
                ),
            reverse=True
        )

        return rooms_filterd


    # =========================================================
    # OCR
    # =========================================================

    def extract_text_boxes(
        self,
        img
    ):
        """
        Detects and recognizes text using EasyOCR.

        Returns a list of dictionaries containing:

        - text
        - confidence
        - center
        - polygon
        - height


        EasyOCR returns coordinates directly in image pixel
        coordinates.

        This means we no longer need the Apple Vision conversion
        from normalized bottom-left coordinates to OpenCV
        top-left coordinates.
        """

        if img is None:

            return []


        # =====================================================
        # RUN EASYOCR
        # =====================================================
        #
        # detail=1:
        # returns:
        #
        # (
        #     bounding box,
        #     detected text,
        #     confidence
        # )
        #
        # paragraph=False:
        # keeps individual text detections because our existing
        # room_contains_text() function combines words itself.
        #
        # min_size=5:
        # floor-plan labels can be small, so we allow smaller
        # detected text boxes than the default.
        # =====================================================

        results = self.ocr.readtext(
            img,
            detail=1,
            paragraph=False,
            min_size=5
        )


        text_boxes = []


        # =====================================================
        # CONVERT EASYOCR RESULTS
        #
        # We convert EasyOCR output into exactly the structure
        # the rest of your existing code already expects.
        # =====================================================

        for result in results:

            if len(result) != 3:

                continue


            box, text, confidence = result


            text = str(
                text
            ).strip()


            confidence = float(
                confidence
            )


            # =================================================
            # CONFIDENCE FILTER
            # =================================================

            if confidence < self.ocr_conf:

                continue


            # =================================================
            # REMOVE DIMENSIONS / USELESS TEXT
            # =================================================

            if not self.is_meaningful(
                text
            ):

                continue


            # =================================================
            # POLYGON
            #
            # EasyOCR normally returns:
            #
            # [
            #   [top-left],
            #   [top-right],
            #   [bottom-right],
            #   [bottom-left]
            # ]
            # =================================================

            polygon = np.array(
                box,
                dtype=np.float32
            )


            # Ensure that the returned data actually looks like
            # a polygon before using it.

            if (
                polygon.ndim != 2
                or
                polygon.shape[0] < 4
                or
                polygon.shape[1] != 2
            ):

                continue


            # =================================================
            # CENTER
            # =================================================

            center_x = float(
                np.mean(
                    polygon[:, 0]
                )
            )


            center_y = float(
                np.mean(
                    polygon[:, 1]
                )
            )


            # =================================================
            # TEXT HEIGHT
            #
            # Used later when grouping words into text lines.
            # =================================================

            text_height = float(
                np.max(
                    polygon[:, 1]
                )
                -
                np.min(
                    polygon[:, 1]
                )
            )


            # =================================================
            # RETURN SAME STRUCTURE AS BEFORE
            # =================================================

            text_boxes.append(
                {
                    "text":
                        text,

                    "confidence":
                        confidence,

                    "center":
                        (
                            center_x,
                            center_y
                        ),

                    "polygon":
                        polygon,

                    "height":
                        max(
                            text_height,
                            1.0
                        ),
                }
            )


        return text_boxes


    # =========================================================
    # FIND TEXT INSIDE ROOM
    # =========================================================

    def room_contains_text(
        self,
        poly,
        text_boxes
    ):
        """
        Finds OCR results whose centre points are inside a room
        polygon and rebuilds the room label in reading order.
        """

        words = []


        for item in text_boxes:

            center_x, center_y = item[
                "center"
            ]


            point = Point(
                center_x,
                center_y
            )


            if poly.covers(
                point
            ):

                words.append(
                    item
                )


        if not words:

            return False, None


        # =====================================================
        # SORT WORDS
        # =====================================================

        words.sort(
            key=lambda item:
                (
                    item[
                        "center"
                    ][1],

                    item[
                        "center"
                    ][0]
                )
        )


        lines = []


        # =====================================================
        # GROUP WORDS INTO LINES
        # =====================================================

        for word in words:

            word_y = word[
                "center"
            ][1]


            tolerance = max(
                word[
                    "height"
                ]
                *
                0.7,

                8.0
            )


            matching_line = None


            for line in lines:

                if abs(
                    word_y
                    -
                    line[
                        "mean_y"
                    ]
                ) <= max(
                    tolerance,
                    line[
                        "tolerance"
                    ]
                ):

                    matching_line = line

                    break


            if matching_line is None:

                lines.append(
                    {
                        "words":
                            [
                                word
                            ],

                        "mean_y":
                            word_y,

                        "tolerance":
                            tolerance,
                    }
                )

            else:

                matching_line[
                    "words"
                ].append(
                    word
                )


                matching_line[
                    "mean_y"
                ] = sum(
                    item[
                        "center"
                    ][1]

                    for item
                    in matching_line[
                        "words"
                    ]

                ) / len(
                    matching_line[
                        "words"
                    ]
                )


                matching_line[
                    "tolerance"
                ] = max(
                    matching_line[
                        "tolerance"
                    ],

                    tolerance
                )


        # =====================================================
        # ORDER LINES
        # =====================================================

        lines.sort(
            key=lambda line:
                line[
                    "mean_y"
                ]
        )


        label_lines = []


        for line in lines:

            line[
                "words"
            ].sort(
                key=lambda item:
                    item[
                        "center"
                    ][0]
            )


            label_lines.append(
                " ".join(
                    item[
                        "text"
                    ]

                    for item
                    in line[
                        "words"
                    ]
                )
            )


        text = " ".join(
            label_lines
        ).strip()


        return (
            bool(
                text
            ),

            text or None
        )


    # =========================================================
    # TEXT FILTER
    # =========================================================

    def is_meaningful(
        self,
        text
    ):
        '''
        Removes everything that is not useful text.

        Dimension-only strings such as:
        120
        300
        4500

        are rejected.
        '''

        cleaned = re.sub(
            r"[^A-Za-z0-9]",
            "",
            text
        )


        if len(
            cleaned
        ) < 2:

            return False


        # Keep words and mixed labels,
        # but reject dimension-only strings.

        if cleaned.isdigit():

            return False


        return any(
            character.isalpha()

            for character
            in cleaned
        )


    # =========================================================
    # BBOX -> POLYGON
    # =========================================================

    def bbox_to_polygon(
        self,
        x1,
        y1,
        x2,
        y2
    ):
        '''
        this method takes coordinates and makes polygons
        '''

        return Polygon(
            [
                (
                    x1,
                    y1
                ),

                (
                    x2,
                    y1
                ),

                (
                    x2,
                    y2
                ),

                (
                    x1,
                    y2
                )
            ]
        )


    # =========================================================
    # REMOVE INSIDE POLYGONS
    # =========================================================

    def remove_inside_polygon(
        self,
        room_poly
    ):
        """
        Removes polygons that are completely inside another
        polygon.

        If a small polygon is fully inside a bigger polygon,
        the small one is deleted.
        """

        final_poly = []


        for i, poly in enumerate(
            room_poly
        ):

            is_inside_poly = False


            for j, other_poly in enumerate(
                room_poly
            ):

                if i == j:

                    continue


                if other_poly.contains(
                    poly
                ):

                    is_inside_poly = True


            if not is_inside_poly:

                final_poly.append(
                    poly
                )


        return final_poly


    # =========================================================
    # SUBTRACT OVERLAPS
    # =========================================================

    def subtract_overlaps(
        self,
        room_polygons
    ):
        '''
        this method subtract polygons from each others.

        this is to get a better shape to the polygons and more
        accurate ones.

        it takes a list of polygon rooms as a list.

        here we subtract the smaller polygons from the bigger
        ones.
        '''

        sorted_polys = sorted(
            room_polygons,
            key=lambda p:
                p.area
        )


        final_polys = []


        for i, current in enumerate(
            sorted_polys
        ):

            # Subtract all smaller ones

            for smaller in sorted_polys[
                :i
            ]:

                if current.intersects(
                    smaller
                ):

                    current = current.difference(
                        smaller
                    )


            if current.is_empty:

                final_polys.append(
                    current
                )

                continue


            if current.geom_type == "MultiPolygon":

                # keep largest part only

                largest = max(
                    current.geoms,
                    key=lambda p:
                        p.area
                )


                current = largest


            final_polys.append(
                current
            )


        return final_polys


    # =========================================================
    # DRAW ROOM POLYGON
    # =========================================================

    def draw_polygon(
        self,
        img,
        poly,
        color,
        label_idx
    ):
        '''
        this method takes a cv2 image read, polygon, a color and
        a label number and then draws out the polygons on the
        image.
        '''

        coords = np.array(
            poly.exterior.coords,
            dtype=np.int32
        )


        # Draw shape

        cv2.polylines(
            img,
            [
                coords
            ],
            True,
            color,
            2
        )


        # Label positioning
        # top-left corner of polygon bbox

        minx, miny, maxx, maxy = poly.bounds


        minx = int(
            minx
        )


        miny = int(
            miny
        )


        label = str(
            label_idx
        )


        font = cv2.FONT_HERSHEY_SIMPLEX


        font_scale = 0.8


        thickness = 2


        (
            tw,
            th
        ), _ = cv2.getTextSize(
            label,
            font,
            font_scale,
            thickness
        )


        # Padding

        pad = 6


        # Background rectangle position

        box_x1 = minx


        box_y1 = max(
            miny
            -
            th
            -
            pad
            *
            2,

            0
        )


        box_x2 = (
            box_x1
            +
            tw
            +
            pad
            *
            2
        )


        box_y2 = (
            box_y1
            +
            th
            +
            pad
            *
            2
        )


        # Draw filled rectangle

        cv2.rectangle(
            img,
            (
                box_x1,
                box_y1
            ),
            (
                box_x2,
                box_y2
            ),
            color,
            -1
        )


        # Draw text centered inside

        text_x = (
            box_x1
            +
            pad
        )


        text_y = (
            box_y1
            +
            th
            +
            pad
        )


        cv2.putText(
            img,
            label,
            (
                text_x,
                text_y
            ),
            font,
            font_scale,
            (
                0,
                0,
                0
            ),
            thickness,
            cv2.LINE_AA
        )


    # =========================================================
    # ROOM CENTER
    # =========================================================

    def room_cent(
        self,
        image_path
    ):

        img = cv2.imread(
            image_path
        )


        h, w = img.shape[
            :2
        ]


        centroid_x = (
            w
            /
            2
        )


        centroid_y = (
            h
            /
            2
        )


        return [
            centroid_x,
            centroid_y
        ]


    # =========================================================
    # DRAW ROOM TEXT
    # =========================================================

    def draw_room_text(
        self,
        img,
        poly,
        text
    ):
        """
        Draws the detected room text inside the polygon.
        """

        if (
            text is None
            or
            text == ""
        ):

            return


        centroid = poly.centroid


        x = int(
            centroid.x
        )


        y = int(
            centroid.y
        )


        font = cv2.FONT_HERSHEY_SIMPLEX


        font_scale = 0.45


        thickness = 1


        # Text size

        (
            text_width,
            text_height
        ), _ = cv2.getTextSize(
            text,
            font,
            font_scale,
            thickness
        )


        # Center text around centroid

        text_x = (
            x
            -
            text_width
            //
            2
        )


        text_y = (
            y
            +
            text_height
            //
            2
        )


        # Optional white background behind text

        pad = 4


        cv2.rectangle(
            img,

            (
                text_x
                -
                pad,

                text_y
                -
                text_height
                -
                pad
            ),

            (
                text_x
                +
                text_width
                +
                pad,

                text_y
                +
                pad
            ),

            (
                255,
                255,
                255
            ),

            -1
        )


        # Draw text

        cv2.putText(
            img,

            text,

            (
                text_x,
                text_y
            ),

            font,

            font_scale,

            (
                0,
                0,
                0
            ),

            thickness,

            cv2.LINE_AA
        )


    # =========================================================
    # GET ROOM CONFIDENCE
    # =========================================================

    def get_room_confidence(
        self,
        final_poly,
        room_info
    ):
        """
        Finds which original detected room belongs to the final
        polygon and returns its original MMDetection confidence.
        """

        best_confidence = 0.0


        largest_overlap = 0.0


        for (
            idx,
            rm,
            original_poly
        ) in room_info:

            if not final_poly.intersects(
                original_poly
            ):

                continue


            overlap_area = final_poly.intersection(
                original_poly
            ).area


            if overlap_area > largest_overlap:

                largest_overlap = overlap_area


                best_confidence = float(
                    rm.get(
                        "confidence",
                        0.0
                    )
                )


        return best_confidence


    # =========================================================
    # CREATE ROOMS
    # =========================================================

    def print_out_rooms(
        self,
        Orgignal_image_path,
        rooms
    ):
        '''
        this method takes an image path, list of filtered rooms,
        the diractory it will be outputted to and the confidance
        number we choose to take and makes the polygons on the
        image, makes the directory and saves the image.
        '''

        original_img = cv2.imread(
            str(
                Orgignal_image_path
            )
        )


        # =====================================================
        # OCR
        # =====================================================

        text_boxes = self.extract_text_boxes(
            original_img
        )


        # =====================================================
        # STEP 1:
        # Convert bboxes -> polygons
        # =====================================================

        polygons = []


        room_info = []


        random.seed(
            42
        )


        for idx, rm in enumerate(
            rooms,
            start=1
        ):

            x1 = int(
                rm[
                    "position"
                ][
                    "start"
                ][
                    "x"
                ]
            )


            y1 = int(
                rm[
                    "position"
                ][
                    "start"
                ][
                    "y"
                ]
            )


            x2 = int(
                rm[
                    "position"
                ][
                    "end"
                ][
                    "x"
                ]
            )


            y2 = int(
                rm[
                    "position"
                ][
                    "end"
                ][
                    "y"
                ]
            )


            poly = self.bbox_to_polygon(
                x1,
                y1,
                x2,
                y2
            )


            polygons.append(
                poly
            )


            room_info.append(
                (
                    idx,
                    rm,
                    poly
                )
            )


        # =====================================================
        # DELETE POLYGONS INSIDE EACH OTHER
        # =====================================================

        polygons = self.remove_inside_polygon(
            polygons
        )


        # =====================================================
        # STEP 2:
        # subtract overlaps
        # smaller rooms win
        # =====================================================

        final_polygons = self.subtract_overlaps(
            polygons
        )


        # =====================================================
        # STEP 3:
        # create room objects
        # =====================================================

        new_idx = 0


        roomse = []


        roomC = self.room_cent(
            Orgignal_image_path
        )


        for poly in final_polygons:

            texten = None


            if poly.is_empty:

                continue


            textInPoly = self.room_contains_text(
                poly,
                text_boxes
            )


            if textInPoly[
                0
            ]:

                texten = textInPoly[
                    1
                ]

            else:

                continue


            geoms = (
                poly.geoms

                if hasattr(
                    poly,
                    "geoms"
                )

                else [
                    poly
                ]
            )


            color = (
                random.randint(
                    50,
                    255
                ),

                random.randint(
                    50,
                    255
                ),

                random.randint(
                    50,
                    255
                ),
            )


            for sub in geoms:

                new_idx += 1


                centroi = sub.centroid


                distance = math.sqrt(
                    (
                        centroi.x
                        -
                        roomC[
                            0
                        ]
                    )
                    **
                    2
                    +
                    (
                        centroi.y
                        -
                        roomC[
                            1
                        ]
                    )
                    **
                    2
                )


                confidence = self.get_room_confidence(
                    sub,
                    room_info
                )


                rom = Room(
                    new_idx,
                    original_img,
                    sub,

                    text=
                        texten,

                    centroid=
                        (
                            centroi.x,
                            centroi.y
                        ),

                    distFromCentroid=
                        distance,

                    confidence=
                        confidence
                )


                roomse.append(
                    rom
                )


                self.draw_polygon(
                    original_img,
                    sub,
                    color,
                    new_idx
                )


                self.draw_room_text(
                    original_img,
                    sub,
                    texten
                )


        return (
            roomse,
            original_img
        )


    # =========================================================
    # RETURN ROOMS
    # =========================================================

    def returnRoom(
        self,
        original_image
    ):

        image_extensions = (
            'png',
            'jpg',
            'jpeg',
            'webp'
        )


        if original_image.split(
            "."
        )[1] not in image_extensions:

            print(
                "Wrong image type."
            )

            return []


        


        data = self.get_detection_json(
            original_image
        )


        rooms = self.rooms_in_plan(
            data,
            self.room_conf
        )


        res = self.print_out_rooms(
            original_image,
            rooms
        )


        roomene = res[
            0
        ]


        img = res[
            1
        ]


        return (
            roomene,
            img
        )


# =============================================================
# TEST
# =============================================================

if __name__ == "__main__":

    start = time.time()


    roomen = "floorPlan.png"


    listRooms, img = imageToRooms().returnRoom(
        roomen
    )


    for room in listRooms:

        print(
            room.id
        )


        print(
            room.text
        )


        coords = list(
            room.roomPoly.exterior.coords
        )


        print(
            "Polygon coordinates:",
            coords
        )


        print(
            "distance to room cent ",
            room.distFromCentroid
        )


        print(
            "Rooms cent ",
            room.centroid
        )


        print()


    cv2.imwrite(
        "outTest.png",
        img
    )


    end = time.time()


    print(
        "Time taken:",
        end - start,
        "seconds"
    )