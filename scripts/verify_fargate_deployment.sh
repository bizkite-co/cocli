#!/bin/bash
set -e

CLUSTER="default"
SERVICE="cocli-enrichment-task-service-biq83pqs"
REGION="us-east-1"
PROFILE="turboship-support"

echo "--- Verifying Fargate Deployment ---"

# 1. Find the Running Task
echo "Finding running task for service $SERVICE..."
TASK_ARN=$(aws ecs list-tasks --cluster $CLUSTER --service-name $SERVICE --desired-status RUNNING --region $REGION --profile $PROFILE | jq -r '.taskArns[0]')

if [ "$TASK_ARN" == "null" ]; then
    echo "No running tasks found. Waiting..."
    sleep 10
    TASK_ARN=$(aws ecs list-tasks --cluster $CLUSTER --service-name $SERVICE --desired-status RUNNING --region $REGION --profile $PROFILE | jq -r '.taskArns[0]')
fi

if [ "$TASK_ARN" == "null" ]; then
    echo "Error: Still no running tasks found."
    exit 1
fi

echo "Found Task: $TASK_ARN"

# 2. Get Public IP
echo "Retrieving Public IP..."
ENI_ID=$(aws ecs describe-tasks --cluster $CLUSTER --tasks $TASK_ARN --region $REGION --profile $PROFILE | jq -r '.tasks[0].attachments[0].details[] | select(.name=="networkInterfaceId") | .value')
PUBLIC_IP=$(aws ec2 describe-network-interfaces --network-interface-ids $ENI_ID --region $REGION --profile $PROFILE | jq -r '.NetworkInterfaces[0].Association.PublicIp')

echo "Task Public IP: $PUBLIC_IP"

# 3. Wait for Health
echo "Waiting for service to be healthy..."
timeout 60 bash -c "while ! curl -s http://$PUBLIC_IP:8000/health > /dev/null; do echo 'Waiting...'; sleep 2; done"
echo "Service is READY!"

# 4. Run Enrichment Test
echo "Running Enrichment Test..."
curl -v -X POST "http://$PUBLIC_IP:8000/enrich" \
-H "Content-Type: application/json" \
-d '{
  "domain": "example.com",
  "force": true,
  "ttl_days": 30,
  "debug": false,
  "campaign_name": "turboship",
  "aws_profile_name": "turboship-support",
  "company_slug": "turbo-heat-welding-tools"
}'

echo -e "\n--- Verification Complete ---"
