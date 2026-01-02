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

# 3. Use Service URL if available, otherwise fallback to Public IP
if [ -n "$SERVICE_URL" ]; then
    echo "Using configured Service URL: $SERVICE_URL"
    TARGET_URL="$SERVICE_URL"
else
    CLUSTER="ScraperCluster"
    SERVICE="EnrichmentService"

    echo "No Service URL configured. Attempting to find Fargate Public IP..."
    # ... (existing task finding logic) ...
    TASK_ARN=$(aws ecs list-tasks --cluster $CLUSTER --service-name $SERVICE --desired-status RUNNING --region $REGION --profile $PROFILE | jq -r '.taskArns[0]')
    # ... (logic to get public IP) ...
    ENI_ID=$(aws ecs describe-tasks --cluster $CLUSTER --tasks $TASK_ARN --region $REGION --profile $PROFILE | jq -r '.tasks[0].attachments[0].details[] | select(.name=="networkInterfaceId") | .value')
    PUBLIC_IP=$(aws ec2 describe-network-interfaces --network-interface-ids $ENI_ID --region $REGION --profile $PROFILE | jq -r '.NetworkInterfaces[0].Association.PublicIp')
    TARGET_URL="http://$PUBLIC_IP:8000"
fi

echo "--- Verifying Fargate Deployment for $CAMPAIGN_NAME ---"
echo "Target URL: $TARGET_URL"

# 4. Wait for Health
echo "Waiting for service to be healthy..."
timeout 60 bash -c "while ! curl -s $TARGET_URL/health > /dev/null; do echo 'Waiting...'; sleep 2; done"
echo "Service is READY!"

# 5. Run Enrichment Test
echo "Running Enrichment Test..."
curl -v -X POST "$TARGET_URL/enrich" \
    -H "Content-Type: application/json" \
    -d "{
  \"domain\": \"google.com\",
  \"force\": true,
  \"ttl_days\": 30,
  \"debug\": false,
  \"campaign_name\": \"$CAMPAIGN_NAME\",
  \"aws_profile_name\": \"$PROFILE\",
  \"company_slug\": \"$COMPANY_SLUG\"
}"

echo -e "\n--- Verification Complete ---"
