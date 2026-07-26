
 Here is the exact discovery workflow for roadmap (or any campaign):

  ### 1. The Standard Discovery Workflow Steps

  1. Generate Grid (Create 0.1-degree tile definitions for target locations):
    cocli campaign generate-grid --campaign roadmap

  2. Prepare Mission (Generate master mission.usv & calculate unscraped frontier):
    cocli campaign prepare-mission --campaign roadmap

  3. Build Mission Index & Queue Scrapes (Explode mission list into gm-list pending queue):
    cocli campaign build-mission-index --campaign roadmap
    cocli campaign queue-scrapes --campaign roadmap

  4. Push Campaign & Config to Cluster (S3):
    cocli campaign rollout push-config --campaign roadmap
    cocli campaign rollout push --campaign roadmap

  ──────
  ### 2. Pi Cluster Assignment

  To assign both Raspberry Pi nodes (cocli5x0.pi and cocli5x1.pi) to run workers on the roadmap campaign,
  update/broadcast the scaling configuration or deploy via rollout:

    cocli campaign rollout broadcast-config --campaign roadmap
    ──────
  ### 3. Monitoring Pi Workers

  Monitor real-time worker logs and gossip status:

  • Live Cluster Audit:
    cocli audit cluster --live

  • Pi Worker Logs:
    cocli cluster logs --host cocli5x0.pi --follow
    cocli cluster logs --host cocli5x1.pi --follow
