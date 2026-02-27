#!/bin/bash
# Recovery Monitor: Sync -> Process -> Compact Loop

CAMPAIGN=${1:-roadmap}
SLEEP_TIME=3600 # 1 hour

echo "--- Starting Recovery Monitor for $CAMPAIGN ---"

while true; do
    echo "[$(date +%T)] Syncing latest data..."
    
    # 1. Sync Raw Witnesses (Down)
    cocli smart-sync raw --campaign $CAMPAIGN
    
    # 2. Sync Pending Tasks (Down)
    cocli smart-sync queues --campaign $CAMPAIGN
    
    # Calculate pending count
    pending_left=$(find data/campaigns/$CAMPAIGN/queues/gm-details/pending/ -name "task.json" | wc -l)
    
    # 3. Process Witnesses locally (Scraper-free transformation)
    # We check the raw directory for any .json files that don't have a corresponding WAL record
    # For now, we'll run the processor role once.
    echo "  [PROCESS] Transforming new witnesses..."
    python3 scripts/test_processor_role.py
    
    echo "  [COMPACT] Updating Gold index..."
    python3 scripts/compact_shards.py $CAMPAIGN
    
    # 4. Status Report
    current_total=$(wc -l < data/campaigns/$CAMPAIGN/indexes/google_maps_prospects/prospects.checkpoint.usv)
    echo "  [STATUS] Total Index: $current_total | Pending Tasks: $pending_left"
    
    echo "Sleeping for $SLEEP_TIME seconds..."
    sleep $SLEEP_TIME
done
