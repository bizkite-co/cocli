#!/bin/bash
export OP_ACCOUNT=my.1password.com
OP_PATH="$1"
VAULT_ITEM="${OP_PATH#op://}"
VAULT="${VAULT_ITEM%%/*}"
ITEM_SECTION_FIELD="${VAULT_ITEM#*/}"
ITEM="${ITEM_SECTION_FIELD%%/*}"
"/mnt/c/Program Files/1Password CLI/op.exe" item get "$ITEM" --vault "$VAULT" --format json