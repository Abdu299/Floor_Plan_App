import os
import shutil
import tempfile

from fastapi import FastAPI, File, HTTPException, UploadFile

from detection_pipeline import DetectionPipeline


app = FastAPI(
    title="Floor Plan Detection API",
    description="API for detecting rooms, doors, windows and openings in floor plans.",
    version="1.0.0"
)




print("Starting Floor Plan Detection API...")

pipeline = DetectionPipeline(
    detection_conf=0.4,
    room_conf=0.4,
    object_conf=0.3
)

print("Detection models loaded.")




@app.get("/health")
def health():
    return {
        "status": "ok"
    }




@app.post("/detect")
async def detect_floor_plan(
    image: UploadFile = File(...)
):
    allowed_extensions = {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp"
    }

    extension = os.path.splitext(
        image.filename or ""
    )[1].lower()

    if extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail="Unsupported image type."
        )

    temp_path = None

    try:

        # Create temporary file
        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=extension
        ) as temp_file:

            temp_path = temp_file.name

            shutil.copyfileobj(
                image.file,
                temp_file
            )

        # Run your existing detection pipeline
        result, _ = pipeline.analyze_floor_plan(
            image_path=temp_path
        )

        # Keep the original uploaded filename
        result["image"]["fileName"] = image.filename

        return result

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )

    finally:

        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

        await image.close()