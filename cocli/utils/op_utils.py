from __future__ import annotations

import logging
import json
import os
import shutil
import subprocess
from typing import Any, Optional, cast

logger = logging.getLogger(__name__)

_WIN_OP = "/mnt/c/Program Files/1Password CLI/op.exe"
_DEFAULT_OP_ACCOUNT = "my.1password.com"
_OP_READ_PAUSED = r"C:\Users\xgenx\.config\powershell\bin\op-read-paused.cmd"
_OP_READ_PAUSED_LINUX = "/mnt/c/Users/xgenx/.config/powershell/bin/op-read-paused.cmd"


def onepassword_cli_available() -> bool:
    """True if SDK-less 1Password I/O can run (linux op or Hello helper)."""
    if os.access("/usr/bin/op", os.X_OK):
        return True
    binary = shutil.which("op")
    if binary and not binary.lower().endswith(".exe"):
        return True
    return os.path.isfile(_OP_READ_PAUSED_LINUX)
_CMD_EXE_CANDIDATES = (
    "/mnt/c/Windows/System32/cmd.exe",
    "/mnt/c/WINDOWS/system32/cmd.exe",
)


def _op_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("OP_ACCOUNT", _DEFAULT_OP_ACCOUNT)
    return env


def _cmd_exe() -> Optional[str]:
    for path in _CMD_EXE_CANDIDATES:
        if os.path.isfile(path):
            return path
    return None


def run_windows_cmd(*args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    """Run a Windows command so Hello/op.exe work from WSL.

    Direct ``cmd.exe`` fails with Exec format error when binfmt WSLInterop
    is unregistered (common under systemd). ``/init`` still runs PE binaries.
    cwd is a Windows path so cmd.exe does not reject a WSL UNC cwd.
    """
    cmd_exe = _cmd_exe()
    if cmd_exe is None:
        raise FileNotFoundError("Windows cmd.exe not found under /mnt/c")
    argv = [cmd_exe, "/c", *args]
    if os.access("/init", os.X_OK):
        argv = ["/init", *argv]
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd="/mnt/c/Windows",
        env=_op_env(),
    )


def read_op_secrets(*op_paths: str) -> Optional[list[str]]:
    """Read one or two ``op://`` refs via op-read-paused (one Windows Hello).

    This is the same helper AWS ``credential_process`` uses. Two refs share
    one unlock session. Linux ``op`` does not raise Hello from WSL.
    """
    refs = [path for path in op_paths if path]
    if not refs:
        return None
    if not os.path.isfile(_OP_READ_PAUSED_LINUX):
        return None
    try:
        result = run_windows_cmd(_OP_READ_PAUSED, *refs, timeout=120)
    except (OSError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.debug("op-read-paused failed: %s", exc)
        return None
    if result.returncode != 0:
        err = (result.stderr or "").replace("\r", "").strip()
        logger.debug("op-read-paused exit %s: %s", result.returncode, err)
        return None
    lines = [line.strip() for line in result.stdout.replace("\r", "").splitlines() if line.strip()]
    if len(lines) < len(refs):
        return None
    return lines[: len(refs)]


def _read_via_linux_op(op_path: str) -> Optional[str]:
    """Native WSL/Linux ``op`` talks to 1Password desktop (Hello) without cmd.exe."""
    binary = shutil.which("op")
    if not binary or binary.lower().endswith(".exe"):
        if os.access("/usr/bin/op", os.X_OK):
            binary = "/usr/bin/op"
        else:
            return None
    try:
        result = subprocess.run(
            [binary, "read", op_path, "--account", _DEFAULT_OP_ACCOUNT],
            capture_output=True,
            text=True,
            env=_op_env(),
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.debug("linux op read failed: %s", exc)
        return None
    if result.returncode != 0:
        logger.debug("linux op read exit %s: %s", result.returncode, result.stderr.strip())
        return None
    value = result.stdout.strip()
    return value or None


def _read_via_windows_op(op_path: str) -> Optional[str]:
    """Last resort: Windows op.exe via WSL ``/init`` (binfmt interop is often missing)."""
    if not os.path.isfile(_WIN_OP):
        return None
    cmd = [_WIN_OP, "read", op_path, "--account", _DEFAULT_OP_ACCOUNT]
    if os.access("/init", os.X_OK):
        cmd = ["/init", *cmd]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=_op_env(),
            timeout=60,
            cwd="/mnt/c/Windows",
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.debug("windows op.exe read failed: %s", exc)
        return None
    if result.returncode != 0:
        logger.debug("windows op.exe exit %s: %s", result.returncode, result.stderr.strip())
        return None
    value = result.stdout.replace("\r", "").strip()
    return value or None


def get_op_secret(op_path: str) -> Optional[str]:
    """
    Retrieves a secret from 1Password.
    Priority:
    1. 1Password Python SDK (via OP_SERVICE_ACCOUNT_TOKEN or Local Biometrics).
    2. Fallback to 'op' CLI if SDK is not available or fails.

    Expects a path like 'op://Vault/Item/Field'
    """
    if not op_path or not op_path.startswith("op://"):
        return None

    # 1. Attempt SDK Retrieval
    try:
        from onepassword.sdk import Client as NewSDKClient  # type: ignore

        # New 1Password SDK (Official)
        if "OP_SERVICE_ACCOUNT_TOKEN" in os.environ:
            try:
                client = NewSDKClient.authenticate(
                    token=os.environ["OP_SERVICE_ACCOUNT_TOKEN"],
                    integration_name="cocli",
                    integration_version="0.1.0",
                )
                return cast(str, client.secrets.retrieve(op_path))
            except Exception as sdk_err:
                logger.debug(f"Official SDK retrieval failed: {sdk_err}")

    except ImportError:
        logger.debug("onepassword-sdk not found, falling back to CLI.")
    except Exception as e:
        logger.debug(f"SDK initialization failed: {e}")

    # 2. Linux ``op`` if a session is already open (no Hello).
    value = _read_via_linux_op(op_path)
    if value:
        return value

    # 3. op-read-paused.cmd via /init — this is the Windows Hello path
    # other AWS/cocli commands use (AHK pause + Windows op.exe).
    paused = read_op_secrets(op_path)
    if paused:
        return paused[0]

    value = _read_via_windows_op(op_path)
    if value:
        return value

    logger.error(
        "Failed to read 1Password path '%s' (SDK, linux op, op-read-paused, windows op.exe).",
        op_path,
    )
    return None


def get_op_item(item_id: str, vault: Optional[str] = None) -> Optional[dict[str, Any]]:
    """
    Retrieves a full item from 1Password as a dictionary.
    Currently only supports CLI fallback for complex item retrieval.
    """
    # 1. SDK Implementation (To be added when needed/supported by SDK for full items)

    # 2. Fallback to 'op' CLI
    try:
        cmd = ["op", "item", "get", item_id, "--format", "json"]
        if vault:
            cmd.extend(["--vault", vault])

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return cast(dict[str, Any], json.loads(result.stdout))
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to get 1Password item '{item_id}' via CLI: {e.stderr}")
        return None
    except FileNotFoundError:
        logger.error("The 'op' CLI was not found in the system path.")
        return None
    except Exception as e:
        logger.error(f"Unexpected error retrieving 1Password item via CLI: {e}")
        return None


def set_op_secret(op_path: str, value: str) -> bool:
    """
    Stores a secret in 1Password using assignment syntax.
    This updates ONLY the specific field, preserving all other fields in the item.

    Uses the full path from config: op://Vault/Item/Section/Field
    """
    from rich.console import Console

    console = Console()

    console.print(f"[dim]set_op_secret: starting with path={op_path[:50]}...[/dim]")

    if not op_path or not op_path.startswith("op://"):
        logger.error(f"Invalid 1Password path: {op_path}")
        return False

    try:
        parts = op_path.replace("op://", "").split("/")

        if len(parts) == 4:
            vault, item, section, field = parts[0], parts[1], parts[2], parts[3]
            field_ref = f"{section}.{field}"
        elif len(parts) == 3:
            vault, item, field = parts[0], parts[1], parts[2]
            field_ref = field
        else:
            logger.error(f"Invalid path format: {op_path}. Expected 3 or 4 parts")
            return False

        console.print(
            f"[dim]set_op_secret: parsed vault={vault}, item={item}, field_ref={field_ref}[/dim]"
        )

        # Use the EXACT same pattern as get_op_secret - inline export + --account
        bash_cmd = f'export OP_ACCOUNT=my.1password.com; "/mnt/c/Program Files/1Password CLI/op.exe" item edit "{item}" --vault "{vault}" "{field_ref}={value}" --account "my.1password.com"'

        console.print(
            "[dim]set_op_secret: executing bash command (30s timeout)…[/dim]"
        )

        try:
            result = subprocess.run(
                ["bash", "-c", bash_cmd],
                capture_output=True,
                text=True,
                env=os.environ.copy(),
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            console.print(
                "[yellow]set_op_secret: timed out after 30s waiting for "
                "1Password CLI (often no Windows Hello prompt from WSL).[/yellow]"
            )
            logger.warning("1Password set_op_secret timed out for %s", op_path)
            return False

        console.print(
            f"[dim]set_op_secret: result.returncode={result.returncode}[/dim]"
        )

        if result.returncode != 0:
            err = (result.stderr or result.stdout or "")[:300]
            console.print(f"[red]set_op_secret: stderr={err}[/red]")
            logger.error(f"Failed to set 1Password secret: {err}")
            return False

        console.print("[dim]set_op_secret: success![/dim]")
        return True
    except subprocess.CalledProcessError as e:
        console.print(f"[red]set_op_secret: CalledProcessError={e}[/red]")
        logger.error(f"Failed to set 1Password secret at '{op_path}': {e.stderr}")
        return False
    except FileNotFoundError:
        console.print("[red]set_op_secret: FileNotFoundError[/red]")
        logger.error("The 'op' CLI was not found in the system path.")
        return False
    except Exception as e:
        console.print(f"[red]set_op_secret: Exception={e}[/red]")
        logger.error(f"Unexpected error setting 1Password secret: {e}")
        return False
