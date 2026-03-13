# Gossip bridge respects current campaign too much

The gossip bridge redirects gossip into the current campaign's queues, instead of the campaign that created it.

We need to add a campaign name to every gossip item datagram so it will be routed to the right directory.

---
**Completed in commit:** `<pending-commit-id>`
