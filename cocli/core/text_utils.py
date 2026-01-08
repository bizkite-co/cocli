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

def is_valid_email(email: str) -> bool:
    """
    Performs basic validation to ensure the string is a likely email address
    and not a resource file (png, jpg, js, etc) or a versioned library.
    """
    if not email:
        return False
        
    # Remove whitespace and common prefixes
    email = email.strip().lower()
    if email.startswith("email:"):
        email = email[6:].strip()
    
    if "@" not in email:
        return False
    
    # 1. Check for common resource extensions
    junk_extensions = {
        '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.ico',
        '.js', '.css', '.pdf', '.zip', '.mp4', '.mp3', '.woff', '.woff2',
        '.exe', '.dmg', '.pkg'
    }
    if any(email.endswith(ext) for ext in junk_extensions):
        return False
    
    # 2. Extract parts
    try:
        user_part, domain_part = email.rsplit("@", 1)
    except ValueError:
        return False

    # 3. Basic structure check
    if not user_part or not domain_part:
        return False
        
    if "." not in domain_part:
        return False
        
    # 4. Filter out versioned strings (e.g. react@16.14.0.js)
    # If the domain part looks like a version number (3 parts with dots)
    if re.match(r"^\d+\.\d+\.\d+", domain_part):
        return False
        
    # 5. Filter out IP addresses as domains
    if re.match(r"^\d+\.\d+\.\d+\.\d+$", domain_part):
        return False
        
    # 6. Check for common junk in user part (e.g. 'image@2x')
    if user_part in ['image', 'img', 'logo', 'icon', 'bg', 'banner']:
        # This might be too aggressive, but in our context it's usually junk if it has a weird domain
        if not domain_part.endswith(('.com', '.net', '.org')):
            return False

    return True
