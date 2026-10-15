"""Stop a frozen `cocli tui` from another shell."""

from __future__ import annotations

import signal
from typing import Any

from cocli.commands.tui import (
    is_cocli_tui_argv,
    list_cocli_tui_processes,
    terminate_cocli_tuis,
)


class _Proc:
    def __init__(
        self,
        pid: int,
        argv: list[str],
        children: list[_Proc] | None = None,
        die_on_term: bool = True,
    ) -> None:
        self.pid = pid
        self._argv = argv
        self._children = children or []
        self.die_on_term = die_on_term
        self.alive = True
        self.signals: list[int] = []

    def cmdline(self) -> list[str]:
        return list(self._argv)

    def children(self, recursive: bool = False) -> list[_Proc]:
        return list(self._children)

    def is_running(self) -> bool:
        return self.alive

    def send_signal(self, sig: int) -> None:
        self.signals.append(sig)
        if sig == signal.SIGTERM and self.die_on_term:
            self.alive = False
        if sig == signal.SIGKILL:
            self.alive = False


def test_is_cocli_tui_argv_matches_the_session_and_skips_kill() -> None:
    assert is_cocli_tui_argv(
        ["/home/x/.venv/bin/python", "/home/x/.venv/bin/cocli", "tui"]
    )
    assert is_cocli_tui_argv(["cocli", "--campaign", "roadmap", "tui"])
    assert is_cocli_tui_argv(["cocli", "-c", "roadmap", "tui", "--dump-tree", "out.txt"])
    assert not is_cocli_tui_argv(["cocli", "tui", "kill"])
    assert not is_cocli_tui_argv(["cocli", "--campaign", "roadmap", "tui", "kill"])
    assert not is_cocli_tui_argv(["cocli", "companies", "list"])
    assert not is_cocli_tui_argv(["rsync", "cocli", "tui"])


def test_list_cocli_tui_processes_skips_this_process(monkeypatch: Any) -> None:
    me = _Proc(10, ["cocli", "tui"])
    other = _Proc(11, ["cocli", "tui"])
    killer = _Proc(12, ["cocli", "tui", "kill"])
    monkeypatch.setattr("os.getpid", lambda: 10)
    found = list_cocli_tui_processes([me, other, killer])
    assert [proc.pid for proc in found] == [11]


def test_terminate_cocli_tuis_signals_children_and_kills_survivors() -> None:
    child = _Proc(21, ["rsync"], die_on_term=False)
    tui = _Proc(20, ["cocli", "tui"], children=[child])
    pids = terminate_cocli_tuis([tui], wait_seconds=0)
    assert pids == [20]
    assert child.signals == [signal.SIGTERM, signal.SIGKILL]
    assert tui.signals == [signal.SIGTERM]
    assert not child.alive


def test_terminate_cocli_tuis_reports_nothing_when_none_match(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "cocli.commands.tui.list_cocli_tui_processes",
        lambda process_iter=None: [],
    )
    assert terminate_cocli_tuis() == []
