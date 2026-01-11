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
    aws_route53_targets as targets,
    aws_elasticloadbalancingv2 as elbv2,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_certificatemanager as acm,
    aws_logs as logs,
    Duration,
    CfnOutput,
    RemovalPolicy,
    Tags,
)
from constructs import Construct

class CdkScraperDeploymentStack(Stack):  # type: ignore[misc]

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:  # type: ignore[no-untyped-def]
        campaign_config = kwargs.pop("campaign_config")
        super().__init__(scope, construct_id, **kwargs)

        domain = campaign_config["domain"]
        zone_id = campaign_config["zone_id"]
        bucket_name = f"cocli-web-assets-{domain.replace('.', '-')}"
        subdomain = f"cocli.{domain}"
        data_bucket_name = campaign_config["data_bucket_name"]
        rpi_user_name = campaign_config["rpi_user_name"]
        ou_arn = campaign_config.get("ou_arn")

        # Global Tagging for Isolation and Billing
        Tags.of(self).add("Campaign", campaign_config["name"])

        if ou_arn:
            Tags.of(self).add("OrganizationalUnit", ou_arn)

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

        # --- Grant Permissions to RPi User ---
        rpi_user = iam.User.from_user_name(self, "RpiUser", rpi_user_name)

        # --- S3 Bucket for Data ---
        # Import existing bucket instead of creating a new one to avoid conflicts
        data_bucket = s3.Bucket.from_bucket_name(self, "CocliDataBucket", data_bucket_name)
        data_bucket.grant_read_write(task_role)
        data_bucket.grant_read_write(rpi_user)

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

        # Strict Isolation: Deny access to other campaign resources
        # This ensures that even if the user has broad permissions, they are restricted
        # to ONLY the resources tagged with this specific campaign name.
        rpi_user.add_to_principal_policy(iam.PolicyStatement(
            effect=iam.Effect.DENY,
            actions=["s3:*", "sqs:*"],
            resources=[
                "arn:aws:s3:::cocli-data-*",
                "arn:aws:s3:::roadmap-cocli-data-*",
                "arn:aws:sqs:*:*:CdkScraperDeploymentStack-*"
            ],
            conditions={
                "StringNotEquals": {
                    "aws:ResourceTag/Campaign": campaign_config["name"]
                },
                "Null": {
                    "aws:ResourceTag/Campaign": "false" # Only trigger deny if the tag exists and is wrong
                }
            }
        ))

        # --- Grant Permissions to RPi User ---
        enrichment_queue.grant_send_messages(rpi_user)
        enrichment_queue.grant_consume_messages(rpi_user)
        
        scrape_tasks_queue.grant_send_messages(rpi_user)
        scrape_tasks_queue.grant_consume_messages(rpi_user)
        
        gm_list_item_queue.grant_send_messages(rpi_user)
        gm_list_item_queue.grant_consume_messages(rpi_user)

        # --- Single-Site Website Infrastructure ---
        zone = route53.HostedZone.from_hosted_zone_attributes(self, "HostedZone",
            hosted_zone_id=zone_id,
            zone_name=domain
        )
        
        # 1. Bucket for Web Assets
        web_bucket = s3.Bucket(self, "CocliWebAssets",
            bucket_name=bucket_name,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True
        )
        
        # 2. Certificate for CloudFront
        web_cert = acm.Certificate(self, "CocliWebCert",
            domain_name=subdomain,
            validation=acm.CertificateValidation.from_dns(zone)
        )
        
        # 3. CloudFront Distribution
        web_distro = cloudfront.Distribution(self, "CocliWebDistro",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(web_bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_DISABLED
            ),
            domain_names=[subdomain],
            certificate=web_cert,
            default_root_object="index.html",
            error_responses=[
                cloudfront.ErrorResponse(http_status=403, response_http_status=200, response_page_path="/index.html", ttl=Duration.minutes(0)),
                cloudfront.ErrorResponse(http_status=404, response_http_status=200, response_page_path="/index.html", ttl=Duration.minutes(0))
            ]
        )
        
        # 4. Route53 Record
        route53.ARecord(self, "CocliWebAlias",
            zone=zone,
            record_name="cocli",
            target=route53.RecordTarget.from_alias(targets.CloudFrontTarget(web_distro))
        )

        # Outputs
        CfnOutput(self, "EnrichmentQueueUrl", value=enrichment_queue.queue_url)
        CfnOutput(self, "ScrapeTasksQueueUrl", value=scrape_tasks_queue.queue_url)
        CfnOutput(self, "GmListItemQueueUrl", value=gm_list_item_queue.queue_url)
        CfnOutput(self, "BucketName", value=data_bucket.bucket_name)
        CfnOutput(self, "WebBucketName", value=web_bucket.bucket_name)
        CfnOutput(self, "WebDomainName", value=subdomain)

        # Application Load Balanced Fargate Service
        fargate_service = ecs_patterns.ApplicationLoadBalancedFargateService(self, "ScraperService",
            cluster=cluster,
            service_name="EnrichmentService", # Explicitly name the service
            cpu=1024,  # 1 vCPU
            memory_limit_mib=3072, # 3GB RAM
            desired_count=campaign_config.get("worker_count", 1),
            domain_name=f"enrich.{domain}",
            domain_zone=zone,
            protocol=elbv2.ApplicationProtocol.HTTPS, # Explicitly set HTTPS protocol
            redirect_http=True, # Redirect HTTP to HTTPS
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_registry(repository.repository_uri + ":latest"),
                container_port=8000,
                log_driver=ecs.LogDrivers.aws_logs(
                    stream_prefix="web",
                    log_retention=logs.RetentionDays.THREE_DAYS
                ),
                environment={
                    "COCLI_ENRICHMENT_QUEUE_URL": enrichment_queue.queue_url,
                    "COCLI_SCRAPE_TASKS_QUEUE_URL": scrape_tasks_queue.queue_url,
                    "COCLI_GM_LIST_ITEM_QUEUE_URL": gm_list_item_queue.queue_url,
                    "COCLI_S3_BUCKET_NAME": data_bucket.bucket_name,
                    "CAMPAIGN_NAME": campaign_config["name"],
                    "COCLI_DATA_HOME": "/app/cocli_data",
                    "COCLI_HOSTNAME": "fargate",
                    "DEPLOY_TIMESTAMP": self.node.try_get_context("deploy_timestamp") or "initial"
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

        CfnOutput(self, "EnrichmentServiceURL",
            value=f"https://enrich.{domain}",
            description="URL of the enrichment service"
        )                                       
