#!/bin/bash
# Wrapper script for cocli to set LD_LIBRARY_PATH for CUDA

# Determine the base directory of the project
BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$BASE_DIR/.venv"

# Find the nvidia libraries directory
# We look for the 'nvidia' directory inside site-packages
NVIDIA_PATH="$(find "$VENV_DIR" -type d -name "nvidia" | head -n 1)"

if [ -n "$NVIDIA_PATH" ]; then
    # Set the LD_LIBRARY_PATH
    # Add the paths to cublas, cudnn, and cuda_nvrtc
    export LD_LIBRARY_PATH="$NVIDIA_PATH/cublas/lib:$NVIDIA_PATH/cudnn/lib:$NVIDIA_PATH/cuda_nvrtc/lib:$LD_LIBRARY_PATH"
fi

# Execute cocli
# Set data home
export COCLI_DATA_HOME="$BASE_DIR/data"
"$VENV_DIR/bin/cocli" "$@"
