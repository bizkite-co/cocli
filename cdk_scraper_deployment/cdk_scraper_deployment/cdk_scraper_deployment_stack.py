from aws_cdk import (
    Stack,
    aws_ecr as ecr,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_s3 as s3,
    aws_sqs as sqs,
    aws_route53 as route53,
    aws_elasticloadbalancingv2 as elbv2,
    Duration,
    CfnOutput,
)
from constructs import Construct

class CdkScraperDeploymentStack(Stack):  # type: ignore[misc]

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(scope, construct_id, **kwargs)

        # Define the path to the Dockerfile (no longer needed, using pre-built image)
        # dockerfile_path = os.path.join(os.path.dirname(__file__), "..", "..")

        # ECR Repository (Import existing to grant permissions)
        repository = ecr.Repository.from_repository_name(self, "ImportedRepo", "cocli-enrichment-service")

        # VPC for Fargate
        vpc = ec2.Vpc(self, "ScraperVpc", max_azs=2)

        # ECS Cluster
        cluster = ecs.Cluster(self, "ScraperCluster", vpc=vpc, cluster_name="ScraperCluster")

        # Enable Fargate Capacity Providers (including FARGATE_SPOT)
        cluster.enable_fargate_capacity_providers()

        # IAM Role for Fargate Task
        task_role = iam.Role(self, "ScraperTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com")
        )

        # --- S3 Bucket for Data (Import existing) ---
        data_bucket = s3.Bucket.from_bucket_name(self, "CocliDataBucket", "cocli-data-turboship")
        data_bucket.grant_read_write(task_role)

        # --- SQS Queues ---
        
        # 1. Enrichment Queue (Existing) - For website enrichment tasks
        enrichment_queue = sqs.Queue(self, "EnrichmentQueue",
            visibility_timeout=Duration.minutes(5), # 5 mins for enrichment task
            retention_period=Duration.days(4)
        )
        enrichment_queue.grant_send_messages(task_role)
        enrichment_queue.grant_consume_messages(task_role)
        
        # 2. Scrape Tasks Queue (New) - For Google Maps scraping tasks (lat/lon/query)
        scrape_tasks_queue = sqs.Queue(self, "ScrapeTasksQueue",
            visibility_timeout=Duration.minutes(15), # 15 mins (scraping a grid cell takes time)
            retention_period=Duration.days(4)
        )
        scrape_tasks_queue.grant_send_messages(task_role)
        scrape_tasks_queue.grant_consume_messages(task_role)

        # 3. Google Maps List Item Queue (New) - For scraping details of found list items
        gm_list_item_queue = sqs.Queue(self, "GmListItemQueue",
            visibility_timeout=Duration.minutes(5), # 5 mins should be plenty for one detail scrape
            retention_period=Duration.days(4)
        )
        gm_list_item_queue.grant_send_messages(task_role)
        gm_list_item_queue.grant_consume_messages(task_role)

        # --- Grant Permissions to RPi User (mark) ---
        rpi_user = iam.User.from_user_name(self, "RpiUser", "mark")
        
        enrichment_queue.grant_send_messages(rpi_user)
        enrichment_queue.grant_consume_messages(rpi_user)
        
        scrape_tasks_queue.grant_send_messages(rpi_user)
        scrape_tasks_queue.grant_consume_messages(rpi_user)
        
        gm_list_item_queue.grant_send_messages(rpi_user)
        gm_list_item_queue.grant_consume_messages(rpi_user)

        # --- DNS / HTTPS ---
        zone = route53.HostedZone.from_hosted_zone_attributes(self, "HostedZone",
            hosted_zone_id="Z0754885WA4ZOH1QH7PJ",
            zone_name="turboheat.net"
        )
        
        # Outputs
        CfnOutput(self, "EnrichmentQueueUrl", value=enrichment_queue.queue_url)
        CfnOutput(self, "ScrapeTasksQueueUrl", value=scrape_tasks_queue.queue_url)
        CfnOutput(self, "GmListItemQueueUrl", value=gm_list_item_queue.queue_url)
        CfnOutput(self, "BucketName", value=data_bucket.bucket_name)

        # Application Load Balanced Fargate Service
        fargate_service = ecs_patterns.ApplicationLoadBalancedFargateService(self, "ScraperService",
            cluster=cluster,
            service_name="EnrichmentService", # Explicitly name the service
            cpu=1024,  # 1 vCPU (Playwright needs this)
            memory_limit_mib=3072, # 3GB RAM (Playwright needs this)
            desired_count=1,
            domain_name="enrich.turboheat.net",
            domain_zone=zone,
            protocol=elbv2.ApplicationProtocol.HTTPS, # Explicitly set HTTPS protocol
            redirect_http=True, # Redirect HTTP to HTTPS
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_registry(repository.repository_uri + ":latest"),
                container_port=8000,
                environment={
                    "COCLI_ENRICHMENT_QUEUE_URL": enrichment_queue.queue_url,
                    "COCLI_SCRAPE_TASKS_QUEUE_URL": scrape_tasks_queue.queue_url,
                    "COCLI_GM_LIST_ITEM_QUEUE_URL": gm_list_item_queue.queue_url,
                    "COCLI_S3_BUCKET_NAME": data_bucket.bucket_name
                },
                task_role=task_role
            ),
            public_load_balancer=True,
            assign_public_ip=True,
            capacity_provider_strategies=[
                ecs.CapacityProviderStrategy(
                    capacity_provider="FARGATE_SPOT",
                    weight=1
                )
            ]
        )
        
        # Grant permissions to pull image from ECR
        repository.grant_pull(fargate_service.task_definition.obtain_execution_role())

        # Configure Health Check
        fargate_service.target_group.configure_health_check(
            path="/health",
            healthy_http_codes="200"
        )