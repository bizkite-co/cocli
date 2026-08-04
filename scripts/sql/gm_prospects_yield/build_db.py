"""Materializes a campaign's prospects checkpoint + gm-list results into a
persisted DuckDB file, so the .sql files in queries/ can be run independently
(`duckdb <db_path> < queries/some_query.sql`) instead of being re-typed as
one-off Python heredocs during an investigation.

Read-only against source data: only ever writes the diagnostic .duckdb file
itself, never the checkpoint or WAL. Safe to re-run any time to refresh.
"""

import json
from pathlib import Path

import duckdb
import typer

from cocli.core.paths import paths
from cocli.core.prospects_csv_manager import ProspectsIndexManager
from cocli.core.email_index_manager import EmailIndexManager
from cocli.core.transformers.gm_list_to_checkpoint import _load_gm_list_results_auto
from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect

app = typer.Typer()


def _db_path(campaign_name: str) -> Path:
    diagnostics_dir = paths.campaign(campaign_name).path / "_diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    return diagnostics_dir / "gm_prospects_yield.duckdb"


@app.command()
def main(campaign_name: str = typer.Argument(..., help="Campaign to build the diagnostic DB for.")) -> None:
    db_path = _db_path(campaign_name)
    if db_path.exists():
        db_path.unlink()

    con = duckdb.connect(str(db_path))

    # --- prospects (checkpoint) ---
    model_fields = GoogleMapsProspect.model_fields
    columns = {}
    for name, f in model_fields.items():
        field_type = "VARCHAR"
        type_str = str(f.annotation)
        if "int" in type_str:
            field_type = "INTEGER"
        elif "float" in type_str:
            field_type = "DOUBLE"
        columns[name] = field_type

    prospect_manager = ProspectsIndexManager(campaign_name)
    checkpoint_path = prospect_manager.checkpoint_path
    if not checkpoint_path.exists():
        typer.echo(f"No checkpoint at {checkpoint_path}, skipping prospects table")
    else:
        con.execute(f"""
            CREATE TABLE prospects AS SELECT * FROM read_csv('{checkpoint_path}',
                delim='\x1f',
                header=False,
                columns={json.dumps(columns)},
                auto_detect=False,
                ignore_errors=True,
                quote=''
            )
        """)
        con.execute("ALTER TABLE prospects ADD COLUMN norm_domain VARCHAR")
        con.execute(r"""
            UPDATE prospects SET norm_domain = regexp_replace(regexp_replace(lower(domain), '^https?://(www\.)?', ''), '/$', '')
        """)
        n = con.execute("SELECT COUNT(*) FROM prospects").fetchone()[0]
        typer.echo(f"prospects: {n} rows")

    # --- gm_results (gm-list completed results) ---
    results_dir = paths.campaign(campaign_name).queue("gm-list").completed / "results"
    if not results_dir.exists():
        typer.echo(f"No gm-list results dir at {results_dir}, skipping gm_results table")
    else:
        _load_gm_list_results_auto(con, results_dir)
        n = con.execute("SELECT COUNT(*) FROM gm_results").fetchone()[0]
        typer.echo(f"gm_results: {n} rows")

    # --- emails (sharded email index) ---
    email_manager = EmailIndexManager(campaign_name)
    shard_files = list(email_manager.shards_dir.glob("*.usv"))
    if shard_files:
        email_shard_glob = str(email_manager.shards_dir / "*.usv")
        con.execute(f"""
            CREATE TABLE emails AS SELECT * FROM read_csv('{email_shard_glob}',
                delim='\x1f',
                header=False,
                columns={{
                    'email': 'VARCHAR',
                    'domain': 'VARCHAR',
                    'company_slug': 'VARCHAR',
                    'source': 'VARCHAR',
                    'found_at': 'VARCHAR',
                    'first_seen': 'VARCHAR',
                    'last_seen': 'VARCHAR',
                    'verification_status': 'VARCHAR',
                    'tags': 'VARCHAR'
                }}
            )
        """)
        con.execute(r"""
            DELETE FROM emails
            WHERE NOT regexp_matches(email, '^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$')
               OR regexp_matches(lower(email), '\.(png|jpe?g|gif|webp|bmp|svg|ico|tiff?)$')
        """)
        con.execute("ALTER TABLE emails ADD COLUMN norm_domain VARCHAR")
        con.execute(r"""
            UPDATE emails SET norm_domain = regexp_replace(regexp_replace(lower(domain), '^https?://(www\.)?', ''), '/$', '')
        """)
        n = con.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
        typer.echo(f"emails: {n} rows (shape-valid)")
    else:
        con.execute("CREATE TABLE emails (email VARCHAR, domain VARCHAR, company_slug VARCHAR, tags VARCHAR, last_seen VARCHAR, norm_domain VARCHAR)")
        typer.echo("emails: 0 shard files found")

    con.close()
    typer.echo(f"\nDB ready: {db_path}")
    typer.echo(f"Run a query with: duckdb {db_path} < queries/<name>.sql")


if __name__ == "__main__":
    app()
