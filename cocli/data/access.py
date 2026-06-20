# -*- coding: utf-8 -*-
"""Data‑access façade for USV/JSON queues.

All code that needs to read campaign queue data should import the helper(s)
from ``cocli.data.access``.  This guarantees that the Frictionless‑Data
``datapackage.json`` is discovered, a DuckDB schema is built, and the data is
loaded in a single, validated step.
"""

import duckdb
from pathlib import Path
import logging

from cocli.utils import duckdb_utils
from cocli.core.paths import paths

logger = logging.getLogger(__name__)


def _connect_memory() -> duckdb.DuckDBPyConnection:
    """Return a fresh in‑memory DuckDB connection.

    Using an in‑memory database isolates each audit run and avoids any
    on‑disk side‑effects.
    """
    return duckdb.connect(database=":memory:")


def load_queue_into_table(
    campaign: str, queue_name: str, table_name: str
) -> duckdb.DuckDBPyConnection:
    """Load *all* files for ``<campaign>/queues/<queue_name>`` into ``table_name``.

    The function discovers the appropriate ``datapackage.json`` (using
    :func:`cocli.utils.duckdb_utils.find_datapackage`), then streams every
    USV/JSON resource described by that datapackage into a DuckDB table via
    :func:`cocli.utils.duckdb_utils.load_from_datapackage`.

    Returns the live DuckDB connection so callers can execute arbitrary SQL.
    The caller is responsible for ``con.close()`` when finished.
    """
    queue_dir = paths.campaign(campaign).queue(queue_name)
    # Look for datapackage.json in the queue directory directly
    dp_path = queue_dir / "datapackage.json"
    if not dp_path.exists():
        raise FileNotFoundError(
            f"No datapackage.json found for queue {queue_name!r} in campaign {campaign!r}"
        )

    con = _connect_memory()
    duckdb_utils.load_from_datapackage(con, table_name, dp_path)
    return con
