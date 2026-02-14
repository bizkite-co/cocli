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
    aws_cognito as cognito,
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

        # --- Conditional Fargate Infrastructure ---
        worker_count = campaign_config.get("worker_count", 0)
        vpc = None
        cluster = None

        if worker_count > 0:
            # VPC for Fargate - Set nat_gateways to 0 to save costs ($100/mo)
            # Fargate tasks will run in public subnets with public IPs assigned
            vpc = ec2.Vpc(self, "ScraperVpc", 
                max_azs=2,
                nat_gateways=0,
                subnet_configuration=[
                    ec2.SubnetConfiguration(
                        name="Public",
                        subnet_type=ec2.SubnetType.PUBLIC,
                        cidr_mask=24
                    )
                ]
            )

            # ECS Cluster
            cluster = ecs.Cluster(self, "ScraperCluster", vpc=vpc, cluster_name="ScraperCluster")

            # Enable Fargate Capacity Providers (including FARGATE_SPOT)
            cluster.enable_fargate_capacity_providers()

        # IAM Role for Fargate Task (Keep as it's free and used for permissions)
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
        
        # Campaign Updates Queue - Still used for remote commands via SQS
        campaign_updates_queue = sqs.Queue(self, "CampaignUpdatesQueue",
            visibility_timeout=Duration.minutes(1),
            retention_period=Duration.days(7),
        )
        campaign_updates_queue.grant_send_messages(task_role)
        campaign_updates_queue.grant_consume_messages(task_role)
        campaign_updates_queue.grant_send_messages(rpi_user)
        campaign_updates_queue.grant_consume_messages(rpi_user)

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
        CfnOutput(self, "CampaignUpdatesQueueUrl", value=campaign_updates_queue.queue_url)

        # Permissions for Fargate Task Role
        task_role.add_to_policy(iam.PolicyStatement(
            actions=["s3:*", "sqs:*"],
            resources=[
                f"arn:aws:s3:::{data_bucket.bucket_name}",
                f"arn:aws:s3:::{data_bucket.bucket_name}/*",
                "arn:aws:sqs:*:*:CdkScraperDeploymentStack-*"
            ]
        ))
        CfnOutput(self, "BucketName", value=data_bucket.bucket_name)
        CfnOutput(self, "WebBucketName", value=web_bucket.bucket_name)
        CfnOutput(self, "WebDomainName", value=subdomain)

        if cluster:
            # Application Load Balanced Fargate Service
            fargate_service = ecs_patterns.ApplicationLoadBalancedFargateService(self, "ScraperService",
                cluster=cluster,
                service_name="EnrichmentService", # Explicitly name the service
                cpu=1024,  # 1 vCPU
                memory_limit_mib=3072, # 3GB RAM
                desired_count=worker_count,
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
                        "COCLI_COMMAND_QUEUE_URL": campaign_updates_queue.queue_url,
                        "COCLI_S3_BUCKET_NAME": data_bucket.bucket_name,
                        "CAMPAIGN_NAME": campaign_config["name"],
                        "COCLI_DATA_HOME": "/app/data",
                        "COCLI_HOSTNAME": "fargate",
                        "DEPLOY_TIMESTAMP": self.node.try_get_context("deploy_timestamp") or "initial"
                    },
                    task_role=task_role
                ),
                public_load_balancer=True,
                assign_public_ip=True,
                task_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
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

        # --- IoT Core Credential Provider (The Gold Standard) ---
        
        # 1. IAM Role for PIs to assume
        iot_role = iam.Role(self, "CocliIoTScraperRole",
            assumed_by=iam.ServicePrincipal("credentials.iot.amazonaws.com"),
            description=f"Role assumed by Raspberry Pi workers for campaign {campaign_config['name']}"
        )

        # Create the Gold Standard Worker Policy
        worker_policy = iam.ManagedPolicy(self, "CocliIoTScraperWorkerPolicy",
            managed_policy_name=f"CocliIoTScraperWorkerPolicy-{campaign_config['name']}",
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "s3:PutObject",
                        "s3:GetObject",
                        "s3:ListBucket",
                        "s3:DeleteObject",
                        "s3:GetBucketLocation"
                    ],
                    resources=[
                        f"arn:aws:s3:::{data_bucket_name}",
                        f"arn:aws:s3:::{data_bucket_name}/*"
                    ]
                ),
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "sqs:SendMessage",
                        "sqs:ReceiveMessage",
                        "sqs:DeleteMessage",
                        "sqs:GetQueueAttributes",
                        "sqs:ChangeMessageVisibility"
                    ],
                    resources=[
                        f"arn:aws:sqs:{self.region}:{self.account}:CdkScraperDeploymentStack-*"
                    ]
                )
            ]
        )
        iot_role.add_managed_policy(worker_policy)

        # Add explicit self-discovery and logging permissions
        iot_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "iot:DescribeEndpoint",
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents",
                "logs:DescribeLogStreams"
            ],
            resources=["*"]
        ))
        
        data_bucket.grant_read_write(iot_role)
        web_bucket.grant_read_write(iot_role)
        campaign_updates_queue.grant_send_messages(iot_role)
        campaign_updates_queue.grant_consume_messages(iot_role)

        # 2. IoT Role Alias
        from aws_cdk import aws_iot as iot
        role_alias = iot.CfnRoleAlias(self, "CocliScraperRoleAlias",
            role_arn=iot_role.role_arn,
            role_alias=f"CocliScraperAlias-{campaign_config['name']}",
            credential_duration_seconds=3600
        )

        # 3. IoT Policy to allow AssumeRoleWithCertificate
        iot_policy = iot.CfnPolicy(self, "CocliIoTAssumeRolePolicy",
            policy_name=f"CocliIoTAssumeRolePolicy-{campaign_config['name']}",
            policy_document={
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": "iot:AssumeRoleWithCertificate",
                        "Resource": role_alias.attr_role_alias_arn
                    }
                ]
            }
        )

        # 4. IAM User for local development / Gemini Agent
        # This user will be used to generate the credentials for the roadmap-iot profile
        agent_user = iam.User(self, "CocliAgentUser",
            user_name=f"cocli-agent-{campaign_config['name']}"
        )
        # Grant the agent user permission to use the IoT Role Alias via a certificate if needed,
        # or just give it direct AssumeRole if we want a shortcut, but let's stick to the IoT path.
        agent_user.add_to_policy(iam.PolicyStatement(
            actions=["iot:AssumeRoleWithCertificate"],
            resources=[role_alias.attr_role_alias_arn]
        ))

        CfnOutput(self, "IoTRoleAlias", value=role_alias.role_alias)
        CfnOutput(self, "IoTPolicyName", value=iot_policy.policy_name)
        CfnOutput(self, "IoTRoleArn", value=iot_role.role_arn)
        CfnOutput(self, "AgentUserName", value=agent_user.user_name)

        # --- Cognito User Pool and Client ---
        user_pool_id = campaign_config.get("user_pool_id")
        client_id = campaign_config.get("user_pool_client_id")
        user_pool_domain_prefix = campaign_config.get("user_pool_domain")

        if not user_pool_id:
            user_pool = cognito.UserPool(self, "CocliUserPool",
                user_pool_name=f"cocli-user-pool-{campaign_config['name']}",
                self_sign_up_enabled=False,
                sign_in_aliases=cognito.SignInAliases(email=True),
                auto_verify=cognito.AutoVerifiedAttrs(email=True),
                removal_policy=RemovalPolicy.RETAIN,
                password_policy=cognito.PasswordPolicy(
                    min_length=8,
                    require_lowercase=True,
                    require_uppercase=True,
                    require_digits=True,
                    require_symbols=True
                )
            )
            user_pool_id = user_pool.user_pool_id
            
            # Create a Domain for Hosted UI
            domain_prefix = user_pool_domain_prefix or f"cocli-auth-{campaign_config['name']}"
            user_pool.add_domain("UserPoolDomain",
                cognito_domain=cognito.CognitoDomainOptions(
                    domain_prefix=domain_prefix
                )
            )
            user_pool_domain_url = f"https://{domain_prefix}.auth.{self.region}.amazoncognito.com"

            # Create a Client
            redirect_uris = [
                f"https://{subdomain}/auth-callback/index.html",
                "http://localhost:8080/auth-callback/index.html"
            ]
            logout_uris = [
                f"https://{subdomain}/signout",
                "http://localhost:8080/signout"
            ]
            
            client = user_pool.add_client("CocliDashboardClient",
                user_pool_client_name=f"cocli-dashboard-{campaign_config['name']}",
                generate_secret=False,
                o_auth=cognito.OAuthSettings(
                    flows=cognito.OAuthFlows(
                        authorization_code_grant=True,
                        implicit_code_grant=True
                    ),
                    scopes=[cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL, cognito.OAuthScope.PROFILE],
                    callback_urls=redirect_uris,
                    logout_urls=logout_uris
                )
            )
            client_id = client.user_pool_client_id
        else:
            # If provided, we assume the domain is either provided or follows the standard
            user_pool_domain_url = f"https://{user_pool_domain_prefix}.auth.{self.region}.amazoncognito.com" if user_pool_domain_prefix else ""

        # --- Cognito Identity Pool for Web-to-SQS Command Bridge ---
        provider_name = f"cognito-idp.{self.region}.amazonaws.com/{user_pool_id}"

        identity_pool = cognito.CfnIdentityPool(self, "CocliDashboardIdentityPool",
            allow_unauthenticated_identities=False,
            cognito_identity_providers=[
                cognito.CfnIdentityPool.CognitoIdentityProviderProperty(
                    client_id=client_id,
                    provider_name=provider_name
                )
            ]
        )

        # IAM Role for Authenticated Users
        authenticated_role = iam.Role(self, "CocliDashboardAuthRole",
            assumed_by=iam.FederatedPrincipal(
                "cognito-identity.amazonaws.com",
                {
                    "StringEquals": { "cognito-identity.amazonaws.com:aud": identity_pool.ref },
                    "ForAnyValue:StringLike": { "cognito-identity.amazonaws.com:amr": "authenticated" }
                },
                "sts:AssumeRoleWithWebIdentity"
            )
        )

        # Grant SendMessage to the specific CampaignUpdatesQueue
        campaign_updates_queue.grant_send_messages(authenticated_role)

        # Grant Read Access to Data and Web Buckets for the Dashboard
        data_bucket.grant_read(authenticated_role)
        web_bucket.grant_read(authenticated_role)

        # Attach roles to Identity Pool
        cognito.CfnIdentityPoolRoleAttachment(self, "CocliDashboardIdentityPoolRoles",
            identity_pool_id=identity_pool.ref,
            roles={
                "authenticated": authenticated_role.role_arn
            }
        )

        CfnOutput(self, "IdentityPoolId", value=identity_pool.ref)
        CfnOutput(self, "UserPoolId", value=user_pool_id)
        CfnOutput(self, "UserPoolClientId", value=client_id)
        if user_pool_domain_url:
            CfnOutput(self, "UserPoolDomain", value=user_pool_domain_url)
