# Task: Implement Identity Enums for Core Stores

## Objective
Replace "magic strings" like `"gm-list"` or `"scraped-tiles"` with strongly typed Enums.

## Background
We have several places in the code where strings are hardcoded to refer to indexes or queues. This is brittle and hard to refactor.

## Requirements
- Define `StoreIdentity` enum.
- Define `QueueIdentity` enum.
- Update `paths.py` to accept these enums instead of raw strings where possible.
- Update `cocli audit` commands to use these identities for registry lookups.
