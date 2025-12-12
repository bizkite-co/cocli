# Current Task: Remote Scraping Infrastructure (Proxy Tunneling)

## Objective
Migrate the Google Maps scraping workload to AWS Fargate while routing browser traffic through a local residential IP to avoid data center blocks.

## Context
*   **Problem:** Google Maps blocks AWS/Data Center IPs.
*   **Solution:** Hybrid Architecture.
    *   **Compute (AWS Fargate):** Runs `cocli` logic, manages queues/state.
    *   **Network (Local Machine):** Acts as a "dumb" proxy node.
    *   **Connection:** Secure tunnel (e.g., SSH Reverse Tunnel, Ngrok, or VPN) bridging AWS to Local.
*   **Parallelism (Future):** The architecture should support multiple proxy nodes (e.g., Raspberry Pis) consuming from a shared scrape-area queue.

## Plan

### Phase 1: Application Support
1.  **Config:** Add `proxy_url` support to `cocli` configuration (TOML/Env).
2.  **Playwright:** Update `cocli/commands/campaign.py` to inject proxy settings into `browser.launch()` if configured.
3.  **HTTPX:** Update enrichment clients to respect proxy settings (optional for now, focus on Maps).

### Phase 2: Tunnel & Deploy
1.  **Tunnel POC:** Use a simple tunnel (e.g., Ngrok or SSH Reverse Forwarding to a bastion) to expose the local proxy port to the AWS VPC.
2.  **Deploy:** Push the updated `cocli` image to ECR.
3.  **Verify:** Run a remote scrape job that connects back through the tunnel and succeeds.

## Todo
- [ ] **Code:** Add `proxy_url` to `cocli` config/args.
- [ ] **Code:** Update `pipeline` in `campaign.py` to use `proxy_url` in `chromium.launch()`.
- [ ] **Test:** Verify local proxy usage (e.g., run local `cocli` pointing to a local proxy to confirm traffic flow).
- [ ] **Infra:** Set up the tunnel method.
- [ ] **Deploy:** Update AWS task definition/image.
