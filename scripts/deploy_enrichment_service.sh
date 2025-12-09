#!/bin/bash
set -e

# Configuration
AWS_REGION="us-east-1"
AWS_PROFILE="turboship-support"
ECR_REPO_URI="193481341784.dkr.ecr.us-east-1.amazonaws.com/cocli-enrichment-service"

echo "--- 1. Authenticating with ECR ---"
aws ecr get-login-password --region $AWS_REGION --profile $AWS_PROFILE | docker login --username AWS --password-stdin $ECR_REPO_URI

echo "--- 2. Tagging and Pushing Image to ECR ---"
# Assumes image 'enrichment-service:latest' was built by Makefile (make docker-build)
# The Makefile builds 'enrichment-service', so we tag it for ECR.
docker tag enrichment-service:latest $ECR_REPO_URI:latest
docker push $ECR_REPO_URI:latest

echo "--- 3. Deploying Infrastructure with CDK ---"
export NODE_OPTIONS="--max-old-space-size=8192"
cd cdk_scraper_deployment

# Ensure venv is active and deps are installed
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    uv venv
fi
source .venv/bin/activate
pip install -r requirements.txt

# Deploy using the profile
echo "Running CDK Deploy..."
cdk deploy --profile $AWS_PROFILE --require-approval never

echo "--- 4. Forcing New ECS Deployment to pick up latest image/task definition ---"
# Retrieve Cluster and Service Name from CDK outputs or hardcode if stable
# Assuming the ECS Service name is 'EnrichmentService' and Cluster is 'ScraperCluster'
ECS_CLUSTER_NAME="ScraperCluster"
ECS_SERVICE_NAME="EnrichmentService"

aws ecs update-service \
    --cluster $ECS_CLUSTER_NAME \
    --service $ECS_SERVICE_NAME \
    --force-new-deployment \
    --profile $AWS_PROFILE

echo "--- 5. Waiting for ECS Service to become stable ---"
aws ecs wait services-stable \
    --cluster $ECS_CLUSTER_NAME \
    --service $ECS_SERVICE_NAME \
    --profile $AWS_PROFILE

echo "--- 6. Running Post-Deployment Verification ---"
# Navigate back to project root to run Makefile targets
cd ../..
./scripts/verify_fargate_deployment.sh
if [ $? -ne 0 ]; then
    echo "ERROR: Basic Fargate health check failed!"
    exit 1
fi

echo "--- 7. Running End-to-End Enrichment Test with google.com ---"
# Using the newly created Python script for robustness
python scripts/enrich_domain.py "google.com"
if [ $? -ne 0 ]; then
    echo "ERROR: End-to-end enrichment test with google.com failed!"
    exit 1
fi

echo "--- Deployment and Verification Complete! ---"