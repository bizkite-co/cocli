# Bucket Schema

The campaign-specific buckets in S3 must be at `s3://{campaign-bucket}/campaigns/{campaign}/` because a client might have more than one campaign from more than one company, and they might push that to their own S3 bucket.

