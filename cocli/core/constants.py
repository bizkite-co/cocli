# POLICY: frictionless-data-policy-enforcement
"""
Core constants for the cocli project, ensuring no circular dependencies 
between models and core utilities.
"""

# Frictionless Data USV Control Characters
UNIT_SEP = "\x1f" # Unit Separator (terminates fields)
RECORD_SEP = "\x1e" # Record Separator (terminates lines)

# Default encoding for all filesystem operations
DEFAULT_ENCODING = "utf-8"
