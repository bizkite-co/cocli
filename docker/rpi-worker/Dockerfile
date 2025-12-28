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
RUN uv pip install --system -e .

# Create the run_worker.sh script directly in the Dockerfile
RUN echo '#!/bin/bash' > docker/rpi-worker/run_worker.sh && \
    echo 'CAMPAIGN_NAME=${CAMPAIGN_NAME:-turboship}' >> docker/rpi-worker/run_worker.sh && \
    echo '# Pass arguments to the script (e.g. "cocli worker details")' >> docker/rpi-worker/run_worker.sh && \
    echo 'if [ "$#" -eq 0 ]; then' >> docker/rpi-worker/run_worker.sh && \
    echo '    cocli worker scrape --campaign "$CAMPAIGN_NAME"' >> docker/rpi-worker/run_worker.sh && \
    echo 'else' >> docker/rpi-worker/run_worker.sh && \
    echo '    # If the user passed "cocli worker details", we should still append the campaign if it was not in args' >> docker/rpi-worker/run_worker.sh && \
    echo '    if [[ "$*" == *"worker"* ]] && [[ "$*" != *"--campaign"* ]] && [[ "$*" != *"-c "* ]]; then' >> docker/rpi-worker/run_worker.sh && \
    echo '        "$@" --campaign "$CAMPAIGN_NAME"' >> docker/rpi-worker/run_worker.sh && \
    echo '    else' >> docker/rpi-worker/run_worker.sh && \
    echo '        "$@"' >> docker/rpi-worker/run_worker.sh && \
    echo '    fi' >> docker/rpi-worker/run_worker.sh && \
    echo 'fi' >> docker/rpi-worker/run_worker.sh && \
    chmod +x docker/rpi-worker/run_worker.sh

# Command to run the cocli worker
CMD ["./docker/rpi-worker/run_worker.sh"]
