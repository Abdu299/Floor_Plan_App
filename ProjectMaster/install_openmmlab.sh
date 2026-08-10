#!/usr/bin/env bash

set -e


echo ""
echo "============================================"
echo " ProjectMaster - OpenMMLab Setup"
echo "============================================"
echo ""


# ============================================================
# CHECK PYTHON
# ============================================================

echo "[1/7] Python version"

python --version


# ============================================================
# CHECK NUMPY
# ============================================================

echo ""
echo "[2/7] Checking NumPy"

python - <<'PY'
import numpy

print("NumPy:", numpy.__version__)

if numpy.__version__ != "1.26.4":
    raise RuntimeError(
        f"Expected NumPy 1.26.4, found {numpy.__version__}"
    )
PY


# ============================================================
# CHECK PYTORCH
# ============================================================

echo ""
echo "[3/7] Checking PyTorch"

python - <<'PY'
import torch

print("PyTorch:", torch.__version__)
print("CUDA:", torch.version.cuda)
PY


# ============================================================
# INSTALL OPENMIM
# ============================================================

echo ""
echo "[4/7] Installing OpenMIM"

python -m pip install \
    --no-cache-dir \
    "openmim"


# ============================================================
# INSTALL MMENGINE
# ============================================================

echo ""
echo "[5/7] Installing MMEngine"

python -m pip install \
    --no-cache-dir \
    "mmengine==0.10.7"


# ============================================================
# INSTALL MMCV
# ============================================================
#
# IMPORTANT:
#
# On some platforms OpenMMLab does not provide a precompiled
# wheel for our Python/PyTorch/CPU combination.
#
# In that case MMCV is compiled from source.
#
# MMCV 2.1.0's setup script still imports pkg_resources.
# pkg_resources was removed from setuptools >= 82.
#
# The Docker image therefore uses setuptools 80.9.0.
#
# --no-build-isolation is CRITICAL:
#
# Without it, pip creates a temporary build environment and
# installs a new setuptools version there, bringing the
# pkg_resources error back.
# ============================================================

echo ""
echo "[6/7] Installing MMCV 2.1.0"

python -m pip install \
    --no-cache-dir \
    --no-build-isolation \
    "mmcv==2.1.0"


# ============================================================
# INSTALL / VERIFY MMDETECTION
# ============================================================

echo ""
echo "[7/7] Installing MMDetection"

python -m pip install \
    --no-cache-dir \
    "mmdet==3.3.0"


# ============================================================
# VERIFY
# ============================================================

echo ""
echo "============================================"
echo " Verifying OpenMMLab installation"
echo "============================================"
echo ""


python - <<'PY'

import numpy
import torch
import mmcv
import mmengine
import mmdet

print("NumPy:       ", numpy.__version__)
print("PyTorch:     ", torch.__version__)
print("MMCV:        ", mmcv.__version__)
print("MMEngine:    ", mmengine.__version__)
print("MMDetection: ", mmdet.__version__)

assert numpy.__version__ == "1.26.4"
assert mmcv.__version__ == "2.1.0"
assert mmengine.__version__ == "0.10.7"
assert mmdet.__version__ == "3.3.0"

print()
print("OpenMMLab installation successful.")

PY


echo ""
echo "============================================"
echo " OpenMMLab setup complete"
echo "============================================"
echo ""