#!/bin/bash
set -e

if [ -z "$LOCAL_DEV" ]; then
  # Only attempt 1Password retrieval if a valid token is provided and it's not the placeholder
  if [ -n "$OP_SESSION_TOKEN" ] && [ "$OP_SESSION_TOKEN" != "placeholder_for_now" ] || [ -n "$OP_SERVICE_ACCOUNT_TOKEN" ]; then
    # Retrieve the 1Password item using our unified helper
    OP_ITEM_ID="4lcddpkk5ytnvemniodqmfxq3i"
    ITEM_DETAILS=$(python3 -m cocli.utils.op_helper $OP_ITEM_ID)

    # Extract credentials from the 1Password item
    export ACCOUNT_ID=$(echo "$ITEM_DETAILS" | jq -r '.fields[] | select(.label == "account_id").value')
    export ACCESS_KEY_ID=$(echo "$ITEM_DETAILS" | jq -r '.fields[] | select(.label == "access_key_id").value')
    export SECRET_ACCESS_KEY=$(echo "$ITEM_DETAILS" | jq -r '.fields[] | select(.label == "secret_access_key").value')

    if [ -n "$ACCOUNT_ID" ] && [ -n "$ACCESS_KEY_ID" ] && [ -n "$SECRET_ACCESS_KEY" ]; then
        echo "Successfully retrieved credentials from 1Password."
        # Export standard AWS env vars if found
        export AWS_ACCESS_KEY_ID=$ACCESS_KEY_ID
        export AWS_SECRET_ACCESS_KEY=$SECRET_ACCESS_KEY
    else
        echo "Warning: Failed to retrieve all credentials from 1Password item $OP_ITEM_ID."
    fi
  else
    echo "Skipping 1Password retrieval (Using IAM Task Role or pre-configured environment)."
  fi
fi

# Execute the original command
# Start Uvicorn server in the background
# It should pick up environment variables from Fargate task definition
uvicorn cocli.services.enrichment_service.main:app --host 0.0.0.0 --port 8000 &

# Set required environment variables for the consumer
export COCLI_ENRICHMENT_QUEUE_URL="${COCLI_ENRICHMENT_QUEUE_URL}"
export COCLI_S3_BUCKET_NAME="${COCLI_S3_BUCKET_NAME}"
export COCLI_RUNNING_IN_FARGATE="true"

# Start the orchestrator in the foreground.
# It resolves worker definitions for this node (COCLI_HOSTNAME) from
# [prospecting.scaling] and launches them; 'worker supervisor' does NOT do
# this (heartbeat-only), so it must not be used here.
if [ -z "$CAMPAIGN_NAME" ]; then
    echo "Error: CAMPAIGN_NAME environment variable is not set."
    exit 1
fi


# Pull the campaign's config.toml from S3 before orchestrating. The Fargate
# image does not bundle data/, so load_campaign_config() would otherwise see
# an empty [prospecting.scaling] and orchestrate would silently fall back to
# its 1-worker gm-list default (this happened in production on 2026-07-02 -
# do not remove this step without replacing it).
echo "Pulling config.toml for $CAMPAIGN_NAME from S3..."
python3 -m cocli.worker_main campaign rollout pull-config --campaign "$CAMPAIGN_NAME"

echo "Starting cocli orchestrator for $CAMPAIGN_NAME..."

exec python3 -m cocli.worker_main worker orchestrate --campaign "$CAMPAIGN_NAME"
