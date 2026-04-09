#!/bin/bash
echo "DEBUG: PATH=$PATH" >&2
echo "DEBUG: HOME=$HOME" >&2
export OP_ACCOUNT=my.1password.com
"/mnt/c/Program Files/1Password CLI/op.exe" read "$1" --account "my.1password.com"
