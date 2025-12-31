import os
import sys
from cocli.core.queue.factory import get_queue_manager

def test_queue_config():
    print("Checking Queue Manager configuration...")
    os.environ["COCLI_RUNNING_IN_FARGATE"] = "true"
    # Mocking environment variables that the factory expects if config file is missing
    os.environ["COCLI_ENRICHMENT_QUEUE_URL"] = "https://sqs.mock.url"
    
    try:
        mgr = get_queue_manager('test', use_cloud=True, queue_type='enrichment', campaign_name='turboship')
        profile = getattr(mgr, "aws_profile_name", None)
        print(f"Queue manager created with profile: {profile}")
        
        if profile is not None:
            print("FAILURE: Profile should be None in Fargate mode!")
            sys.exit(1)
        else:
            print("SUCCESS: Profile suppressed correctly for Fargate.")
            
    except Exception as e:
        print(f"Error during check: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_queue_config()
