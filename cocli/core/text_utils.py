from __future__ import annotations
import re
from typing import Optional

def slugify(text: str, max_length: Optional[int] = None) -> str:
    """
    Converts text to a filesystem-friendly slug.
    Preserves forward slashes (/) to support namespacing.
    Replaces other non-alphanumeric characters with dashes.
    Truncates to max_length if provided.
    """
    if not text:
        return ""
    text = str(text).lower().strip()
    # Replace any character that is NOT alphanumeric, underscore, or forward slash with a dash
    text = re.sub(r'[^a-z0-9/_]+', '-', text)
    # Ensure we don't have multiple dashes or dashes next to slashes
    text = re.sub(r'-+', '-', text)
    text = re.sub(r'-?/-?', '/', text)
    s = text.strip('-')
    
    if max_length:
        s = s[:max_length]
    return s

def parse_postal_address(full_address: Optional[str]) -> dict[str, Optional[str]]:
    """Conservative postal-address parser (US + international).

    Replaces the US-only heuristics in the old parse_address_components and
    Company.parse_full_address so every caller shares one parser and the two
    cannot diverge (task-agent: international-location-data-from-google-maps-
    detail-scrapes).

    Rules:
    - Last comma piece that is a known English country name or alpha-2 code
      becomes ``country`` stored as the alpha-2 code (``Denmark`` -> ``DK``).
      An unknown last piece stays in the text and country stays empty.
    - A remaining ``ST 12345`` piece keeps the US split (state + zip).
    - A remaining ``1870 Frederiksberg`` piece peels a leading postal code
      off the locality. Never writes a postal code alone into ``city``.
    - Anything else (e.g. UK ``London SW1A 2AA``) leaves city and postal
      code empty; the full address string remains the record of truth.

    Keys: street_address, city, state, zip, country (None when unknown).
    """
    components: dict[str, Optional[str]] = {
        "street_address": None,
        "city": None,
        "state": None,
        "zip": None,
        "country": None,
    }

    if not full_address or "," not in full_address:
        return components

    from cocli.core.countries import country_code_for

    parts = [p.strip() for p in str(full_address).split(",") if p.strip()]
    if len(parts) < 2:
        return components
    # Drop empty between parts handled above.

    # 1) Country: exact match on the last piece (English name or alpha-2).
    code = country_code_for(parts[-1])
    if code and (len(parts[-1]) <= 40):
        components["country"] = code
        parts.pop()

    if len(parts) < 2:
        return components

    # 2) US state + ZIP: 'TX 75094' / 'TX 75094-1234'.
    state_zip = re.fullmatch(r"([A-Z]{2})\s+(\d{5})(?:-(\d{4}))?", parts[-1])
    if state_zip:
        components["state"] = state_zip.group(1)
        components["zip"] = state_zip.group(2)
        parts.pop()

    if len(parts) < 2:
        return components

    # 3) Leading postal code glued to the locality: '1870 Frederiksberg'.
    postal_city = re.fullmatch(r"(\d{4,6})(?:\s*-(?:\d{1,4}))?\s+(\D.*)", parts[-1])
    if postal_city:
        components["zip"] = postal_city.group(1)
        components["city"] = postal_city.group(2).strip()
        parts.pop()

    if parts:
        components["street_address"] = parts[0]

    # 4) A remaining bare locality with no digits (no postal glue like
    # "London SW1A 2AA" - that stays unparsed) is still a city.
    if len(parts) >= 2 and not any(ch.isdigit() for ch in parts[-1]):
        components["city"] = parts[-1]

    return components


def parse_address_components(full_address: Optional[str]) -> dict[str, Optional[str]]:
    """Legacy US-oriented component slice over parse_postal_address.

    Kept for the quarantined legacy models (turboship_legacy,
    legacy_prospect); live callers use parse_postal_address directly.
    """
    full = parse_postal_address(full_address)
    return {
        "street_address": full["street_address"],
        "city": full["city"],
        "state": full["state"],
        "zip": full["zip"],
    }

def calculate_company_hash(name: Optional[str], street: Optional[str], zip_code: Optional[str]) -> Optional[str]:
    """
    Generates a human-readable unique identifier for a company location.
    Format: slug(name)[:8]-slug(street)[:8]-zip[:5]
    Returns None if street or zip is missing to prevent toxic collisions.
    """
    if not name or not street or not zip_code:
        return None
        
    n = slugify(name)[:8]
    s = slugify(street)[:8]
    
    # Extract first 5 digits of zip
    z_match = re.search(r'\d{5}', str(zip_code))
    if not z_match:
        return None
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

def extract_domain(url: Optional[str]) -> Optional[str]:
    """
    Extracts the base domain from a URL, stripping 'www.' and paths.
    """
    if not url:
        return None
        
    from urllib.parse import urlparse
    
    try:
        if "://" not in url:
            url = "http://" + url
            
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        if not domain:
            return None
            
        # Strip www.
        if domain.startswith("www."):
            domain = domain[4:]
            
        # Strip common ports if present
        if ":" in domain:
            domain = domain.split(":")[0]
            
        return domain
    except Exception:
        return None
