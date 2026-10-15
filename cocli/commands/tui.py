from __future__ import annotations

import logging
import os
import signal
import time
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

import typer

from ..core.logging_config import setup_file_logging

logger = logging.getLogger(__name__)

app = typer.Typer()

_COCLI_NAMES = {"cocli", "cocli.exe"}
_OPTIONS_WITH_VALUES = {"-c", "--campaign"}

@app.callback(invoke_without_command=True)
def run_tui_app(
    ctx: typer.Context,
    dump_tree: Optional[Path] = typer.Option(
        None, "--dump-tree", help="Dump the TUI widget tree to a file and exit."
    ),
) -> None:
    """
    Launches the Textual TUI for cocli.
    """
    if ctx.invoked_subcommand is not None:
        return

    if dump_tree:
        import asyncio
        from ..tui.utils import dump_tree as dump_tree_util
        from ..application.services import ServiceContainer
        from ..core.paths import paths

        async def _dump() -> None:
            from ..tui.app import CocliApp
            services = ServiceContainer()
            tui_app = CocliApp(services=services, auto_show=False)
            
            output_path = Path(dump_tree)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, "w", encoding="utf-8") as f:
                async with tui_app.run_test() as pilot:
                    f.write("=== CocliApp Top Level ===\n")
                    dump_tree_util(tui_app, file=f)
                    
                    f.write("\n=== ApplicationView ===\n")
                    await tui_app.action_show_application()
                    await pilot.pause()
                    app_content = tui_app.query_one("#app_content")
                    dump_tree_util(app_content, file=f)

                    f.write("\n=== CompanySearchView ===\n")
                    await tui_app.action_show_companies()
                    await pilot.pause()
                    dump_tree_util(app_content, file=f)

                    f.write("\n=== PersonList ===\n")
                    await tui_app.action_show_people()
                    await pilot.pause()
                    dump_tree_util(app_content, file=f)

                    f.write("\n=== CompanyDetail ===\n")
                    # Dynamically find a sample company to show the detail view structure
                    sample_slug = None
                    companies_dir = paths.root / "companies"
                    if companies_dir.exists():
                        for item in companies_dir.iterdir():
                            if item.is_dir() and (item / "_index.md").exists():
                                sample_slug = item.name
                                break
                    
                    if sample_slug:
                        company_data = services.get_company_details(sample_slug)
                        if company_data:
                            from ..tui.widgets.company_detail import CompanyDetail
                            await app_content.remove_children()
                            await app_content.mount(CompanyDetail(company_data))
                            await pilot.pause()
                            dump_tree_util(app_content, file=f)
            
            print(f"TUI tree dumped to {output_path}")

        asyncio.run(_dump())
        raise typer.Exit()

    setup_file_logging("tui", file_level=logging.DEBUG, disable_console=True)
    from ..tui.app import CocliApp
    tui_app = CocliApp()
    tui_app.run()


def is_cocli_tui_argv(argv: Sequence[str]) -> bool:
    """True when argv is a `cocli tui` session, including `cocli --campaign X tui`.

    `cocli tui kill` is the stopper, so it does not match. The `cocli` token
    has to be the program (or the script after a python launcher). A later
    argument that happens to be named cocli is not a session.
    """
    if not argv:
        return False
    indexes = [0]
    if Path(argv[0]).name.startswith("python") and len(argv) > 1:
        indexes.append(1)
    for index in indexes:
        if Path(argv[index]).name not in _COCLI_NAMES:
            continue
        rest = list(argv[index + 1 :])
        position = 0
        while position < len(rest):
            token = rest[position]
            if token == "--":
                position += 1
                break
            if token.startswith("-"):
                if token in _OPTIONS_WITH_VALUES and "=" not in token:
                    position += 2
                else:
                    position += 1
                continue
            break
        if position >= len(rest) or rest[position] != "tui":
            continue
        following = rest[position + 1] if position + 1 < len(rest) else None
        return following != "kill"
    return False


def list_cocli_tui_processes(process_iter: Iterable[Any] | None = None) -> list[Any]:
    """Live `cocli tui` processes on this machine, excluding this process."""
    if process_iter is None:
        import psutil

        process_iter = psutil.process_iter()
    me = os.getpid()
    found: list[Any] = []
    for proc in process_iter:
        if getattr(proc, "pid", None) == me:
            continue
        try:
            argv = proc.cmdline()
        except Exception:
            continue
        if is_cocli_tui_argv(argv):
            found.append(proc)
    return found


def _still_running(proc: Any) -> bool:
    try:
        return bool(proc.is_running())
    except Exception:
        return False


def _signal(proc: Any, sig: int) -> None:
    try:
        proc.send_signal(sig)
    except Exception as exc:
        logger.debug("Could not signal pid %s with %s: %s", getattr(proc, "pid", "?"), sig, exc)


def terminate_cocli_tuis(
    procs: Sequence[Any] | None = None,
    wait_seconds: float = 2.0,
) -> list[int]:
    """SIGTERM every local cocli TUI and its children, then SIGKILL any that remain.

    Returns the TUI pids that were targeted.
    """
    targets = list(procs) if procs is not None else list_cocli_tui_processes()
    me = os.getpid()
    tuis: list[Any] = []
    victims: list[Any] = []
    seen: set[int] = set()
    for proc in targets:
        pid = getattr(proc, "pid", None)
        if pid is None or pid == me or pid in seen:
            continue
        seen.add(pid)
        tuis.append(proc)
        victims.append(proc)
        try:
            children = proc.children(recursive=True)
        except Exception:
            children = []
        for child in children:
            child_pid = getattr(child, "pid", None)
            if child_pid is None or child_pid == me or child_pid in seen:
                continue
            seen.add(child_pid)
            victims.append(child)

    if not tuis:
        return []

    for proc in victims:
        _signal(proc, signal.SIGTERM)

    deadline = time.monotonic() + wait_seconds
    while any(_still_running(proc) for proc in victims):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(0.05, remaining))

    for proc in victims:
        if _still_running(proc):
            logger.info("PID %s ignored SIGTERM; sending SIGKILL", proc.pid)
            _signal(proc, signal.SIGKILL)

    return [proc.pid for proc in tuis]


@app.command("kill")
def kill_tui() -> None:
    """Stop every cocli TUI on this machine."""
    setup_file_logging("tui-kill", file_level=logging.INFO)
    pids = terminate_cocli_tuis()
    if not pids:
        logger.info("No cocli TUI processes are running.")
        return
    logger.info(
        "Stopped cocli TUI process%s: %s",
        "" if len(pids) == 1 else "es",
        ", ".join(str(pid) for pid in pids),
    )
