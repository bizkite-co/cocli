import re

def slugify(text: str) -> str:
    """Converts text to a filesystem-friendly slug (aggressive, replaces dots with dashes)."""
    text = text.lower()
    text = re.sub(r'[\s\W]+', '-', text)
    return text.strip('-')

def slugdotify(text: str) -> str:
    """
    Converts text to a filesystem-friendly slug but PRESERVES DOTS (.).
    Useful for domain names (example.com) and email user parts (john.doe).
    Replaces other non-alphanumeric characters with dashes.
    """
    text = text.lower().strip()
    # Replace any character that is NOT alphanumeric, underscore, or dot with a dash
    text = re.sub(r'[^\w\.]+', '-', text)
    return text.strip('-')
