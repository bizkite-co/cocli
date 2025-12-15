#!/bin/bash
set -e

if [ -z "$LOCAL_DEV" ]; then
  # Only attempt 1Password retrieval if a valid token is provided and it's not the placeholder
  if [ -n "$OP_SESSION_TOKEN" ] && [ "$OP_SESSION_TOKEN" != "placeholder_for_now" ]; then
    # Retrieve the 1Password item
    OP_ITEM_ID="4lcddpkk5ytnvemniodqmfxq3i"
    # Correct command syntax: op item get
    ITEM_DETAILS=$(op item get $OP_ITEM_ID --format json)

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

# Start the SQS consumer (enrich-from-queue in consumer mode) in the foreground
# It will use the COCLI_ENRICHMENT_QUEUE_URL and COCLI_S3_BUCKET_NAME env vars
# And it will call the locally running API (uvicorn) for enrichment logic
exec uv run cocli campaign prospects enrich-from-queue turboship --cloud-queue
