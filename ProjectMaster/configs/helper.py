import PIL
import pandas as pd

def count_detected_objects(model, filtered_boxes):
    """
    Count detected objects and return a dictionary of counts.
    """
    object_counts = {}
    for box in filtered_boxes:
        # Extract class label of detected object
        label = model.names[int(box.cls)]
        # Update count in dictionary
        object_counts[label] = object_counts.get(label, 0) + 1
    return object_counts

def generate_csv(object_counts, filename="results.csv"):
    csv_data = pd.DataFrame(
        list(object_counts.items()),
        columns=['Label', 'Count']
    )
    
    csv_data.to_csv(filename, index=False)
    return filename