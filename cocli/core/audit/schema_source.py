import re
import os
from pathlib import Path
from typing import List, Pattern

class SchemaSource:
    """
    Manages the structural source of truth from docs/_schema/data-root/.
    Allows matching real paths against architectural templates.
    """
    def __init__(self, schema_root: Path):
        self.schema_root = schema_root
        self.templates: List[str] = self._load_templates()
        self.patterns: List[Pattern[str]] = self._compile_patterns()

    def _load_templates(self) -> List[str]:
        templates = []
        if not self.schema_root.exists():
            return []
            
        for root, dirs, files in os.walk(self.schema_root):
            rel_root = Path(root).relative_to(self.schema_root)
            
            # Add directories as templates
            for d in dirs:
                templates.append(str(rel_root / d))
                
            # Add files as templates
            for f in files:
                if f != "README.md":
                    templates.append(str(rel_root / f))
        return templates

    def _compile_patterns(self) -> List[Pattern[str]]:
        patterns = []
        # Replace {variable} with a regex that matches a single path component
        var_regex = re.compile(r'\{[^}]+\}')
        
        for template in self.templates:
            # Escape literal dots and other regex chars, but keep {var} parts
            escaped = re.escape(template)
            pattern_str = escaped.replace(r'\{', '{').replace(r'\}', '}')
            
            # Replace {var} with [^/]+
            pattern_str = var_regex.sub(r'[^/]+', pattern_str)
            
            # Anchor to start and end
            patterns.append(re.compile(f"^{pattern_str}$"))
        return patterns

    def is_compliant(self, rel_path: str) -> bool:
        """Checks if a relative path matches any architectural template."""
        normalized = str(Path(rel_path))
        
        # Exact match for root-level files/dirs
        if normalized == ".":
            return True
            
        for pattern in self.patterns:
            if pattern.match(normalized):
                return True
        return False

    def get_template_for(self, rel_path: str) -> str:
        """Returns the matching template string if found."""
        normalized = str(Path(rel_path))
        for i, pattern in enumerate(self.patterns):
            if pattern.match(normalized):
                return self.templates[i]
        return "Unknown"
