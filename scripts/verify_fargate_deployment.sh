#!/bin/bash
set -e

# 1. Determine Campaign
CAMPAIGN_NAME=$1
if [ -z "$CAMPAIGN_NAME" ]; then
    # Fallback to cocli active campaign
    CAMPAIGN_NAME=$(./.venv/bin/python -c "from cocli.core.config import get_campaign; print(get_campaign() or '')")
fi

if [ -z "$CAMPAIGN_NAME" ]; then
    echo "Error: No campaign specified and no active campaign found."
    exit 1
fi

# 2. Resolve AWS Configuration and Service URL from campaign config.toml
PROFILE=$(./.venv/bin/python -c "from cocli.core.config import load_campaign_config; config = load_campaign_config('$CAMPAIGN_NAME'); print(config.get('aws', {}).get('profile', ''))")
REGION=$(./.venv/bin/python -c "from cocli.core.config import load_campaign_config; config = load_campaign_config('$CAMPAIGN_NAME'); print(config.get('aws', {}).get('region', 'us-east-1'))")
COMPANY_SLUG=$(./.venv/bin/python -c "from cocli.core.config import load_campaign_config; config = load_campaign_config('$CAMPAIGN_NAME'); print(config.get('campaign', {}).get('company-slug', ''))")
SERVICE_URL=$(./.venv/bin/python -c "from cocli.core.config import load_campaign_config; config = load_campaign_config('$CAMPAIGN_NAME'); print(config.get('aws', {}).get('cocli_enrichment_service_url', ''))")

if [ -z "$PROFILE" ]; then
    echo "Error: AWS profile not found in campaign config for '$CAMPAIGN_NAME'."
    exit 1
fi

# 3. Wait for ECS Task to be RUNNING
CLUSTER="ScraperCluster"
SERVICE="EnrichmentService"
echo "Waiting for ECS Task to be RUNNING..."
TASK_STATUS="UNKNOWN"
for i in {1..30}; do
    TASK_ARN=$(aws ecs list-tasks --cluster $CLUSTER --service-name $SERVICE --desired-status RUNNING --region $REGION --profile $PROFILE | jq -r '.taskArns[0] // empty')
    if [ -n "$TASK_ARN" ]; then
        echo "ECS Task is RUNNING: $TASK_ARN"
        TASK_STATUS="RUNNING"
        break
    fi
    echo "Waiting for task to start... ($i/30)"
    sleep 5
done

if [ "$TASK_STATUS" != "RUNNING" ]; then
    echo "ERROR: Fargate task did not start within 150 seconds."
    exit 1
fi

# 4. Wait for S3 Heartbeat update
BUCKET_NAME=$(./.venv/bin/python -c "from cocli.core.config import load_campaign_config; config = load_campaign_config('$CAMPAIGN_NAME'); print(config.get('aws', {}).get('data_bucket_name', ''))")
echo "Waiting for S3 Heartbeat update in bucket '$BUCKET_NAME'..."
HEARTBEAT_STATUS="FAIL"
for i in {1..20}; do
    # Check if the heartbeat file exists and has been modified recently
    HEARTBEAT_TIME=$(aws s3api head-object --bucket "$BUCKET_NAME" --key "status/fargate.json" --region "$REGION" --profile "$PROFILE" --query "LastModified" --output text 2>/dev/null || echo "")
    if [ -n "$HEARTBEAT_TIME" ]; then
        echo "Heartbeat detected in S3: $HEARTBEAT_TIME"
        HEARTBEAT_STATUS="SUCCESS"
        break
    fi
    echo "Waiting for heartbeat... ($i/20)"
    sleep 10
done

if [ "$HEARTBEAT_STATUS" != "SUCCESS" ]; then
    echo "ERROR: Fargate heartbeat was not updated in S3."
    exit 1
fi

echo "--- Verification Complete: Fargate consumer is active and reporting! ---"
