import re
from typing import Optional

def slugify(text: str) -> str:
    """
    Converts text to a filesystem-friendly slug.
    Preserves forward slashes (/) to support namespacing.
    Replaces other non-alphanumeric characters with dashes.
    """
    if not text:
        return ""
    text = str(text).lower().strip()
    # Replace any character that is NOT alphanumeric, underscore, or forward slash with a dash
    text = re.sub(r'[^a-z0-9/_]+', '-', text)
    # Ensure we don't have multiple dashes or dashes next to slashes
    text = re.sub(r'-+', '-', text)
    text = re.sub(r'-?/-?', '/', text)
    return text.strip('-')

def calculate_company_hash(name: str, street: Optional[str], zip_code: Optional[str]) -> str:
    """
    Generates a human-readable unique identifier for a company location.
    Format: slug(name)[:8]-slug(street)[:8]-zip[:5]
    """
    n = slugify(name or "unknown")[:8]
    s = slugify(street or "none")[:8]
    # Extract first 5 digits of zip
    z = "00000"
    if zip_code:
        z_match = re.search(r'\d{5}', str(zip_code))
        if z_match:
            z = z_match.group(0)
    
    return f"{n}-{s}-{z}"

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
    
    # 1. Check for common resource extensions (anywhere in the string to catch logo@2x.png)
    junk_patterns = [
        r'\.png$', r'\.jpg$', r'\.jpeg$', r'\.gif$', r'\.svg$', r'\.webp$', r'\.ico$',
        r'\.js$', r'\.css$', r'\.pdf$', r'\.zip$', r'\.mp4$', r'\.mp3$', r'\.woff', 
        r'\.exe$', r'\.dmg$', r'\.pkg$', r'@\d+x', r'\.png\b'
    ]
    if any(re.search(pattern, email) for pattern in junk_patterns):
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

def parse_frontmatter(content: str) -> Optional[str]:
    """
    Extracts YAML frontmatter from a markdown string.
    Returns the YAML string if found, otherwise None.
    Handles '---' inside YAML values correctly by only splitting on line-start delimiters.
    Supports malformed start headers like ---key: val
    """
    if not content.startswith("---"):
        return None
        
    # Standard case: starts with ---\n
    if content.startswith("---\n") or content.startswith("---\r\n"):
        parts = re.split(r'^---\s*$', content, maxsplit=2, flags=re.MULTILINE)
        if len(parts) >= 2:
            return parts[1]
    
    # Malformed case: starts with ---key: val
    # We find the NEXT occurrence of ^---$
    match = re.search(r'^---\s*$', content, re.MULTILINE)
    if match:
        end_idx = match.start()
        # Frontmatter is everything between the first 3 chars and the start of the next ---
        return content[3:end_idx]
        
    return None
