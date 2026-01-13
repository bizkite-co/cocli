# Use the official Microsoft Playwright image
FROM mcr.microsoft.com/playwright/python:v1.55.0-noble

WORKDIR /app

# Install system dependencies needed for pandas/numpy on ARM
RUN apt-get update && apt-get install -y \
    libatlas-base-dev \
    && rm -rf /var/lib/apt/lists/*

# Install UV for fast dependency management
RUN pip install uv

# Copy the dependency files first for caching
COPY pyproject.toml uv.lock* ./

# Export requirements (including 'full' for pandas/numpy) and install them
RUN uv export --frozen --no-dev --no-hashes --extra full > requirements.txt && \
    uv pip install -r requirements.txt --system && \
    uv pip install ruff --system

# Copy the application code
COPY . .

# Install the package into the system python
RUN uv pip install . --system --no-deps

# Final static analysis check
RUN ruff check cocli/

# Verify that the core application can be imported (Safety check)
# We run this from /tmp to ensure we are testing the installed package
RUN cd /tmp && python3 -c "import cocli.main; import cocli.commands.worker; print('Import check passed!')"

# Set COCLI_DATA_HOME to a persistent-ish location in the container
ENV COCLI_DATA_HOME=/app/cocli_data

# Create the run_worker.sh script directly in the Dockerfile
RUN echo '#!/bin/bash' > docker/rpi-worker/run_worker.sh && \
    echo 'CAMPAIGN_NAME=${CAMPAIGN_NAME:-turboship}' >> docker/rpi-worker/run_worker.sh && \
    echo 'export CAMPAIGN_NAME' >> docker/rpi-worker/run_worker.sh && \
    echo 'echo "Starting worker for campaign: $CAMPAIGN_NAME"' >> docker/rpi-worker/run_worker.sh && \
    echo 'if [ "$#" -eq 0 ]; then' >> docker/rpi-worker/run_worker.sh && \
    echo '    cocli worker gm-list' >> docker/rpi-worker/run_worker.sh && \
    echo 'else' >> docker/rpi-worker/run_worker.sh && \
    echo '    "$@"' >> docker/rpi-worker/run_worker.sh && \
    echo 'fi' >> docker/rpi-worker/run_worker.sh && \
    chmod +x docker/rpi-worker/run_worker.sh

# Command to run the cocli worker
CMD ["./docker/rpi-worker/run_worker.sh"]
