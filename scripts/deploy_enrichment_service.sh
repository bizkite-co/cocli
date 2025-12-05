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

echo "--- Deployment Complete! ---"