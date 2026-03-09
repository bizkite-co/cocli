import logging
from typing import Optional
from pathlib import Path
import typer
from ..tui.app import CocliApp
from ..core.logging_config import setup_file_logging

logger = logging.getLogger(__name__)

app = typer.Typer()

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
    tui_app = CocliApp()
    tui_app.run()
