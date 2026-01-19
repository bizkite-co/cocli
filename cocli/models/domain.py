from typing_extensions import Annotated
from pydantic import AfterValidator

def to_lowercase_domain(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("string required")
    
    # Use urllib.parse to handle complex URLs consistently
    from urllib.parse import urlparse
    
    # If it doesn't have a protocol, urlparse won't identify the netloc
    if "://" not in value:
        # Prepend a dummy protocol to help parsing
        parsed = urlparse(f"http://{value}")
    else:
        parsed = urlparse(value)
        
    host = parsed.netloc or parsed.path
    
    # Clean up the host
    if host.startswith("www."):
        host = host[4:]
        
    # Split by colon to remove port if present
    host = host.split(":")[0]
    
    # Final strip of any stray slashes or spaces
    return host.strip("/ ").lower()

Domain = Annotated[str, AfterValidator(to_lowercase_domain)]
