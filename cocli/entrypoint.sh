#!/bin/bash
set -e

if [ -z "$LOCAL_DEV" ]; then
  # Check if OP_SESSION_TOKEN is set
  if [ -z "$OP_SESSION_TOKEN" ]; then
    echo "Error: OP_SESSION_TOKEN environment variable is not set."
    exit 1
  fi

  # Retrieve the 1Password item
  OP_ITEM_ID="4lcddpkk5ytnvemniodqmfxq3i"
  ITEM_DETAILS=$(op get item $OP_ITEM_ID --format json)

  # Extract credentials from the 1Password item
  # Assuming the fields are named 'account_id', 'access_key_id', 'secret_access_key'
  export ACCOUNT_ID=$(echo "$ITEM_DETAILS" | jq -r '.fields[] | select(.label == "account_id").value')
  export ACCESS_KEY_ID=$(echo "$ITEM_DETAILS" | jq -r '.fields[] | select(.label == "access_key_id").value')
  export SECRET_ACCESS_KEY=$(echo "$ITEM_DETAILS" | jq -r '.fields[] | select(.label == "secret_access_key").value')

  # Check if credentials were successfully retrieved
  if [ -z "$ACCOUNT_ID" ] || [ -z "$ACCESS_KEY_ID" ] || [ -z "$SECRET_ACCESS_KEY" ]; then
    echo "Error: Failed to retrieve all credentials from 1Password item $OP_ITEM_ID."
    exit 1
  fi

  echo "Successfully retrieved credentials from 1Password."
fi

# Execute the original command
exec uvicorn cocli.services.enrichment_service.main:app --host 0.0.0.0 --port 8000
