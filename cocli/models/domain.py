from typing_extensions import Annotated
from pydantic import AfterValidator

def to_lowercase_domain(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("string required")
    
    # remove protocol
    value = value.replace("https://", "").replace("http://", "")
    # remove www.
    if value.startswith("www."):
        value = value[4:]
    # remove trailing slash
    if value.endswith("/"):
        value = value[:-1]
        
    return value.lower()

Domain = Annotated[str, AfterValidator(to_lowercase_domain)]
