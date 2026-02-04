import boto3

try:
    session = boto3.Session(profile_name='roadmap')
except Exception:
    session = boto3.Session()

# Force us-east-1 explicitly in the client
s3 = session.client('s3', region_name='us-east-1')
bucket = 'roadmap-cocli-data-use1'
prefix = 'campaigns/roadmap/queues/gm-details/pending/'

print(f"Testing list_objects_v2 on {bucket} with prefix {prefix} (REGION=us-east-1)")
try:
    response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, Delimiter='/')
    print(f"CommonPrefixes: {response.get('CommonPrefixes', [])}")
    print(f"Contents count: {len(response.get('Contents', []))}")
except Exception as e:
    print(f"Error: {e}")
