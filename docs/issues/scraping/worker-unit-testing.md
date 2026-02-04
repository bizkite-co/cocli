## Achitecture Refactor

You've hit on the exact reason why we're struggling right now: the "Infrastructure" (Queue/Discovery) is tightly coupled with the "Application" (Worker/Scraper), and neither is adequately tested in a distributed context.

1. Why isn't this part of our tests?

Currently, our tests (in tests/ and features/) focus on high-level CRM functionality or local data transformation. 

The FilesystemQueue and its S3 Discovery logic are relatively new and inherently "cloud-native."

* Mocking Trap: We likely didn't write unit tests for the S3 discovery because mocking S3 list_objects_v2 with Delimiter and CommonPrefixes is complex. If you mock it slightly wrong, the test passes while the real code fails.
* Environment Gap: Our local tests run on your Linux machine with a local filesystem. They don't simulate the "Cold Start" discovery where a worker wakes up with an empty disk and must "hydrate" from S3.

2. Should we run a local Docker container?
Yes, but with one addition: LocalStack.

If we run a local Docker container and point it at a local S3 simulator (LocalStack), we could replicate this "Discovery" failure in seconds on your machine. 

This would be much faster than the 2-minute rsync -> docker cp ->
restart -> tail logs cycle we're doing now.

3. Refactoring into "Portable Components"

You are 100% correct. cocli is currently a monolith. The workers and the CRM application have different "concerns":

* CRM Application: Identity, Prospect Management, CLI UX.
* Scraping Infrastructure: Distributed Queues, Browser Management, Proxy/Anti-bot logic.

Proposed "Parceling" Strategy:

1. Isolate the Queue Manager: Move cocli/core/queue/ into a standalone, pure-logic component. It should be testable without a browser or a CRM campaign.
2. Decompose `worker.py`: That file is 1700+ lines. It should be split into:
   * Supervisor: Manages process life-cycles.
   * Orchestrator: Handles the polling/scaling logic.
   * Scrapers: Pure "Input -> HTML -> Pydantic Model" functions.
3. Shared "Core" Library: Create a cocli-common (or similar) that contains the data models (GoogleMapsProspect) and configuration loaders. This allows the workers to be lightweight and portable.

