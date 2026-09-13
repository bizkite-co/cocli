"""Guards the "one credential utility" invariant.

cocli/core/secrets.py's SecretProvider (backed by cocli/utils/op_utils.py) is
the only sanctioned way to read a 1Password secret, and
cocli/core/reporting.py's get_boto3_session() is the only sanctioned way to
build a boto3.Session for a named AWS profile. Both exist specifically
because ad hoc reimplementations of 1Password/AWS-credential resolution have
broken in incompatible ways: scripts/provision_pi_iot.py's raw
boto3.Session(profile_name=...) bypasses the op_utils-routed credential path
entirely and falls back to boto3's native credential_process, which shells
out to the far more fragile external ~/.aws/scripts/1password-aws-credentials.sh
(no WSL binfmt-interop fallback, no shared 1Password-unlock cache) - see the
2026-09-12 incident where that path failed with "authorization timeout" and
"Exec format error" while cocli's own op_utils.py handled the same profile
fine.

This test fails fast the next time someone reinvents either path, instead of
relying on it silently breaking in some rarely-run script months later.
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# The only file allowed to import the 1Password SDK directly.
ONEPASSWORD_SDK_ALLOWED = {"cocli/utils/op_utils.py"}

# Pre-existing call sites that predate this guard, keyed by file with the
# exact number of boto3.Session(...) call expressions AST currently finds
# there (a ternary like `Session(...) if x else Session()` counts as two).
# Do NOT bump a count or add a new key - fix the call site to go through
# cocli.core.reporting.get_boto3_session() instead, and lower the count (or
# drop the key entirely) as you fix each one. If a new file genuinely cannot
# use get_boto3_session, that's a design conversation, not a quiet edit here.
BOTO3_SESSION_ALLOWED = {
    "cocli/core/reporting.py": 9,
    "cocli/application/email_service.py": 2,
    "cocli/application/web_service.py": 1,
    "cocli/application/reporting_service.py": 1,
    "cocli/application/ses_suppression_service.py": 2,
    "cocli/application/data_sync_service.py": 1,
    "cocli/core/domain_index_manager.py": 1,
    "cocli/core/queue/gm_item_sqs_queue.py": 2,
    "scripts/migrate_filesystem_queue_v2.py": 1,
    "scripts/migrate_s3_paths.py": 1,
    "scripts/migrate_s3_domain_keys.py": 1,
    "scripts/debug_s3_container.py": 2,
}


def _iter_python_files() -> list[Path]:
    files = []
    for base in ("cocli", "scripts"):
        for path in (REPO_ROOT / base).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            files.append(path)
    return files


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT).as_posix())


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_onepassword_sdk_import_confined_to_op_utils() -> None:
    violations = []
    for path in _iter_python_files():
        rel = _rel(path)
        if rel in ONEPASSWORD_SDK_ALLOWED:
            continue
        for node in ast.walk(_parse(path)):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("onepassword"):
                violations.append(f"{rel}:{node.lineno}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("onepassword"):
                        violations.append(f"{rel}:{node.lineno}")

    assert not violations, (
        "Only cocli/utils/op_utils.py may import the 1Password SDK directly. "
        "Read secrets via cocli.core.secrets.get_secret_provider() instead. "
        "Violations:\n" + "\n".join(violations)
    )


def _count_boto3_session_calls(path: Path) -> list[int]:
    lines = []
    for node in ast.walk(_parse(path)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "Session"
            and isinstance(func.value, ast.Name)
            and func.value.id == "boto3"
        ):
            lines.append(node.lineno)
    return lines


def test_no_new_direct_boto3_session_construction() -> None:
    unexpected = []
    for path in _iter_python_files():
        rel = _rel(path)
        allowed = BOTO3_SESSION_ALLOWED.get(rel, 0)
        found = _count_boto3_session_calls(path)
        if len(found) > allowed:
            unexpected.append(
                f"{rel}: found {len(found)} boto3.Session(...) call(s) at "
                f"lines {found}, only {allowed} grandfathered"
            )

    assert not unexpected, (
        "New code must build AWS sessions via "
        "cocli.core.reporting.get_boto3_session(config, profile_name=...), "
        "not boto3.Session(...) directly - direct construction bypasses the "
        "1Password-routed credential resolution and silently falls back to "
        "boto3's native (and much more fragile) credential_process handling. "
        "A grandfathered file gained a NEW call site, or a new file added "
        "one - fix the call site rather than raising its count in "
        "BOTO3_SESSION_ALLOWED:\n" + "\n".join(unexpected)
    )


def test_boto3_session_allowlist_has_no_stale_entries() -> None:
    """Catches counts left too high after a call site is fixed/removed."""
    stale = []
    for rel, allowed in BOTO3_SESSION_ALLOWED.items():
        path = REPO_ROOT / rel
        found = len(_count_boto3_session_calls(path)) if path.exists() else 0
        if found < allowed:
            stale.append(f"{rel}: allowlisted for {allowed}, only {found} remain - lower the count")

    assert not stale, "\n".join(stale)
