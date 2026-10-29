# AdventureForge — Docker Image
# Multi-stage build for web editor + pygame runtime + AI tools

# ============================================================================
# Base stage with system dependencies
# ============================================================================
FROM python:3.12-slim AS base

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    wget \
    ca-certificates \
    # For pygame
    libsdl2-2.0-0 \
    libsdl2-image-2.0-0 \
    libsdl2-mixer-2.0-0 \
    libsdl2-ttf-2.0-0 \
    libfreetype6 \
    libportmidi0 \
    # For pillow
    libjpeg-dev \
    libpng-dev \
    libwebp-dev \
    # For numpy/scipy
    libopenblas-dev \
    # For headless display
    xvfb \
    xauth \
    # For building some packages
    build-essential \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN groupadd -r appuser && useradd -r -g appuser -m -d /home/appuser -s /bin/bash appuser

WORKDIR /app

# ============================================================================
# Python dependencies stage
# ============================================================================
FROM base AS python-deps

COPY requirements.txt ./
# Fail loudly if the dependency install breaks - a masked failure here only
# surfaces later as an ImportError at runtime.
RUN pip install --no-cache-dir -r requirements.txt

# ============================================================================
# Application stage
# ============================================================================
FROM python-deps AS app

# Copy application code (includes the vendored sprite_slicer/ package)
COPY --chown=appuser:appuser . .

# Create required directories
RUN mkdir -p /app/data/assets/{backgrounds,items,sprites,sounds,music} \
    /app/data/test_grid \
    /app/static \
    /app/__pycache__ \
    && chown -R appuser:appuser /app/data /app/static

# Environment variables (can be overridden at runtime)
ENV ADVENTURE_FORGE_HOST=0.0.0.0 \
    ADVENTURE_FORGE_PORT=8780 \
    ADVENTURE_FORGE_SPRITE_SLICER_PATH=/app/sprite_slicer \
    ADVENTURE_FORGE_JETSON_MODELS_DIR=/app/models \
    ADVENTURE_FORGE_SD_CPP_DIR=/app/stable-diffusion.cpp \
    ADVENTURE_FORGE_JETSON_DOCKER_IMAGE=hotbreath/pytorch:2.12-r39.2.tegra-aarch64-cu132-24.04-cmake \
    DISPLAY=:99 \
    PYTHONPATH=/app

# Expose port
EXPOSE 8780

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8780/health || exit 1

# Switch to app user
USER appuser

# Default command
CMD ["python3", "app.py"]

# ============================================================================
# Jetson GPU stage (for NVIDIA Jetson devices with CUDA)
# ============================================================================
FROM app AS jetson

USER root

# Install NVIDIA Container Toolkit dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    nvidia-container-toolkit \
    && rm -rf /var/lib/apt/lists/*

# Build stable-diffusion.cpp for Jetson
RUN git clone --depth 1 https://github.com/leejet/stable-diffusion.cpp.git /app/stable-diffusion.cpp \
    && cd /app/stable-diffusion.cpp \
    && mkdir -p build && cd build \
    && cmake .. -DCMAKE_BUILD_TYPE=Release -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES="87" \
    && make -j$(nproc) \
    && chown -R appuser:appuser /app/stable-diffusion.cpp

USER appuser

# Jetson-specific entrypoint
CMD ["python3", "app.py"]

# ============================================================================
# Development stage (with extra tools)
# ============================================================================
FROM python-deps AS dev

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
    vim \
    htop \
    net-tools \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/*

# Development dependencies (pytest, black, ruff, mypy) already come from
# requirements.txt in the python-deps stage.
RUN pip install --no-cache-dir --upgrade pip

USER appuser

CMD ["python3", "app.py"]