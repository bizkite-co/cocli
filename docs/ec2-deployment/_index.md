# EC2 Deployment Plan for `cocli`

This document outlines a plan for deploying the `cocli` application to an AWS EC2 instance. This approach offers a simpler initial cloud migration path compared to Fargate/serverless, while still addressing key concerns like redeployment, service management, and data persistence.

## Objective

To deploy the `cocli` application, including its Google Maps scraper and website enrichment service, to an AWS EC2 instance. The deployment should allow for easy updates, robust service management, and resilience against instance failures (especially for spot instances) through S3-backed data storage.

## Prerequisites

*   **AWS Account and CLI:** Configured with appropriate permissions.
*   **EC2 Instance:** A running EC2 instance (e.g., Ubuntu, Amazon Linux 2023) with sufficient resources (CPU, RAM) to run Playwright and Python processes. Consider `t3.medium` or `t3.large` for Playwright.
*   **SSH Access:** An SSH key pair configured for secure access to the EC2 instance.
*   **Security Group:** An EC2 Security Group allowing inbound SSH (port 22) and outbound HTTP/HTTPS (ports 80, 443) for web scraping. If the enrichment service is exposed, additional inbound rules might be needed.

## Deployment Steps

### 1. EC2 Instance Setup

1.  **Launch Instance:** Launch an EC2 instance with your chosen AMI and instance type.
2.  **Install System Dependencies:** SSH into the instance and install necessary software:
    *   **Python:** Ensure Python 3.10+ is installed.
    *   **`uv`:** Install `uv` globally or via `pipx`.
    *   **Docker:** Install Docker for running the enrichment service container.
    *   **`git`:** For cloning the repository.
    *   **Playwright System Dependencies:** Install browser dependencies (e.g., `apt-get install -y chromium-browser` or similar for other browsers).
    *   **`aws-cli`:** For S3 synchronization.

### 2. Code Deployment

1.  **Initial Clone:**
    ```bash
    git clone https://github.com/bizkite-co/cocli.git /opt/cocli
    cd /opt/cocli
    ```
2.  **Subsequent Updates:** For future code updates, use `git pull` or `rsync` from your local machine:
    ```bash
    # From local machine
    rsync -avz --exclude='.git' --exclude='.venv' /path/to/local/cocli/ user@your-ec2-ip:/opt/cocli/
    ```

### 3. Application Environment Setup

1.  **Create Virtual Environment:**
    ```bash
    cd /opt/cocli
    uv venv
    source .venv/bin/activate
    ```
2.  **Install Python Dependencies:**
    ```bash
    uv pip install -e .
    ```
3.  **Install Playwright Browsers:**
    ```bash
    playwright install chromium # or other browsers as needed
    ```

### 4. Data Storage Migration (`cocli_data/` to S3)

To ensure resilience against spot instance interruptions and allow for scalable storage, the `cocli_data/` directory will be moved to S3.

1.  **Create S3 Bucket:** Create a dedicated S3 bucket (e.g., `cocli-data-bucket`) in your AWS account.
2.  **Configure `COCLI_DATA_HOME`:** On the EC2 instance, set the `COCLI_DATA_HOME` environment variable to point to a local directory that will be synchronized with S3.
    ```bash
    export COCLI_DATA_HOME=/mnt/cocli_data # Or any preferred local path
    mkdir -p /mnt/cocli_data
    ```
3.  **Implement S3-backed Domain Manager:**
    *   As outlined in `task.md`, implement the `S3DomainManager` for the website enrichment service. This manager will directly interact with S3 for domain indexing and status, using S3 object tags for metadata.
    *   The Google Maps scraper will continue to write its raw output (e.g., `prospects.csv`) to the local `COCLI_DATA_HOME` directory.
4.  **S3 Synchronization:**
    *   **Initial Sync:** Copy existing local data to S3.
        ```bash
        aws s3 sync /mnt/cocli_data s3://cocli-data-bucket --delete
        ```
    *   **Continuous Sync:** Implement a `cron` job on the EC2 instance to periodically synchronize the local `COCLI_DATA_HOME` with the S3 bucket. This ensures data written locally by the Google Maps scraper is persisted to S3.
        ```bash
        # Example cron entry (run every 5 minutes)
        */5 * * * * /usr/bin/aws s3 sync /mnt/cocli_data s3://cocli-data-bucket
        ```
    *   **IAM Role:** Attach an IAM role to the EC2 instance with permissions to read/write to the S3 bucket.

### 5. Service Management (Systemd)

We will use `systemd` to manage the `cocli` application components as background services, ensuring they start on boot and restart on failure.

1.  **Create Systemd Unit Files:**
    *   **`cocli-enrichment.service` (for the Dockerized enrichment service):**
        ```ini
        # /etc/systemd/system/cocli-enrichment.service
        [Unit]
        Description=CoCLI Website Enrichment Service
        After=docker.service
        Requires=docker.service

        [Service]
        ExecStartPre=-/usr/bin/docker rm -f cocli-enrichment
        ExecStart=/usr/bin/docker run --name cocli-enrichment -p 8000:8000 -e COCLI_DATA_HOME=/mnt/cocli_data enrichment-service:latest
        ExecStop=/usr/bin/docker stop cocli-enrichment
        Restart=on-failure
        RestartSec=10
        User=root # Or a dedicated user if configured
        Group=root # Or a dedicated group

        [Install]
        WantedBy=multi-user.target
        ```
    *   **`cocli-gmaps-scraper.service` (for the Google Maps scraper, if running continuously):**
        *   This would be more complex as `achieve-goal` is a pipeline. A simpler approach might be to run `achieve-goal` on demand via SSH or trigger it via a cron job. If a continuous "trickle-scrape" is desired, it would need to be refactored into a long-running process or orchestrated by a separate mechanism (e.g., AWS Step Functions, which is part of the Fargate plan). For initial EC2 deployment, running `achieve-goal` on demand is sufficient.

2.  **Enable and Start Services:**
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl enable cocli-enrichment.service
    sudo systemctl start cocli-enrichment.service
    sudo systemctl status cocli-enrichment.service
    ```

### 6. Running `achieve-goal`

*   You can execute `cocli campaign achieve-goal` commands directly via SSH.
*   For long-running scraping sessions, consider using `tmux` or `screen` to keep the session alive even if your SSH connection drops.

## Redeployment Strategy

1.  **Update Code:**
    ```bash
    cd /opt/cocli
    git pull
    # Or rsync from local machine
    ```
2.  **Rebuild/Restart Enrichment Service:**
    ```bash
    sudo systemctl stop cocli-enrichment.service
    docker build --no-cache -t enrichment-service:latest /opt/cocli # Rebuild image
    sudo systemctl start cocli-enrichment.service
    ```
3.  **Restart Google Maps Scraper (if running as a service):**
    ```bash
    # If running as a systemd service
    sudo systemctl restart cocli-gmaps-scraper.service
    ```

## Spot Instance Considerations

*   **Statelessness:** The S3-backed data storage is crucial here. Ensure all critical data is written to S3. The local `COCLI_DATA_HOME` should be considered ephemeral.
*   **Restartability:** `systemd` services are configured to `Restart=on-failure`, which helps with unexpected instance terminations.
*   **Checkpointing:** For long-running scraping tasks, consider implementing checkpointing to S3 so that a new instance can resume from the last known state.

## Monitoring

*   **CloudWatch:** Monitor EC2 instance metrics (CPU, memory, network).
*   **Application Logs:** Configure `cocli` to write logs to files, and use CloudWatch Logs Agent to push them to CloudWatch Logs for centralized monitoring and alerting.

This plan provides a robust framework for deploying `cocli` on EC2, addressing the user's concerns about redeployment, service management, and data persistence.
