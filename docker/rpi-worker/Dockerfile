# Use our public base image from Docker Hub
# This image already has OS libs, Python, UV, and Playwright Chromium installed.
FROM integrator/cocli-rpi-base:latest

WORKDIR /app

# Copy the application code
# This is the layer that changes frequently
COPY . .

# Install project dependencies into system python
# Since base image has uv and core libs, this is fast.
# We use --system to avoid venv overhead on the dedicated worker.
# Install playwright browsers
RUN playwright install chromium

# Install ruff for a final static analysis check
RUN pip install ruff
RUN ruff check cocli/

# Verify that the core application can be imported (Safety check)
RUN python3 -c "import cocli.main; import cocli.commands.worker; print('Import check passed!')"

# Set the entrypoint to the wrapper script

# Set COCLI_DATA_HOME to a persistent-ish location in the container
ENV COCLI_DATA_HOME=/app/cocli_data

# Create the run_worker.sh script directly in the Dockerfile
RUN echo '#!/bin/bash' > docker/rpi-worker/run_worker.sh && \
    echo 'CAMPAIGN_NAME=${CAMPAIGN_NAME:-turboship}' >> docker/rpi-worker/run_worker.sh && \
    echo 'export CAMPAIGN_NAME' >> docker/rpi-worker/run_worker.sh && \
    echo 'echo "Starting worker for campaign: $CAMPAIGN_NAME"' >> docker/rpi-worker/run_worker.sh && \
    echo 'if [ "$#" -eq 0 ]; then' >> docker/rpi-worker/run_worker.sh && \
    echo '    cocli worker scrape' >> docker/rpi-worker/run_worker.sh && \
    echo 'else' >> docker/rpi-worker/run_worker.sh && \
    echo '    "$@"' >> docker/rpi-worker/run_worker.sh && \
    echo 'fi' >> docker/rpi-worker/run_worker.sh && \
    chmod +x docker/rpi-worker/run_worker.sh

# Command to run the cocli worker
CMD ["./docker/rpi-worker/run_worker.sh"]
