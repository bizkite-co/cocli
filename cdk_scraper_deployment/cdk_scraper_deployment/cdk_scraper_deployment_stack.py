from aws_cdk import (
    Stack,
    aws_ecr as ecr,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_ec2 as ec2,
    aws_secretsmanager as secretsmanager,
    aws_iam as iam,
)
from constructs import Construct
import os

class CdkScraperDeploymentStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Define the path to the Dockerfile
        dockerfile_path = os.path.join(os.path.dirname(__file__), "..", "..", "cocli")

        # ECR Repository
        ecr_repository = ecr.Repository(self, "ScraperRepository")

        # Build and push Docker image to ECR
        # The image will be built from the Dockerfile in the cocli directory
        # and pushed to the ECR repository.
        # The 'image' property of the FargateService will handle the Docker build and push.

        # VPC for Fargate
        vpc = ec2.Vpc(self, "ScraperVpc", max_azs=2)

        # ECS Cluster
        cluster = ecs.Cluster(self, "ScraperCluster", vpc=vpc)

        # Add Fargate Spot capacity provider
        cluster.add_capacity_provider(ecs.FargateCapacityProvider(self, "FargateSpotCapacityProvider",
            capacity_provider_name="FARGATE_SPOT"
        ))

        # Secrets Manager Secret for 1Password Session Token
        # The user needs to create this secret manually in AWS Secrets Manager
        # and provide its name here. The value of the secret should be the 1Password session token.
        op_session_token_secret_name = "1PasswordSessionToken"
        op_session_token_secret = secretsmanager.Secret.from_secret_name_v2(
            self, "OPSessionTokenSecret", op_session_token_secret_name
        )

        # IAM Role for Fargate Task to access Secrets Manager
        task_role = iam.Role(self, "ScraperTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com")
        )
        op_session_token_secret.grant_read(task_role)

        # Application Load Balanced Fargate Service
        ecs_patterns.ApplicationLoadBalancedFargateService(self, "ScraperService",
            cluster=cluster,
            cpu=256,  # Smallest CPU unit
            memory_limit_mib=512, # Smallest memory unit
            desired_count=1,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_asset(dockerfile_path),
                container_port=8000, # Port that uvicorn listens on
                environment={
                    # Pass the 1Password item ID as an environment variable
                    "OP_ITEM_ID": "4lcddpkk5ytnvemniodqmfxq3i"
                },
                secrets={
                    "OP_SESSION_TOKEN": ecs.Secret.from_secrets_manager(op_session_token_secret)
                },
                task_role=task_role
            ),
            public_load_balancer=True, # Make the ALB public
            assign_public_ip=True, # Assign public IP to tasks
            capacity_provider_strategies=[
                ecs.CapacityProviderStrategy(
                    capacity_provider="FARGATE_SPOT",
                    weight=1
                )
            ]
        )