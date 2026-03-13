# Transition to 1Password Python SDK

Replace the op CLI-based secret retrieval with the official 1Password Python SDK. 1. This will improve reliability on Windows (triggering Hello/Biometrics). 2. It enables the use of Service Accounts for headless operation on Raspberry Pi nodes. 3. Refactor cocli/utils/op_utils.py to use the SDK.
