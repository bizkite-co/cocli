# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED 1
ENV PLAYWRIGHT_BROWSERS_PATH /ms-playwright
ENV DEBIAN_FRONTEND=noninteractive

# Set the working directory in the container
WORKDIR /app

# Install uv
RUN pip install uv
RUN pip install --upgrade pip --root-user-action=ignore

# Install 1Password CLI
COPY --from=1password/op:2 /usr/local/bin/op /usr/local/bin/op

# Install jq for JSON parsing in entrypoint.sh
RUN apt-get update && apt-get install -y jq && rm -rf /var/lib/apt/lists/*

# Copy the dependency files and application code
COPY pyproject.toml uv.lock* ./
COPY ./cocli ./cocli
COPY ./cocli/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Install project dependencies using uv
# This also installs the project itself in editable mode
RUN uv pip install -e . --system 

# Install system dependencies for Playwright
RUN playwright install-deps

# Install Playwright browser binaries
RUN playwright install chromium

# Expose the port the app runs on
EXPOSE 8000

# Define the command to run the application
CMD ["/usr/local/bin/entrypoint.sh"]
