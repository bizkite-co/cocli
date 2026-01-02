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

echo "Deploying enrichment service for campaign: $CAMPAIGN_NAME"

# 2. Resolve AWS Configuration from campaign config.toml
# We use a python snippet to reliably extract values from the TOML
AWS_PROFILE=$(./.venv/bin/python -c "from cocli.core.config import load_campaign_config; config = load_campaign_config('$CAMPAIGN_NAME'); print(config.get('aws', {}).get('profile', ''))")
AWS_REGION=$(./.venv/bin/python -c "from cocli.core.config import load_campaign_config; config = load_campaign_config('$CAMPAIGN_NAME'); print(config.get('aws', {}).get('region', 'us-east-1'))")
AWS_ACCOUNT=$(./.venv/bin/python -c "from cocli.core.config import load_campaign_config; config = load_campaign_config('$CAMPAIGN_NAME'); print(config.get('aws', {}).get('account', ''))")

if [ -z "$AWS_PROFILE" ]; then
    echo "Error: AWS profile not found in campaign config for '$CAMPAIGN_NAME'."
    exit 1
fi

if [ -z "$AWS_ACCOUNT" ]; then
    echo "Error: AWS account ID not found in campaign config for '$CAMPAIGN_NAME'."
    exit 1
fi

ECR_REPO_NAME="cocli-enrichment-service"
ECR_REPO_URI="$AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME"

echo "Using AWS Profile: $AWS_PROFILE"
echo "Using AWS Region:  $AWS_REGION"
echo "Using ECR URI:     $ECR_REPO_URI"

echo "--- 1. Ensuring ECR Repository Exists ---"
aws ecr describe-repositories --repository-names "$ECR_REPO_NAME" --region "$AWS_REGION" --profile "$AWS_PROFILE" > /dev/null 2>&1 || \
aws ecr create-repository --repository-name "$ECR_REPO_NAME" --region "$AWS_REGION" --profile "$AWS_PROFILE"

echo "--- 2. Authenticating with ECR ---"
aws ecr get-login-password --region $AWS_REGION --profile $AWS_PROFILE | docker login --username AWS --password-stdin $ECR_REPO_URI

echo "--- 3. Tagging and Pushing Image to ECR ---"
# Assumes image 'enrichment-service:latest' was built by Makefile (make docker-build)
docker tag enrichment-service:latest $ECR_REPO_URI:latest
docker push $ECR_REPO_URI:latest

echo "--- 4. Deploying Infrastructure with CDK ---"
export NODE_OPTIONS="--max-old-space-size=8192"
cd cdk_scraper_deployment

# Ensure venv is active and deps are installed
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    uv venv
fi
source .venv/bin/activate
pip install -r requirements.txt

# Deploy using the profile and campaign context
echo "Running CDK Deploy..."
DEPLOY_TIMESTAMP=$(date +%s)
cdk deploy --profile $AWS_PROFILE --require-approval never -c campaign=$CAMPAIGN_NAME -c deploy_timestamp=$DEPLOY_TIMESTAMP

echo "--- 5. Forcing New ECS Deployment to pick up latest image/task definition ---"
ECS_CLUSTER_NAME="ScraperCluster"
ECS_SERVICE_NAME="EnrichmentService"

aws ecs update-service \
    --cluster $ECS_CLUSTER_NAME \
    --service $ECS_SERVICE_NAME \
    --force-new-deployment \
    --profile $AWS_PROFILE \
    --region $AWS_REGION

echo "--- 6. Waiting for ECS Service to become stable ---"
aws ecs wait services-stable \
    --cluster $ECS_CLUSTER_NAME \
    --service $ECS_SERVICE_NAME \
    --profile $AWS_PROFILE \
    --region $AWS_REGION

echo "--- 7. Running Post-Deployment Verification ---"
cd ..
./scripts/verify_fargate_deployment.sh "$CAMPAIGN_NAME"
if [ $? -ne 0 ]; then
    echo "ERROR: Basic Fargate health check failed!"
    exit 1
fi

echo "--- 8. Running End-to-End Enrichment Test with google.com ---"
python scripts/enrich_domain.py "google.com"
if [ $? -ne 0 ]; then
    echo "ERROR: End-to-end enrichment test with google.com failed!"
    exit 1
fi

echo "--- Deployment and Verification Complete! ---"
