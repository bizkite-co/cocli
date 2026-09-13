from __future__ import annotations
import sys
from typing import Optional
from cocli.application.services import ServiceContainer
from cocli.core.reporting import get_boto3_session

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/create_cognito_user.py <campaign_name>")
        sys.exit(1)
        
    campaign_name = sys.argv[1]
    services = ServiceContainer(campaign_name=campaign_name)
    config = services.campaign_service.get_config()
    
    aws_config = config.get("aws", {})
    user_pool_id: Optional[str] = aws_config.get("cocli_user_pool_id") or aws_config.get("user_pool_id")
    profile: Optional[str] = aws_config.get("aws_profile") or aws_config.get("profile")
    region: str = aws_config.get("region", "us-east-1")
    
    user_uri: Optional[str] = aws_config.get("cocli_op_test_username")
    pass_uri: Optional[str] = aws_config.get("cocli_op_test_password")
    
    if not user_pool_id:
        print(f"Error: user_pool_id not found in config for campaign {campaign_name}")
        sys.exit(1)
        
    if not user_uri or not pass_uri:
        print(f"Error: cocli_op_test_username and cocli_op_test_password must be defined in the [aws] section of {campaign_name} config.toml")
        sys.exit(1)
        
    print(f"Resolving credentials for {campaign_name} in {region}...")
    username = services.secret_service.get_secret(user_uri)
    password = services.secret_service.get_secret(pass_uri)
    
    if not username or not password:
        print("Error: Could not resolve one or more credentials from 1Password.")
        sys.exit(1)
    
    # get_boto3_session (not boto3.Session directly) resolves 1Password-backed
    # profiles through cocli's op_utils path instead of boto3's native (and
    # more fragile) credential_process handling. Region now comes from the
    # AWS profile's own config rather than campaign config.toml - every
    # profile and campaign in this repo agrees on us-east-1 today.
    session = get_boto3_session({}, profile_name=profile)
    client = session.client("cognito-idp")
    
    print(f"Provisioning user {username} in pool {user_pool_id}...")
    
    try:
        client.admin_create_user(
            UserPoolId=user_pool_id,
            Username=username,
            UserAttributes=[
                {"Name": "email", "Value": username},
                {"Name": "email_verified", "Value": "true"}
            ],
            MessageAction="SUPPRESS"
        )
    except client.exceptions.UsernameExistsException:
        print(f"User {username} already exists, updating password.")
        
    client.admin_set_user_password(
        UserPoolId=user_pool_id,
        Username=username,
        Password=password,
        Permanent=True
    )
    print("Success: Test user is ready for login.")

if __name__ == "__main__":
    main()
