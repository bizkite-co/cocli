import yaml
import re
from typing import Any

class ResilientLoader(yaml.SafeLoader):
    """A YAML loader that handles legacy cocli Python object tags."""
    pass

def construct_python_object(loader: yaml.SafeLoader, suffix: str, node: yaml.Node) -> Any:
    """Handles !!python/object/new:... tags by extracting the first element if it's a list."""
    try:
        if isinstance(node, yaml.SequenceNode):
            data = loader.construct_sequence(node)
            if data and isinstance(data, list):
                return data[0]
            return data
        elif isinstance(node, yaml.ScalarNode):
            return loader.construct_scalar(node)
        elif isinstance(node, yaml.MappingNode):
            return loader.construct_mapping(node)
    except Exception:
        pass
    return str(node)

# Register multi-constructors for legacy Python tags
yaml.add_multi_constructor('tag:yaml.org,2002:python/object/new:', construct_python_object, Loader=ResilientLoader)
yaml.add_multi_constructor('!!python/object/new:', construct_python_object, Loader=ResilientLoader)

def resilient_safe_load(stream: str) -> Any:
    """
    Safely loads YAML, with additional resilience for known legacy cocli tags.
    """
    try:
        return yaml.load(stream, Loader=ResilientLoader)
    except Exception:
        # Fallback: try to strip the problematic tags with regex if they are causing issues
        # This is a bit of a hack but helps recover data when the tag structure is weird
        sanitized = re.sub(r'!!python/object/new:cocli\.models\.email_address\.EmailAddress', '', stream)
        try:
            return yaml.safe_load(sanitized)
        except Exception:
            return None