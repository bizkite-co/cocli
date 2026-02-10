import re
from typing import Optional, Dict

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

def parse_address_components(full_address: Optional[str]) -> Dict[str, Optional[str]]:
    """
    Conservatively extracts street, city, state, and zip from a full address string.
    Format: '123 Main St, City, ST 12345'
    """
    components = {
        "street_address": None,
        "city": None,
        "state": None,
        "zip": None
    }
    
    if not full_address or "," not in full_address:
        return components
        
    parts = [p.strip() for p in full_address.split(",")]
    
    # Heuristic for US Addresses:
    # Last part usually contains State and ZIP: 'TX 75094'
    if len(parts) >= 2:
        last_part = parts[-1]
        zip_match = re.search(r'(\d{5})', last_part)
        if zip_match:
            components["zip"] = zip_match.group(1)
            # State is usually the word before the zip
            state_match = re.search(r'([A-Z]{2})', last_part)
            if state_match:
                components["state"] = state_match.group(1)
        
        # If we have 3 parts: [Street, City, State Zip]
        if len(parts) >= 3:
            components["street_address"] = parts[0]
            components["city"] = parts[1]
        # If we only have 2 parts: [Street/City Mix, State Zip]
        elif len(parts) == 2:
            components["street_address"] = parts[0]

    return components

def calculate_company_hash(name: Optional[str], street: Optional[str], zip_code: Optional[str]) -> Optional[str]:
    """
    Generates a human-readable unique identifier for a company location.
    Format: slug(name)[:8]-slug(street)[:8]-zip[:5]
    """
    if not name:
        return None
        
    n = slugify(name)[:8]
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
    if re.match(r"^\d+\.\d+\.\d+", domain_part):
        return False
        
    # 5. Filter out IP addresses as domains
    if re.match(r"^\d+\.\d+\.\d+\.\d+$", domain_part):
        return False
        
    # 6. Check for common junk in user part (e.g. 'image@2x')
    if user_part in ['image', 'img', 'logo', 'icon', 'bg', 'banner']:
        if not domain_part.endswith(('.com', '.net', '.org')):
            return False

    return True

def parse_frontmatter(content: str) -> Optional[str]:
    """
    Extracts YAML frontmatter from a markdown string.
    Returns the YAML string if found, otherwise None.
    """
    if not content.startswith("---"):
        return None
        
    # Standard case: starts with ---\n
    if content.startswith("---\n") or content.startswith("---\r\n"):
        parts = re.split(r'^---\s*$', content, maxsplit=2, flags=re.MULTILINE)
        if len(parts) >= 2:
            return parts[1]
    
    # Malformed case: starts with ---key: val
    match = re.search(r'^---\s*$', content, re.MULTILINE)
    if match:
        end_idx = match.start()
        return content[3:end_idx]
        
    return None