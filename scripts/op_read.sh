#!/bin/bash
export OP_ACCOUNT=my.1password.com

OP_PATH="$1"
if [[ "$OP_PATH" == *"op://"* ]]; then
    VAULT_ITEM="${OP_PATH#op://}"
    
    slash_count=$(echo "$VAULT_ITEM" | tr -cd '/' | wc -c)
    part_count=$((slash_count + 1))
    
    if [[ "$part_count" -eq 2 ]]; then
        VAULT="${VAULT_ITEM%%/*}"
        ITEM="${VAULT_ITEM#*/}"
        "/mnt/c/Program Files/1Password CLI/op.exe" item get "$ITEM" --vault "$VAULT" --format json
    elif [[ "$part_count" -eq 3 ]]; then
        VAULT="${VAULT_ITEM%%/*}"
        ITEM_REM="${VAULT_ITEM#*/}"
        ITEM="${ITEM_REM%%/*}"
        FIELD="${ITEM_REM#*/}"
        "/mnt/c/Program Files/1Password CLI/op.exe" read "op://${VAULT}/${ITEM}/${FIELD}" --account "my.1password.com"
    elif [[ "$part_count" -ge 4 ]]; then
        VAULT="${VAULT_ITEM%%/*}"
        REMAIN="${VAULT_ITEM#*/}"
        ITEM="${REMAIN%%/*}"
        REMAIN2="${REMAIN#*/}"
        if [[ "$part_count" -eq 4 ]]; then
            SECTION="${REMAIN2%%/*}"
            FIELD="${REMAIN2#*/}"
        else
            SECTION_FIELD="${REMAIN2#*/}"
            SECTION="${SECTION_FIELD%%/*}"
            FIELD="${SECTION_FIELD#*/}"
        fi
        "/mnt/c/Program Files/1Password CLI/op.exe" read "op://${VAULT}/${ITEM}/${SECTION}/${FIELD}" --account "my.1password.com"
    else
        echo "ERROR: Invalid path format" >&2
        exit 1
    fi
else
    ITEM="$1"
    VAULT="$2"
    "/mnt/c/Program Files/1Password CLI/op.exe" item get "$ITEM" --vault "$VAULT" --format json
fi