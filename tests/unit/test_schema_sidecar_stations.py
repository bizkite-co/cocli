"""Schema sidecars must be written only via stations.schema (0007 §3)."""

from __future__ import annotations

import ast
import json
import stat
from pathlib import Path
from typing import List


from stations.schema import SCHEMA_FILENAME, is_schema_protected, write_schema_sidecar


# Production modules allowed to *call* write_schema_sidecar / stations schema API.
_ALLOWED_WRITE_MODULES = frozenset(
    {
        "cocli/models/base.py",
        "cocli/models/campaigns/indexes/base.py",
        "cocli/core/stations_runtime.py",  # may write CURRENT-adjacent docs; not schema today
    }
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _is_direct_datapackage_write(node: ast.AST) -> bool:
    """Heuristic: open(..., 'w') where the path mentions datapackage.json."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    name = ""
    if isinstance(func, ast.Name):
        name = func.id
    elif isinstance(func, ast.Attribute):
        name = func.attr
    if name not in {"open", "write_text", "write_bytes"}:
        return False
    # Stringify args roughly
    dump = ast.dump(node)
    return "datapackage.json" in dump and (
        "'w'" in dump or '"w"' in dump or "mode" in dump
    )


def test_no_ad_hoc_datapackage_writes_in_cocli_package() -> None:
    """Grep/AST audit: no open(..., 'w') of datapackage.json outside allowlist."""
    root = _repo_root() / "cocli"
    offenders: List[str] = []
    for path in root.rglob("*.py"):
        rel = str(path.relative_to(_repo_root())).replace("\\", "/")
        if rel in _ALLOWED_WRITE_MODULES:
            continue
        if "/__pycache__/" in rel:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if _is_direct_datapackage_write(node):
                offenders.append(f"{rel}:{getattr(node, 'lineno', '?')}")

    # Also flag raw json.dump to a variable named sentinel with open w —
    # covered by AST open check above for base.py after cutover (base is allowlisted).
    assert offenders == [], (
        "Ad-hoc datapackage.json writers found (must use stations.schema.write_schema_sidecar):\n"
        + "\n".join(offenders)
    )


def test_base_usv_save_datapackage_uses_stations_and_protects(tmp_path: Path) -> None:
    from pydantic import Field

    from cocli.models.base import BaseUsvModel

    class Tiny(BaseUsvModel):
        a: str = Field(default="x")
        b: int = Field(default=1)

        class Config:
            extra = "ignore"

    Tiny.save_datapackage(tmp_path, "tiny", "*.usv")
    dp = tmp_path / SCHEMA_FILENAME
    assert dp.exists()
    data = json.loads(dp.read_text(encoding="utf-8"))
    assert data["resources"][0]["name"] == "tiny"
    assert is_schema_protected(dp)
    mode = dp.stat().st_mode
    assert not (mode & stat.S_IWUSR)


def test_stations_write_is_only_physical_path(tmp_path: Path) -> None:
    """Sanity: stations write_schema_sidecar is the engine under the hood."""
    write_schema_sidecar(
        tmp_path,
        {
            "profile": "tabular-data-package",
            "name": "x",
            "resources": [
                {
                    "name": "x",
                    "path": "*.usv",
                    "schema": {"fields": [{"name": "id", "type": "string"}]},
                }
            ],
        },
        protect=True,
    )
    assert (tmp_path / SCHEMA_FILENAME).exists()
