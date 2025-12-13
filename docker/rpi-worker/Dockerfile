# Use an official Python runtime as a parent image
# python:3.12-slim-bullseye is a good choice for Raspberry Pi (arm32v7)
# as bullseye is based on Debian 11, which is common for Raspberry Pi OS.
FROM python:3.12-slim-bullseye

# Set the working directory in the container
WORKDIR /app

# Install system dependencies for Playwright
# Playwright requires a few system libraries like libnss3, libatk-bridge2.0-0, libdrm2, etc.
# These are commonly found on Debian-based systems.
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

# Install project dependencies
# Use --system to avoid creating a new virtual environment inside the container
# uv already manages it.
RUN uv pip install --system -e .

# Install Playwright browsers (will install into the uv-managed environment)
# Playwright needs to be installed after application dependencies if it's a direct dependency
RUN playwright install --with-deps

# Create the run_worker.sh script directly in the Dockerfile
# This ensures it's always correctly configured within the container
# The AWS_PROFILE is set here because it's required for boto3 to find credentials
# It assumes credentials are mounted or available through IAM roles (Fargate case)
# For local Pi, it assumes ~/.aws/credentials will be mounted.
RUN echo '#!/bin/bash' > docker/rpi-worker/run_worker.sh && \
    echo 'export COCLI_SCRAPE_TASKS_QUEUE_URL="https://sqs.us-east-1.amazonaws.com/193481341784/CdkScraperDeploymentStack-ScrapeTasksQueue9836DB1F-TfprnaM0R5gs"' >> docker/rpi-worker/run_worker.sh && \
    echo 'export COCLI_ENRICHMENT_QUEUE_URL="https://sqs.us-east-1.amazonaws.com/193481341784/CdkScraperDeploymentStack-EnrichmentQueue4D4E619F-srLGUESiUDYU"' >> docker/rpi-worker/run_worker.sh && \
    echo 'export AWS_PROFILE="turboship-support"' >> docker/rpi-worker/run_worker.sh && \
    echo 'uv run cocli worker scrape --headed' >> docker/rpi-worker/run_worker.sh && \
    chmod +x docker/rpi-worker/run_worker.sh

# Command to run the cocli worker
# Playwright runs headless by default in Docker unless --headed is specified.
# We explicitly specify --headed for debugging/observation as per previous discussions.
CMD ["./docker/rpi-worker/run_worker.sh"]
