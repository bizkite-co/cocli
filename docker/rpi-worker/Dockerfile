# Use an official Python runtime as a parent image
# python:3.12-slim-bullseye is a good choice for Raspberry Pi (arm32v7)
# as bullseye is based on Debian 11, which is common for Raspberry Pi OS.
FROM python:3.12-slim-bullseye

# Set the working directory in the container
WORKDIR /app

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    wget \
    git \
    build-essential \
    libnss3 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libgbm1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libasound2 \
    libdbus-1-3 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxrandr2 \
    libxkbcommon0 \
    libcups2 \
    libu2f-udev \
    libvulkan1 \
    libxkbfile1 \
    libfontconfig1 \
    libfreetype6 \
    libharfbuzz0b \
    libpng16-16 \
    libjpeg62-turbo \
    libwebp6 \
    libgl1 \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Install uv (Python package manager)
RUN pip install uv

# Copy the application code
COPY . .

# Install project dependencies into system python
# We use --system so we don't need a venv inside the container
RUN uv pip install --system -e .

# Install Playwright Chromium ONLY during build time
# This saves ~500MB+ and prevents download on every startup
RUN playwright install chromium --with-deps

# Create the run_worker.sh script directly in the Dockerfile
# Optimized to run fast without re-installing
RUN echo '#!/bin/bash' > docker/rpi-worker/run_worker.sh && \
    echo 'export COCLI_SCRAPE_TASKS_QUEUE_URL="https://sqs.us-east-1.amazonaws.com/193481341784/CdkScraperDeploymentStack-ScrapeTasksQueue9836DB1F-TfprnaM0R5gs"' >> docker/rpi-worker/run_worker.sh && \
    echo 'export COCLI_ENRICHMENT_QUEUE_URL="https://sqs.us-east-1.amazonaws.com/193481341784/CdkScraperDeploymentStack-EnrichmentQueue4D4E619F-srLGUESiUDYU"' >> docker/rpi-worker/run_worker.sh && \
    echo 'export AWS_PROFILE="turboship-support"' >> docker/rpi-worker/run_worker.sh && \
    echo '# Pass arguments to the script (e.g. "cocli worker details")' >> docker/rpi-worker/run_worker.sh && \
    echo 'if [ "$#" -eq 0 ]; then' >> docker/rpi-worker/run_worker.sh && \
    echo '    cocli worker scrape' >> docker/rpi-worker/run_worker.sh && \
    echo 'else' >> docker/rpi-worker/run_worker.sh && \
    echo '    "$@"' >> docker/rpi-worker/run_worker.sh && \
    echo 'fi' >> docker/rpi-worker/run_worker.sh && \
    chmod +x docker/rpi-worker/run_worker.sh

# Command to run the cocli worker
CMD ["./docker/rpi-worker/run_worker.sh"]