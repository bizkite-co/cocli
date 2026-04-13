#!/bin/bash
echo "DEBUG: Writing to 1Password via Windows CLI" >&2
export OP_ACCOUNT=my.1password.com
"/mnt/c/Program Files/1Password CLI/op.exe" read "$1" --account "my.1password.com"