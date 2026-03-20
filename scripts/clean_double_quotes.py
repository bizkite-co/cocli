#!/usr/bin/env python3
"""
Clean double-quote abuse in prospects.checkpoint.usv.

This script collapses consecutive double quotes to single quotes and
strips remaining leading/trailing quotes from text fields.

Usage:
    python scripts/clean_double_quotes.py --campaign CAMPAIGN
"""

from __future__ import annotations

import argparse

import duckdb

from cocli.core.paths import paths
from cocli.utils.duckdb_utils import load_usv_to_duckdb
from cocli.utils.usv_utils import USVWriter


def collapse_quotes(s: str | None) -> str | None:
    """Collapse consecutive double quotes and strip leading/trailing quotes."""
    if s is None:
        return None
    while '""' in s:
        s = s.replace('""', '"')
    return s.strip('"')


def clean_checkpoint(campaign_name: str) -> None:
    """Clean double-quote abuse from prospects checkpoint."""
    con = duckdb.connect(database=":memory:")
    usv_path = paths.campaign(campaign_name).index("google_maps_prospects").checkpoint
    dp_path = usv_path.parent / "datapackage.json"

    print(f"Loading {usv_path}...")
    load_usv_to_duckdb(con, "prospects", usv_path, datapackage_path=dp_path)

    text_cols = [
        "name",
        "full_address",
        "street_address",
        "website",
        "city",
        "domain",
        "first_category",
        "second_category",
        "quotes",
        "reviews",
    ]

    total_cleaned = 0
    for col in text_cols:
        rows: list[tuple[str, str]] = con.execute(
            f"SELECT place_id, {col} FROM prospects WHERE {col} LIKE '%\"%'"
        ).fetchall()
        for place_id, value in rows:
            cleaned = collapse_quotes(value)
            if cleaned != value:
                con.execute(
                    f"UPDATE prospects SET {col} = ? WHERE place_id = ?",
                    [cleaned, place_id],
                )
                total_cleaned += 1

    print(f"Cleaned {total_cleaned} fields.")

    columns = [r[1] for r in con.execute("PRAGMA table_info('prospects')").fetchall()]
    output_usv = usv_path.parent / "prospects.checkpoint.cleaned.usv"

    print(f"Writing to {output_usv}...")
    with open(output_usv, "w", encoding="utf-8") as f:
        writer = USVWriter(f)
        data = con.execute(
            "SELECT " + ", ".join([f'"{c}"' for c in columns]) + " FROM prospects"
        ).fetchall()
        for row in data:
            trimmed_row = [
                str(cell).strip() if cell is not None else "" for cell in row
            ]
            writer.writerow(trimmed_row)

    backup = usv_path.parent / "prospects.checkpoint.usv.backup"
    backup.write_bytes(usv_path.read_bytes())
    output_usv.rename(usv_path)
    print(f"Swapped. Backup at {backup}")
    print("Done!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Clean double-quote abuse in prospects checkpoint."
    )
    parser.add_argument("--campaign", "-c", default="roadmap", help="Campaign name")
    args = parser.parse_args()

    clean_checkpoint(args.campaign)
