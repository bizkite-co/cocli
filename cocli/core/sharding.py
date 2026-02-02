def get_shard_id(identifier: str) -> str:
    """
    Returns a deterministic 1-character shard ID for a given identifier.
    Uses the 6th character (index 5) which is one character after the 
    common "ChIJ-" prefix, providing high variability and instant visibility.
    """
    if not identifier or len(identifier) < 6:
        return "_"
    
    return identifier[5]