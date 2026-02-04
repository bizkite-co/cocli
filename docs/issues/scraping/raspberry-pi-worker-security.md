To address your question, using long-lived Admin-level keys on edge devices
  (Raspberry Pis) is a major security risk. AWS provides several better patterns
  for this:

  1. AWS IoT Core "Credential Provider" (IMPLEMENTED - Feb 4, 2026)
  This is the gold standard for Raspberry Pis.
   * How it works: Each Pi uses a unique X.509 certificate to exchange for temporary STS tokens via the IoT endpoint.
   * Implementation: See `cocli/core/reporting.py:get_boto3_session` and the RPi schema in `docs/.schema/rpi-worker/`.
   * Benefit: No long-lived secret keys on disk; granular revocation per device.

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

