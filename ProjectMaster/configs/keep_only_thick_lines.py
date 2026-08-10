import cv2
import numpy as np


def keep_only_thick_lines(
    input_path,
    output_path=None,
    threshold_value=120,
    min_thickness=8,
    min_area=500,
    min_length=40
):
    gray = cv2.imread(input_path, cv2.IMREAD_GRAYSCALE)

    if gray is None:
        raise ValueError(f"Could not read image: {input_path}")

    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    # Invert: black walls become white, white background becomes black
    _, binary = cv2.threshold(
        gray,
        threshold_value,
        255,
        cv2.THRESH_BINARY_INV
    )

    # Keep only thick parts
    dist = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
    core = np.uint8(dist >= (min_thickness / 2)) * 255

    # Restore thickness
    kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (min_thickness, min_thickness)
    )
    thick_lines = cv2.dilate(core, kernel, iterations=1)

    # Remove small objects
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        thick_lines,
        connectivity=8
    )

    cleaned = np.zeros_like(thick_lines)

    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        width = stats[i, cv2.CC_STAT_WIDTH]
        height = stats[i, cv2.CC_STAT_HEIGHT]

        if area >= min_area and max(width, height) >= min_length:
            cleaned[labels == i] = 255

    # Smooth small gaps
    close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, close_kernel)

    if output_path is not None:
        cv2.imwrite(output_path, cleaned)
        #print(f"Saved result to: {output_path}")

    return cleaned


def main():
    input_path = "floorplan.png"
    output_path = "walls_only.png"

    keep_only_thick_lines(
        input_path=input_path,
        output_path=output_path,
        threshold_value=120,
        min_thickness=8,
        min_area=500,
        min_length=40
    )


if __name__ == "__main__":
    main()
