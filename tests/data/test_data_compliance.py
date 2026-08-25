"""Frictionless-schema compliance for gm-list's compacted.usv output.

Self-contained: builds synthetic raw gm-list result files under tmp_path,
runs the real production compaction pipeline (run_compilation +
run_compaction from cocli.core.auditors.gm_list_auditor) to produce
compacted.usv, then validates it via cocli.core.frictionless_validation.
validate_usv_file() - the project's own datapackage.json validator (also
used by validate_stage_outputs()) - against a schema matching the exact
column contract that pipeline enforces (gm_list_auditor.py's run_compaction
validity filter).

Previously hardcoded to an absolute personal path
(/home/mstouffer/.local/share/cocli_data_dev/...) that only ever existed
on one machine's old data layout - silently skipped everywhere else,
including CI - and called frictionless.validate() directly with a full
datapackage.json as schema=, which frictionless.validate() doesn't accept
(it wants a bare Schema descriptor, not a package wrapper) - so even with
data present, the old test would never have actually passed.
"""

import json
from pathlib import Path

from cocli.core.auditors.gm_list_auditor import run_compaction, run_compilation
from cocli.core.constants import UNIT_SEP
from cocli.core.frictionless_validation import validate_usv_file
from cocli.utils.usv_utils import USVWriter

# Matches run_compaction's raw_data columns exactly (gm_list_auditor.py).
_COLUMNS = [
    "place_id", "company_slug", "name", "category", "phone", "domain",
    "reviews_count", "average_rating", "street_address", "gmb_url",
]

_VALID_ROW = [
    "ChIJN1t_tDeuEmsRUsoyG83frY4",  # place_id: 27 chars, in [26, 29]
    "acme-flooring",  # company_slug: in [3, 100]
    "Acme Flooring",  # name: in [1, 100]
    "Flooring contractor",  # category: unconstrained
    "5551234567",  # phone: 10 digits, in [10, 15]
    "acmeflooring.com",  # domain: in [3, 100]
    "42",  # reviews_count: castable int >= 0
    "4.5",  # average_rating: castable float in [0.0, 5.0]
    "123 Main St, Springfield",  # street_address: in [5, 100]
    "https://maps.google.com/?cid=12345",  # gmb_url: len >= 20
]


def _write_datapackage(results_dir: Path) -> Path:
    fields = [
        {"name": c, "type": "integer" if c == "reviews_count" else
         "number" if c == "average_rating" else "string"}
        for c in _COLUMNS
    ]
    datapackage_path = results_dir / "datapackage.json"
    datapackage_path.write_text(json.dumps({
        "profile": "tabular-data-package",
        "name": "gm_list_compacted",
        "resources": [{
            "name": "compacted",
            "path": "compacted.usv",
            "format": "usv",
            "dialect": {"delimiter": UNIT_SEP, "header": False},
            "schema": {"fields": fields},
        }],
    }))
    return datapackage_path


def test_data_compliance(tmp_path: Path) -> None:
    """compacted.usv (real compaction pipeline output) conforms to its schema."""
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    with open(results_dir / "raw.usv", "w", encoding="utf-8") as f:
        USVWriter(f).writerow(_VALID_ROW)

    run_compilation(campaign="test", queue="gm-list", results_dir=results_dir)
    compacted_path = run_compaction(results_dir)
    assert compacted_path.exists()

    schema_path = _write_datapackage(results_dir)

    is_valid, record_count, errors = validate_usv_file(compacted_path, schema_path)
    assert is_valid, f"Data compliance failed: {errors}"
    assert record_count == 1
