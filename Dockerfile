# Use the official Playwright Python image as a parent image
# This image comes with Python, Playwright, and all necessary browser binaries pre-installed.
FROM mcr.microsoft.com/playwright/python:v1.55.0-noble

# Set environment variables
ENV PYTHONUNBUFFERED 1
ENV DEBIAN_FRONTEND=noninteractive
ENV COCLI_RUNNING_IN_FARGATE 1
# PLAYWRIGHT_BROWSERS_PATH is already set correctly by the base image

# Versioning
ARG VERSION=0.0.0
ENV COCLI_VERSION=$VERSION
RUN echo $VERSION > /app_version

# Set the working directory in the container
WORKDIR /app

# Install uv (if not already present or for specific version control)
RUN pip install uv
RUN pip install --upgrade pip --root-user-action=ignore

# Install 1Password CLI
COPY --from=1password/op:2 /usr/local/bin/op /usr/local/bin/op

# Install jq for JSON parsing in entrypoint.sh and qsv for high-performance data indexing
RUN apt-get update && \
    apt-get install -y jq wget gpg --no-install-recommends && \
    wget -O - https://dathere.github.io/qsv-deb-releases/qsv-deb.gpg | gpg --dearmor -o /usr/share/keyrings/qsv-deb.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/qsv-deb.gpg] https://dathere.github.io/qsv-deb-releases ./" | tee /etc/apt/sources.list.d/qsv.list && \
    apt-get update && \
    apt-get install -y qsv --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Copy the dependency files and application code
COPY pyproject.toml uv.lock* ./
COPY ./cocli ./cocli
COPY ./scripts ./scripts
COPY ./scripts/verify_container_sanity.py ./verify_container_sanity.py
COPY ./scripts/verify_container_config.py ./verify_container_config.py
COPY ./cocli/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Install project dependencies using uv
# We export the requirements from uv.lock to ensure we install the exact versions
RUN uv export --frozen --no-dev --no-hashes > requirements.txt && \
    uv pip install -r requirements.txt --system

# Set PYTHONPATH to include the current directory so 'import cocli' works
ENV PYTHONPATH="/app:${PYTHONPATH}"

# Expose the port the app runs on
EXPOSE 8000

# Define the command to run the application
CMD ["/usr/local/bin/entrypoint.sh"]
