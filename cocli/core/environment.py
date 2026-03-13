import os
from enum import Enum

class Environment(str, Enum):
    DEV = "dev"
    PROD = "prod"
    UAT = "uat"
    TEST = "test"

def get_environment() -> Environment:
    """
    Returns the current active environment based on COCLI_ENV.
    Defaults to PROD if not set.
    """
    env_str = os.environ.get("COCLI_ENV", "prod").lower()
    try:
        return Environment(env_str)
    except ValueError:
        # Fallback for unexpected values
        if "test" in env_str:
            return Environment.TEST
        return Environment.PROD

def is_prod() -> bool:
    return get_environment() == Environment.PROD

def is_dev() -> bool:
    return get_environment() == Environment.DEV

def is_test() -> bool:
    return get_environment() == Environment.TEST
