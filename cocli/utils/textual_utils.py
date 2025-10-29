import re

def sanitize_id(text: str) -> str:
    """Sanitizes a string to be a valid Textual widget ID.

    Textual IDs must be `^[a-zA-Z_][a-zA-Z0-9_-]*$`.
    This function converts the text to lowercase, replaces invalid characters with
    hyphens, and prepends an underscore if the ID starts with a number.
    """
    if not text: # Handle empty string input
        return "_unknown-id"

    # Convert to lowercase
    sanitized = text.lower()
    # Replace invalid characters with hyphens
    sanitized = re.sub(r'[^a-z0-9_-]', '-', sanitized)
    # Remove leading/trailing hyphens
    sanitized = sanitized.strip('-')
    # If the ID starts with a number, prepend an underscore
    if sanitized and sanitized[0].isdigit():
        sanitized = f"_{sanitized}"
    
    if not sanitized: # If after sanitization, it becomes empty (e.g., input was only invalid chars)
        return "_unknown-id"

    return sanitized
