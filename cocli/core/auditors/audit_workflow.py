from transitions import Machine
from typing import Any
from rich.console import Console
from cocli.core.paths import paths
from .gm_list_auditor import run_compilation, run_compaction, run_reporting

console = Console()


class DataAuditWorkflow:
    states = ["idle", "compiling", "compacting", "reporting", "completed", "failed"]

    # Transition methods added by transitions
    start: Any
    finish_compilation: Any
    finish_compacting: Any
    finish_reporting: Any
    fail: Any

    def __init__(self, campaign: str, queue: str):
        self.campaign = campaign
        self.queue = queue
        self.state = "idle"

        self.results_dir = paths.campaign(campaign).queue(queue).completed / "results"

        transitions = [
            {
                "trigger": "start",
                "source": "idle",
                "dest": "compiling",
                "after": "run_compilation",
            },
            {
                "trigger": "finish_compilation",
                "source": "compiling",
                "dest": "compacting",
                "after": "run_compaction",
            },
            {
                "trigger": "finish_compacting",
                "source": "compacting",
                "dest": "reporting",
                "after": "run_reporting",
            },
            {"trigger": "finish_reporting", "source": "reporting", "dest": "completed"},
            {
                "trigger": "fail",
                "source": "*",
                "dest": "failed",
                "after": "log_failure",
            },
        ]

        self.machine = Machine(
            model=self, states=self.states, transitions=transitions, initial=self.state
        )

    def run_compilation(self) -> None:
        try:
            run_compilation(self.campaign, self.queue, self.results_dir)
            self.finish_compilation()
        except Exception as e:
            console.print(f"[bold red]Compilation error: {e}[/bold red]")
            self.fail()

    def run_compaction(self) -> None:
        try:
            run_compaction(self.results_dir)
            self.finish_compacting()
        except Exception as e:
            console.print(f"[bold red]Compaction error: {e}[/bold red]")
            self.fail()

    def run_reporting(self) -> None:
        try:
            run_reporting(self.results_dir)
            self.finish_reporting()
        except Exception as e:
            console.print(f"[bold red]Reporting error: {e}[/bold red]")
            self.fail()

    def log_failure(self) -> None:
        console.print(f"[bold red]Audit failed in state: {self.state}[/bold red]")
