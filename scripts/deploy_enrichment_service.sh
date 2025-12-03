#!/bin/bash
set -e

# Configuration
AWS_REGION="us-east-1"
AWS_PROFILE="turboship-support"
ECR_REPO_URI="193481341784.dkr.ecr.us-east-1.amazonaws.com/cocli-enrichment-service"
CLUSTER_NAME="default"
SERVICE_NAME="cocli-enrichment-task-service-biq83pqs"
TASK_FAMILY="cocli-enrichment-task"

echo "--- 1. Authenticating with ECR ---"
aws ecr get-login-password --region $AWS_REGION --profile $AWS_PROFILE | docker login --username AWS --password-stdin $ECR_REPO_URI

echo "--- 2. Tagging and Pushing Image to ECR ---"
# Assumes image 'enrichment-service:latest' was built by Makefile
docker tag enrichment-service:latest $ECR_REPO_URI:latest
# Also tag with specific version if possible, but for now latest is fine for the deploy script flow
docker push $ECR_REPO_URI:latest

echo "--- 3. Registering New Task Definition ---"
# This registers the local task-definition.json and captures the new revision number
NEW_TASK_DEF_ARN=$(aws ecs register-task-definition --cli-input-json file://task-definition.json --region $AWS_REGION --profile $AWS_PROFILE | jq -r '.taskDefinition.taskDefinitionArn')
echo "Registered new task definition: $NEW_TASK_DEF_ARN"

echo "--- 5. Updating ECS Service ---"
aws ecs update-service \
    --cluster $CLUSTER_NAME \
    --service $SERVICE_NAME \
    --task-definition $NEW_TASK_DEF_ARN \
    --force-new-deployment \
    --region $AWS_REGION \
    --profile $AWS_PROFILE

echo "--- Deployment Triggered Successfully! ---"
echo "Monitor status with: aws ecs describe-services --cluster $CLUSTER_NAME --services $SERVICE_NAME --region $AWS_REGION --profile $AWS_PROFILE"
