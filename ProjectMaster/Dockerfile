# ============================================================
# ProjectMaster - Floor Plan Detection API
# ============================================================

FROM python:3.11-slim-bookworm


# ============================================================
# ENVIRONMENT
# ============================================================

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app


# ============================================================
# SYSTEM DEPENDENCIES
#
# MMCV may need to compile from source on platforms where
# OpenMMLab does not provide a matching wheel.
# ============================================================

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        git \
        libglib2.0-0 \
        libgl1 \
        libgomp1 \
        ninja-build \
    && rm -rf /var/lib/apt/lists/*


# ============================================================
# PYTHON BUILD TOOLS
#
# IMPORTANT:
#
# Do NOT upgrade setuptools to latest.
#
# MMCV 2.1.0 still imports pkg_resources during source build.
# pkg_resources was removed from setuptools >= 82.
# ============================================================

RUN python -m pip install \
    --no-cache-dir \
    --upgrade \
    pip \
    wheel \
    "setuptools==80.9.0"


# ============================================================
# VERIFY pkg_resources EXISTS
# ============================================================

RUN python -c "\
import pkg_resources; \
print('pkg_resources available')"


# ============================================================
# COPY DEPENDENCY FILES FIRST
# ============================================================

COPY requirements.txt /app/requirements.txt
COPY install_openmmlab.sh /app/install_openmmlab.sh

RUN chmod +x /app/install_openmmlab.sh


# ============================================================
# NUMPY FIRST
#
# Keep NumPy 1.x because our tested PyTorch stack is not
# compatible with NumPy 2.x.
# ============================================================

RUN python -m pip install \
    --no-cache-dir \
    "numpy==1.26.4"


# ============================================================
# STANDARD DEPENDENCIES
# ============================================================

RUN python -m pip install \
    --no-cache-dir \
    -r /app/requirements.txt


# ============================================================
# IMPORTANT
#
# Installing dependencies can sometimes modify setuptools.
# Pin it again before compiling MMCV.
# ============================================================

RUN python -m pip install \
    --no-cache-dir \
    --force-reinstall \
    "setuptools==80.9.0"


# ============================================================
# VERIFY BUILD ENVIRONMENT
# ============================================================

RUN python - <<'PY'
import numpy
import setuptools
import pkg_resources
import torch

print("NumPy:", numpy.__version__)
print("Setuptools:", setuptools.__version__)
print("PyTorch:", torch.__version__)
print("pkg_resources: available")

assert numpy.__version__ == "1.26.4"
PY


# ============================================================
# OPENMMLAB
# ============================================================

RUN /app/install_openmmlab.sh

# ============================================================
# FILELOCK
#
# Newer Ultralytics imports AsyncFileLock.
# Pin to the same version used by our known-working
# local environment.
# ============================================================

RUN python -m pip install \
    --no-cache-dir \
    --upgrade \
    "filelock==3.32.2"


# Verify AsyncFileLock is available
RUN python - <<'PY'
import filelock
from filelock import AsyncFileLock

print("filelock:", filelock.__version__)
print("AsyncFileLock: OK")
PY

# ============================================================
# VERIFY ML STACK
# ============================================================

RUN python - <<'PY'

import numpy
import torch
import mmcv
import mmengine
import mmdet
import easyocr

print()
print("============================================")
print(" ProjectMaster ML environment")
print("============================================")

print("NumPy:", numpy.__version__)
print("PyTorch:", torch.__version__)
print("MMCV:", mmcv.__version__)
print("MMEngine:", mmengine.__version__)
print("MMDetection:", mmdet.__version__)
print("EasyOCR: OK")

PY


# ============================================================
# DOWNLOAD EASYOCR MODEL DURING BUILD
#
# This means EasyOCR does not need to download the model when
# the container handles its first request.
# ============================================================

RUN python - <<'PY'

import easyocr

print("Preparing EasyOCR model...")

easyocr.Reader(
    ["en"],
    gpu=False
)

print("EasyOCR model ready.")

PY


# ============================================================
# COPY PROJECT
# ============================================================

COPY . /app


# ============================================================
# REMOVE LOCAL DEVELOPMENT FILES IF THEY WERE COPIED
# ============================================================

RUN rm -rf \
    /app/venvy \
    /app/.venv \
    /app/__pycache__


# ============================================================
# VERIFY MODEL WEIGHTS
# ============================================================

RUN test -f /app/weights/best.pt || \
    (echo "ERROR: weights/best.pt is missing" && exit 1)


RUN test -f /app/weights/cascade_swin_latest.pth || \
    (echo "ERROR: weights/cascade_swin_latest.pth is missing" && exit 1)


# ============================================================
# PORT
# ============================================================

EXPOSE 8000


# ============================================================
# START FASTAPI
# ============================================================

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]