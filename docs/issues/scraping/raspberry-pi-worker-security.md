To address your question, using long-lived Admin-level keys on edge devices
  (Raspberry Pis) is a major security risk. AWS provides several better patterns
  for this:

  1. AWS IoT Core "Credential Provider" (The Recommended Way)
  This is the gold standard for Raspberry Pis.
   * How it works: You install a unique X.509 certificate on each Pi. The Pi uses
     this cert to talk to an AWS IoT endpoint, which then returns temporary,
     short-lived IAM credentials (STS tokens).
   * Benefit: No secret keys are stored on the disk. If a Pi is stolen, you just
     revoke its certificate in the AWS Console.
   * Integration: You would point boto3 to use the IoT Credential Provider instead
     of a static profile.

  2. IAM Roles Anywhere
  This is a newer, similar service for "non-AWS" workloads (on-prem servers, RPs).
   * How it works: You use your own Certificate Authority (CA) to issue
     certificates to your devices. They use these certs to "assume" an IAM role
     directly.
   * Benefit: Extremely secure and follows the same "Role" pattern used inside AWS.

  3. AWS SSO (IAM Identity Center) + aws configure sso
  If these are devices you physically manage and can log into occasionally:
   * How it works: You run aws sso login. It opens a browser (or provides a code),
     and you get short-lived tokens (8–12 hours).
   * Benefit: No permanent keys. But it requires manual re-authentication when
     tokens expire, which isn't ideal for a headless scraper.

  4. Limited IAM Policy (Immediate Mitigation)
  Even if you continue using static keys for now, they should never be Admin-level.
   * The Fix: Create a "Scraper" IAM user with a policy that ONLY has
     s3:ListBucket, s3:GetObject, and s3:PutObject restricted to the specific
     roadmap-cocli-data-use1 bucket.

