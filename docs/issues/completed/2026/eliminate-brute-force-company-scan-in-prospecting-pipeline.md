# Eliminate brute-force Company scan in prospecting pipeline

The  /  command currently calls  at the start to build a deduplication map. This performs a brute-force scan of 12,000+ files, violating the 'Index-First' mandate. This should be refactored to use DuckDB or USV indices for presence checks.

---
**Completed in commit:** `2a1b302`
