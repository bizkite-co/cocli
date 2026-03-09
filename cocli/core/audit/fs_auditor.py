from pathlib import Path
from typing import List, Optional, Any
from pydantic import BaseModel, Field
from enum import Enum
from cocli.core.paths import paths

class AuditStatus(str, Enum):
    VALID = "VALID"
    MISSING = "MISSING"
    ORPHAN = "ORPHAN"
    ERROR = "ERROR"

class AuditNode(BaseModel):
    name: str
    path: Path
    status: AuditStatus
    is_dir: bool
    children: List['AuditNode'] = Field(default_factory=list)
    message: Optional[str] = None

    model_config = {"arbitrary_types_allowed": True}

class FsAuditor:
    """
    Audits the filesystem for OMAP (Ordinant Mapping) compliance.
    Compares Actual state vs Expected "Screaming Architecture" rules.
    """
    def __init__(self, root: Optional[Path] = None):
        self.root = root or paths.root
        
    def audit_campaigns(self, campaign_name: Optional[str] = None) -> AuditNode:
        """Audits the campaigns/ directory structure."""
        campaigns_root = self.root / "campaigns"
        node = AuditNode(
            name="campaigns",
            path=campaigns_root,
            is_dir=True,
            status=AuditStatus.VALID if campaigns_root.exists() else AuditStatus.MISSING
        )
        
        if not node.path.exists():
            return node
            
        # If specific campaign requested, only audit that
        if campaign_name:
            target = node.path / campaign_name
            node.children.append(self._audit_single_campaign(target))
        else:
            # Audit all folders in campaigns/
            for item in node.path.iterdir():
                if item.is_dir():
                    node.children.append(self._audit_single_campaign(item))
                else:
                    node.children.append(AuditNode(
                        name=item.name, path=item, is_dir=False, 
                        status=AuditStatus.ORPHAN, message="Files not allowed in campaigns root"
                    ))
        return node

    def _audit_single_campaign(self, path: Path) -> AuditNode:
        """Validates a single campaign folder structure."""
        # Expected sub-folders in a campaign
        expected = ["config.toml", "queues", "indexes", "recovery"]
        node = AuditNode(
            name=path.name,
            path=path,
            is_dir=True,
            status=AuditStatus.VALID if path.exists() else AuditStatus.MISSING
        )
        
        if not path.exists():
            return node
            
        actual_items = {p.name: p for p in path.iterdir()}
        
        for name in expected:
            item_path = path / name
            status = AuditStatus.VALID if item_path.exists() else AuditStatus.MISSING
            node.children.append(AuditNode(
                name=name, path=item_path, is_dir=item_path.is_dir() if item_path.exists() else name != "config.toml",
                status=status
            ))
            
        # Check for orphans
        for name, item_path in actual_items.items():
            if name not in expected:
                node.children.append(AuditNode(
                    name=name, path=item_path, is_dir=item_path.is_dir(),
                    status=AuditStatus.ORPHAN, message="Unknown campaign component"
                ))
                
        return node

    def audit_queues(self) -> AuditNode:
        """Audits the global or campaign queues/ directory."""
        # This is complex because queues can be global or per-campaign
        # Let's start with global queues/
        queues_root = self.root / "queues"
        node = AuditNode(
            name="queues",
            path=queues_root,
            is_dir=True,
            status=AuditStatus.VALID if queues_root.exists() else AuditStatus.MISSING
        )
        
        if not queues_root.exists():
            return node
            
        for queue_dir in queues_root.iterdir():
            if not queue_dir.is_dir():
                node.children.append(AuditNode(
                    name=queue_dir.name, path=queue_dir, is_dir=False,
                    status=AuditStatus.ORPHAN, message="Files not allowed in queues root"
                ))
                continue
                
            # Audit queue sub-structure (pending/completed/active)
            q_node = AuditNode(name=queue_dir.name, path=queue_dir, is_dir=True, status=AuditStatus.VALID)
            for sub in ["pending", "completed", "active"]:
                sub_path = queue_dir / sub
                q_node.children.append(AuditNode(
                    name=sub, path=sub_path, is_dir=True, 
                    status=AuditStatus.VALID if sub_path.exists() else AuditStatus.MISSING
                ))
            node.children.append(q_node)
            
        return node

def dump_audit_tree(node: AuditNode, console: Optional[Any] = None, tree: Optional[Any] = None) -> Any:
    """Renders the audit tree using Rich's Tree widget."""
    from rich.tree import Tree
    from rich.text import Text
    
    colors = {
        AuditStatus.VALID: "green",
        AuditStatus.MISSING: "red",
        AuditStatus.ORPHAN: "yellow",
        AuditStatus.ERROR: "bold red"
    }
    
    status_color = colors.get(node.status, "white")
    status_text = Text(f"[{node.status:8}] ", style=status_color)
    name_text = Text(node.name)
    if node.message:
        name_text.append(f" ({node.message})", style="italic dim")
    
    label = Text.assemble(status_text, name_text)
    
    if tree is None:
        tree = Tree(label)
    else:
        tree = tree.add(label)
        
    for child in node.children:
        dump_audit_tree(child, tree=tree)
        
    return tree
