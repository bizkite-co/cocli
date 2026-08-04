import os
import subprocess
import logging
import json
from typing import Optional, cast, Any, Dict

logger = logging.getLogger(__name__)


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

    # 2. Fallback to 'op' CLI
    try:
        result = subprocess.run(
            [
                "bash",
                "-c",
                f'export OP_ACCOUNT=my.1password.com; "/mnt/c/Program Files/1Password CLI/op.exe" read "{op_path}" --account "my.1password.com"',
            ],
            capture_output=True,
            text=True,
            check=True,
            env=os.environ.copy(),
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.strip()
        if "authorization timeout" in err_msg or "not signed in" in err_msg:
            logger.error("1Password session expired. Please run: eval $(op signin)")
        else:
            logger.error(
                f"Failed to read from 1Password path '{op_path}' via CLI: {e.stderr}"
            )
        return None
    except FileNotFoundError:
        logger.error("The 'op' CLI was not found in the system path.")
        return None
    except Exception as e:
        logger.error(f"Unexpected error retrieving 1Password secret via CLI: {e}")
        return None


def get_op_item(item_id: str, vault: Optional[str] = None) -> Optional[Dict[str, Any]]:
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
        return cast(Dict[str, Any], json.loads(result.stdout))
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
