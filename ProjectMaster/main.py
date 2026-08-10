import os
import json
import cv2

from detection_pipeline import DetectionPipeline


def write_text_report(file_path, result):

    with open(file_path, "w", encoding="utf-8") as txt_file:

        txt_file.write(
            f"Image: {result['image']['fileName']}\n"
        )

        txt_file.write("=" * 40 + "\n\n")

        # -----------------------------------------------------
        # Validation
        # -----------------------------------------------------

        txt_file.write("Is the floor plan valid:\n")
        txt_file.write(
            f"{result['validation']['valid']}\n\n"
        )

        txt_file.write(
            f"Has bathroom: "
            f"{result['validation']['hasBathroom']}\n"
        )

        txt_file.write(
            f"Has kitchen: "
            f"{result['validation']['hasKitchen']}\n\n"
        )

        # -----------------------------------------------------
        # Rooms
        # -----------------------------------------------------

        txt_file.write("Rooms detected:\n")

        rooms = result["rooms"]

        if rooms:

            for room in rooms:

                txt_file.write(
                    f"Room id: {room['id']}, "
                    f"confidence: {room['confidence']}, "
                    f"text: {room['name']}, "
                    f"centroid: "
                    f"({room['centroid']['x']}, "
                    f"{room['centroid']['y']})\n"
                )

        else:
            txt_file.write("No rooms detected.\n")

        txt_file.write("\n")

        # -----------------------------------------------------
        # Doors
        # -----------------------------------------------------

        txt_file.write("Doors detected:\n")

        doors = result["doors"]

        if doors:

            for door in doors:

                txt_file.write(
                    f"Door {door['id']} connects room "
                    f"{door['room1']['name']} "
                    f"with id: {door['room1']['id']} "
                    f"and room "
                    f"{door['room2']['name']} "
                    f"with id: {door['room2']['id']}\n"
                )

        else:
            txt_file.write("No doors detected.\n")

        txt_file.write("\n")

        # -----------------------------------------------------
        # Windows
        # -----------------------------------------------------

        txt_file.write("Windows detected:\n")

        windows = result["windows"]

        if windows:

            for window in windows:

                bbox = window["bbox"]

                txt_file.write(
                    f"Window {window['id']}: "
                    f"bbox=("
                    f"{int(bbox['x1'])}, "
                    f"{int(bbox['y1'])}, "
                    f"{int(bbox['x2'])}, "
                    f"{int(bbox['y2'])})\n"
                )

        else:
            txt_file.write("No windows detected.\n")

        txt_file.write("\n")

        # -----------------------------------------------------
        # Openings
        # -----------------------------------------------------

        txt_file.write("Openings detected:\n")

        openings = result["openings"]

        if openings:

            for opening in openings:

                bbox = opening["bbox"]

                txt_file.write(
                    f"Opening {opening['id']} connects room "
                    f"{opening['room1']['name']} "
                    f"with id: {opening['room1']['id']} "
                    f"and room "
                    f"{opening['room2']['name']} "
                    f"with id: {opening['room2']['id']}. "
                    f"bbox=("
                    f"{int(bbox['x1'])}, "
                    f"{int(bbox['y1'])}, "
                    f"{int(bbox['x2'])}, "
                    f"{int(bbox['y2'])})\n"
                )

        else:
            txt_file.write(
                "No extra openings detected.\n"
            )


if __name__ == "__main__":

    folder_name = "image"
    result_folder = "results"
    walls_folder = "walls_results"

    os.makedirs(
        result_folder,
        exist_ok=True
    )

    os.makedirs(
        walls_folder,
        exist_ok=True
    )

    image_extensions = (
        ".png",
        ".jpg",
        ".jpeg",
        ".webp"
    )

    # ---------------------------------------------------------
    # IMPORTANT:
    # Create the pipeline ONCE.
    #
    # The MMDetection model is loaded here once,
    # before processing any images.
    # ---------------------------------------------------------

    pipeline = DetectionPipeline(
        detection_conf=0.4,
        room_conf=0.4,
        object_conf=0.3
    )

    # ---------------------------------------------------------
    # Process images
    # ---------------------------------------------------------

    for file in os.listdir(folder_name):

        if not file.lower().endswith(
            image_extensions
        ):
            continue

        path = os.path.join(
            folder_name,
            file
        )

        #print()
        #print("=" * 50)
        #print(f"Processing: {path}")
        #print("=" * 50)

        file_name = os.path.splitext(file)[0]

        wall_img_path = os.path.join(
            walls_folder,
            file_name + "_walls.png"
        )

        try:

            result, annotated_image = (
                pipeline.analyze_floor_plan(
                    image_path=path,
                    wall_output_path=wall_img_path
                )
            )

        except Exception as error:

            print(
                f"Failed to process {file}: {error}"
            )

            continue

        # -----------------------------------------------------
        # Save annotated image
        # -----------------------------------------------------

        result_image_path = os.path.join(
            result_folder,
            file_name + ".png"
        )

        cv2.imwrite(
            result_image_path,
            annotated_image
        )

        # -----------------------------------------------------
        # Save human-readable TXT result
        # -----------------------------------------------------

        result_text_path = os.path.join(
            result_folder,
            file_name + ".txt"
        )

        write_text_report(
            result_text_path,
            result
        )

        # -----------------------------------------------------
        # Save structured JSON result
        #
        # This is especially important because this JSON
        # is approximately what FastAPI will later send to .NET.
        # -----------------------------------------------------

        result_json_path = os.path.join(
            result_folder,
            file_name + ".json"
        )

        with open(
            result_json_path,
            "w",
            encoding="utf-8"
        ) as json_file:

            json.dump(
                result,
                json_file,
                indent=4
            )

       