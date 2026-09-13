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

# Pre-existing call sites that predate this guard. Do NOT add to this list -
# fix the call site to go through cocli.core.reporting.get_boto3_session()
# instead. If a new file genuinely cannot use get_boto3_session, that is a
# design conversation, not a quiet addition here.
BOTO3_SESSION_ALLOWED = {
    "cocli/core/reporting.py",
    "cocli/application/email_service.py",
    "cocli/application/web_service.py",
    "cocli/application/reporting_service.py",
    "cocli/application/ses_suppression_service.py",
    "cocli/application/data_sync_service.py",
    "cocli/core/domain_index_manager.py",
    "cocli/core/queue/gm_item_sqs_queue.py",
    "cocli/commands/web.py",
    "scripts/create_cognito_user.py",
    "scripts/update_campaign_infra_config.py",
    "scripts/count_enriched_domains.py",
    "scripts/migrate_filesystem_queue_v2.py",
    "scripts/provision_pi_iot.py",
    "scripts/push_queue.py",
    "scripts/migrate_s3_paths.py",
    "scripts/deploy_rpi_creds.py",
    "scripts/manage_campaign_identity.py",
    "scripts/migrate_s3_domain_keys.py",
    "scripts/debug_s3_container.py",
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


def test_no_new_direct_boto3_session_construction() -> None:
    violations = []
    for path in _iter_python_files():
        rel = _rel(path)
        if rel in BOTO3_SESSION_ALLOWED:
            continue
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
                violations.append(f"{rel}:{node.lineno}")

    assert not violations, (
        "New code must build AWS sessions via "
        "cocli.core.reporting.get_boto3_session(config, profile_name=...), "
        "not boto3.Session(...) directly - direct construction bypasses the "
        "1Password-routed credential resolution and silently falls back to "
        "boto3's native (and much more fragile) credential_process handling. "
        "Violations (not grandfathered - fix the call site, don't extend "
        "BOTO3_SESSION_ALLOWED in this test):\n" + "\n".join(violations)
    )
