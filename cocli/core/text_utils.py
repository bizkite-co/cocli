import re

def slugify(text: str) -> str:
    """Converts text to a filesystem-friendly slug."""
    text = text.lower()
    text = re.sub(r'[\s\W]+', '-', text)
    return text.strip('-')
