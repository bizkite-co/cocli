import csv
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import duckdb
from pydantic import BaseModel, Field

from ..core.config import get_campaign, get_cocli_base_dir, load_campaign_config
from ..core.paths import paths
from ..core.smart_sync import run_smart_sync

logger = logging.getLogger(__name__)

LogCallback = Callable[[str], None]


def _emit(log_callback: Optional[LogCallback], message: str) -> None:
    logger.info(message)
    if log_callback is not None:
        log_callback(message)


class DatapackageSummary(BaseModel):
    """A discovered frictionless datapackage under the data root."""

    path: Path
    relative_path: str
    resource_names: List[str] = Field(default_factory=list)


class SchemaField(BaseModel):
    index: int
    name: str
    type: str = "string"


class SchemaDescribeResult(BaseModel):
    """Schema description for one or more resources (datapackage or USV)."""

    source_label: str
    datapackage_path: Optional[Path] = None
    resources: List[Dict[str, Any]] = Field(default_factory=list)


class SampleResult(BaseModel):
    """First N rows from a USV / datapackage load."""

    title: str
    columns: List[str] = Field(default_factory=list)
    rows: List[List[Any]] = Field(default_factory=list)


class MetricsResult(BaseModel):
    """Data-quality metrics for a USV dataset."""

    source_name: str
    metrics: Dict[str, Any] = Field(default_factory=dict)
    used_fallback: bool = False
    output_path: Optional[Path] = None
    message: str = ""


class SearchResult(BaseModel):
    """SQL search results over a USV file."""

    query: str
    columns: List[str] = Field(default_factory=list)
    rows: List[List[Any]] = Field(default_factory=list)
    row_count: int = 0
    schema_warning: Optional[str] = None
    valid_columns_preview: List[str] = Field(default_factory=list)


class InspectRowResult(BaseModel):
    """Single-row field inspection against a datapackage schema."""

    file_name: str
    row_number: int
    fields: List[Tuple[int, str, str]] = Field(default_factory=list)


class QueueCompactResult(BaseModel):
    """Result of compacting a queue's completed results."""

    campaign_name: str
    queue_name: str
    success: bool = True
    message: str = ""
    records_merged: int = 0


class UnknownColumnError(ValueError):
    """Raised when a search query references columns not in the datapackage schema."""

    def __init__(self, invalid_cols: Any, valid_preview: List[str]):
        self.invalid_cols = invalid_cols
        self.valid_preview = valid_preview
        super().__init__(f"Unknown column(s) in query: {invalid_cols}")


class DataSyncService:
    def __init__(self, campaign_name: Optional[str] = None):
        self.campaign_name = campaign_name or get_campaign() or "default"

    def sync_prospects(self, force: bool = False, full: bool = False) -> Dict[str, Any]:
        return self._sync_target("prospects", force, full)

    def sync_companies(self, force: bool = False, full: bool = False) -> Dict[str, Any]:
        return self._sync_target("companies", force, full)

    def sync_emails(self, force: bool = False, full: bool = False) -> Dict[str, Any]:
        return self._sync_target("emails", force, full)

    def sync_indexes(self, force: bool = False, full: bool = False) -> Dict[str, Any]:
        """Syncs all critical indexes (Prospects, Emails, Scraped Areas)."""
        results = {}
        results["prospects"] = self.sync_prospects(force, full)
        results["emails"] = self.sync_emails(force, full)
        # Add scraped-areas if needed
        return results

    def sync_queues(self, queue_name: Optional[str] = None, force: bool = False, full: bool = False) -> Dict[str, Any]:
        """Syncs one or all queues from S3."""
        config = load_campaign_config(self.campaign_name)
        aws_config = config.get("aws", {})
        bucket_name = aws_config.get("data_bucket_name") or f"cocli-data-{self.campaign_name}"
        
        target_queues = [queue_name] if queue_name else ["gm-list", "gm-details", "enrichment"]
        
        for q in target_queues:
            try:
                local_base_completed = paths.queue(self.campaign_name, q) / "completed"
                local_base_pending = paths.queue(self.campaign_name, q) / "pending"
                
                # Pending
                run_smart_sync(f"{q}-pending", bucket_name, f"campaigns/{self.campaign_name}/queues/{q}/pending/", 
                                local_base_pending, self.campaign_name, aws_config, force=force, full=full,
                                completed_dir=local_base_completed)
                # Completed
                run_smart_sync(f"{q}-completed", bucket_name, f"campaigns/{self.campaign_name}/queues/{q}/completed/", 
                                local_base_completed, self.campaign_name, aws_config, force=force, full=full)
            except Exception as e:
                logger.error(f"Failed to sync queue {q}: {e}")
                return {"status": "error", "message": str(e), "queue": q}
        
        return {"status": "success", "queues": target_queues}

    def sync_all(self, force: bool = False, full: bool = False) -> Dict[str, Any]:
        results = {}
        results["prospects"] = self.sync_prospects(force, full)
        results["companies"] = self.sync_companies(force, full)
        results["emails"] = self.sync_emails(force, full)
        results["queues"] = self.sync_queues(force=force, full=full)
        return results

    def _sync_target(self, target: str, force: bool = False, full: bool = False) -> Dict[str, Any]:
        config = load_campaign_config(self.campaign_name)
        aws_config = config.get("aws", {})
        bucket_name = aws_config.get("data_bucket_name") or f"cocli-data-{self.campaign_name}"
        data_dir = get_cocli_base_dir()
        
        prefix = ""
        local_base = Path(".")
        
        if target == "prospects":
            prefix = f"campaigns/{self.campaign_name}/indexes/google_maps_prospects/"
            local_base = data_dir / "campaigns" / self.campaign_name / "indexes" / "google_maps_prospects"
        elif target == "companies":
            prefix = "companies/"
            local_base = data_dir / "companies"
        elif target == "emails":
            prefix = f"campaigns/{self.campaign_name}/indexes/emails/"
            local_base = data_dir / "campaigns" / self.campaign_name / "indexes" / "emails"
            
        try:
            run_smart_sync(target, bucket_name, prefix, local_base, self.campaign_name, aws_config, force=force, full=full)
            return {"status": "success", "target": target}
        except Exception as e:
            logger.error(f"Sync failed for {target}: {e}")
            return {"status": "error", "message": str(e), "target": target}

    def compact_index(self) -> Dict[str, Any]:
        """Runs the email index compaction (Hot Inbox -> Shards)."""
        try:
            from ..core.email_index_manager import EmailIndexManager
            manager = EmailIndexManager(self.campaign_name)
            manager.compact()
            return {"status": "success", "message": "Email index compacted (Hot Inbox -> Shards)"}
        except Exception as e:
            logger.error(f"Email compaction failed: {e}")
            return {"status": "error", "message": str(e)}

    def push_queue(self, queue_name: str = "enrichment") -> Dict[str, Any]:
        """
        Pushes local queue items to S3.
        Corresponds to 'make push-queue' / 'scripts/push_queue.py'.
        """
        import boto3
        from ..core.paths import paths
        
        config = load_campaign_config(self.campaign_name)
        aws_config = config.get("aws", {})
        bucket_name = aws_config.get("data_bucket_name") or f"cocli-data-{self.campaign_name}"
        profile_name = aws_config.get("profile") or aws_config.get("aws_profile")

        try:
            session = boto3.Session(profile_name=profile_name)
            s3 = session.client("s3")
            
            local_queue_dir = paths.queue(self.campaign_name, queue_name) / "pending"
            if not local_queue_dir.exists():
                return {"status": "error", "message": f"Queue directory not found: {local_queue_dir}"}
                
            s3_prefix = f"campaigns/{self.campaign_name}/queues/{queue_name}/pending/"
            
            uploaded_count = 0
            for root, _, files in os.walk(local_queue_dir):
                for file in files:
                    local_path = Path(root) / file
                    rel_path = local_path.relative_to(local_queue_dir)
                    s3_key = f"{s3_prefix}{rel_path}"
                    
                    # Simple check to avoid redundant uploads
                    should_upload = True
                    try:
                        head = s3.head_object(Bucket=bucket_name, Key=s3_key)
                        if head['ContentLength'] == local_path.stat().st_size:
                            should_upload = False
                    except Exception:
                        pass
                        
                    if should_upload:
                        s3.upload_file(str(local_path), bucket_name, s3_key)
                        uploaded_count += 1
            
            return {"status": "success", "uploaded_count": uploaded_count}
        except Exception as e:
            logger.error(f"Push queue failed for {queue_name}: {e}")
            return {"status": "error", "message": str(e)}

    # ------------------------------------------------------------------
    # Frictionless data inspection (from commands/data.py)
    # Intermediate artifacts: datapackages, local USV stores
    # ------------------------------------------------------------------

    @staticmethod
    def resolve_usv_path(
        file_path: Path, resource_name: Optional[str] = None
    ) -> Path:
        """Resolve a datapackage/directory path to a concrete USV file path."""
        if file_path.is_dir() and (file_path / "datapackage.json").exists():
            file_path = file_path / "datapackage.json"

        if file_path.name == "datapackage.json":
            with open(file_path, "r") as f:
                pkg = json.load(f)

            resource = None
            if resource_name:
                for res in pkg.get("resources", []):
                    if res.get("name") == resource_name:
                        resource = res
                        break
            elif pkg.get("resources"):
                resource = pkg["resources"][0]

            if not resource:
                raise ValueError("Could not identify resource in datapackage.")

            res_path_pattern = resource.get("path", "")
            matches = list(file_path.parent.glob(res_path_pattern))
            if not matches:
                raise ValueError(f"No files found matching {res_path_pattern}")

            return matches[0]

        return file_path

    def list_datapackages(self) -> List[DatapackageSummary]:
        """List all datapackage.json files under the data root."""
        data_dir = paths.root
        results: List[DatapackageSummary] = []
        for dp in sorted(data_dir.glob("**/datapackage.json")):
            try:
                with open(dp, "r") as f:
                    pkg = json.load(f)
                resource_names = [
                    res.get("name", "unknown") for res in pkg.get("resources", [])
                ]
                results.append(
                    DatapackageSummary(
                        path=dp,
                        relative_path=str(dp.relative_to(data_dir)),
                        resource_names=resource_names,
                    )
                )
            except Exception:
                continue
        return results

    def describe_schema(self, file_path: Path) -> SchemaDescribeResult:
        """
        Return schema field definitions for a USV file or datapackage.

        Raises:
            FileNotFoundError, ValueError
        """
        from cocli.utils.duckdb_utils import find_datapackage, match_resource_path

        if file_path.is_dir() and (file_path / "datapackage.json").exists():
            file_path = file_path / "datapackage.json"

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if file_path.name == "datapackage.json":
            with open(file_path, "r") as f:
                pkg = json.load(f)

            resources = pkg.get("resources", [])
            if not resources:
                raise ValueError("No resources in datapackage")

            resource_payloads: List[Dict[str, Any]] = []
            for res in resources:
                fields = res.get("schema", {}).get("fields", [])
                resource_payloads.append(
                    {
                        "name": res.get("name", "unknown"),
                        "path": res.get("path"),
                        "fields": [
                            SchemaField(
                                index=i,
                                name=field["name"],
                                type=field.get("type", "string"),
                            ).model_dump()
                            for i, field in enumerate(fields)
                        ],
                    }
                )
            return SchemaDescribeResult(
                source_label=file_path.parent.name,
                datapackage_path=file_path,
                resources=resource_payloads,
            )

        dp_path = find_datapackage(file_path)
        if not dp_path:
            raise ValueError(
                f"Could not find authoritative datapackage.json for: {file_path}"
            )

        with open(dp_path, "r") as f:
            pkg = json.load(f)

        resource = None
        filename = file_path.name
        for res in pkg.get("resources", []):
            if match_resource_path(filename, res.get("path", "")):
                resource = res
                break

        if not resource:
            raise ValueError(f"No resource found in {dp_path} for: {filename}")

        fields = resource.get("schema", {}).get("fields", [])
        return SchemaDescribeResult(
            source_label=file_path.name,
            datapackage_path=dp_path,
            resources=[
                {
                    "name": resource.get("name", file_path.name),
                    "path": resource.get("path"),
                    "fields": [
                        SchemaField(
                            index=i,
                            name=field["name"],
                            type=field.get("type", "string"),
                        ).model_dump()
                        for i, field in enumerate(fields)
                    ],
                }
            ],
        )

    def locate_datapackage(self, file_path: Path) -> Optional[Path]:
        """Find the authoritative datapackage.json for a file or directory."""
        from cocli.utils.duckdb_utils import find_datapackage

        if file_path.is_dir() and (file_path / "datapackage.json").exists():
            file_path = file_path / "datapackage.json"
        return find_datapackage(file_path)

    def sample_rows(
        self,
        file_path: Path,
        limit: int = 10,
        resource_name: Optional[str] = None,
    ) -> SampleResult:
        """Load first N rows from a USV file or datapackage via DuckDB."""
        from cocli.utils.duckdb_utils import load_from_datapackage, load_usv_to_duckdb

        # resource_name retained for API parity with CLI (unused in original path).
        _ = resource_name

        if file_path.is_dir() and (file_path / "datapackage.json").exists():
            file_path = file_path / "datapackage.json"

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        con = duckdb.connect(database=":memory:")
        try:
            if file_path.name == "datapackage.json":
                load_from_datapackage(con, "sample_table", file_path)
                title = f"Sample: {file_path.parent.name} (Unified Datapackage)"
            else:
                load_usv_to_duckdb(con, "sample_table", file_path)
                title = f"Sample: {file_path.name}"

            results = con.execute(
                f"SELECT * FROM sample_table LIMIT {limit}"
            ).fetchall()
            columns = [
                col[1]
                for col in con.execute("PRAGMA table_info('sample_table')").fetchall()
            ]
            rows = [list(row) for row in results]
            return SampleResult(title=title, columns=columns, rows=rows)
        finally:
            con.close()

    def compute_metrics(
        self,
        file_path: Path,
        resource_name: Optional[str] = None,
        output_path: Optional[Path] = None,
        log_callback: Optional[LogCallback] = None,
    ) -> MetricsResult:
        """
        Compute data-quality metrics for a USV dataset or datapackage.

        Tries DuckDB first; falls back to pure-Python USV scanning.
        Optionally writes a Markdown report to ``output_path``.
        """
        from cocli.utils.duckdb_utils import (
            find_datapackage,
            get_schema_field_names,
            load_from_datapackage,
            load_usv_to_duckdb,
        )

        _ = resource_name

        if file_path.is_dir() and (file_path / "datapackage.json").exists():
            file_path = file_path / "datapackage.json"

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if file_path.name == "datapackage.json":
            dp_path: Path = file_path
            usv_path = file_path
        else:
            found_dp = find_datapackage(file_path)
            if not found_dp:
                raise ValueError(f"Could not find datapackage for {file_path}")
            dp_path = found_dp
            usv_path = file_path

        with open(dp_path, "r") as f:
            pkg = json.load(f)

        resource = pkg.get("resources", [{}])[0]
        schema_fields = get_schema_field_names(dp_path)
        fields_info = {
            f["name"]: f.get("type", "string")
            for f in resource.get("schema", {}).get("fields", [])
        }
        logger.debug(
            "Schema has %s fields: %s...",
            len(schema_fields),
            schema_fields[:5],
        )

        con = duckdb.connect(database=":memory:")
        try:
            if file_path.name == "datapackage.json":
                load_from_datapackage(con, "metrics_data", file_path)
            else:
                load_usv_to_duckdb(con, "metrics_data", usv_path, dp_path)

            cols_info = con.execute("PRAGMA table_info('metrics_data')").fetchall()
            loaded_cols = [c[1] for c in cols_info]
            logger.debug("Loaded table has columns: %s...", loaded_cols[:5])

            # A "place_id"-keyed dataset (e.g. gm-list's raw discovery archive)
            # legitimately has multiple rows per place - the same business
            # discovered via overlapping geo-tiles / different keyword
            # searches. Computing per-field counts over those raw rows
            # double-counts every duplicated place, inflating every metric by
            # the same ratio (raw rows / distinct places) - it doesn't tell
            # you anything about real business coverage, and reporting a raw
            # "Total Rows" alongside it only invites reading percentages that
            # were never computed. Reduce to one row per place_id first (same
            # null-ignoring MAX() per column already proven in
            # scripts/sql/gm_prospects_yield/queries/06_gm_results_reduced_per_place_id.sql)
            # so every subsequent metric is a real "N of M distinct places"
            # percentage, not a raw row count with an unrelated aside.
            metrics_table = "metrics_data"
            denominator_label = "Total Rows"
            is_deduped = "place_id" in loaded_cols
            if is_deduped:
                agg_cols = ", ".join(
                    f'max("{c}") AS "{c}"' for c in loaded_cols if c != "place_id"
                )
                con.execute("DROP TABLE IF EXISTS metrics_data_deduped")
                con.execute(f"""
                    CREATE TABLE metrics_data_deduped AS
                    SELECT place_id, {agg_cols}
                    FROM metrics_data
                    GROUP BY place_id
                """)
                metrics_table = "metrics_data_deduped"
                denominator_label = "Distinct Places"

            denom_row = con.execute(f"SELECT COUNT(*) FROM {metrics_table}").fetchone()
            denominator = denom_row[0] if denom_row is not None else 0

            metrics: Dict[str, Any] = {denominator_label: denominator}
            for field in schema_fields:
                if field in loaded_cols:
                    field_type = fields_info.get(field, "string")
                    if field_type in ("integer", "number"):
                        count_row = con.execute(
                            f'SELECT COUNT(*) FROM {metrics_table} WHERE '
                            f'TRY_CAST("{field}" AS VARCHAR) IS NOT NULL AND '
                            f'TRY_CAST("{field}" AS VARCHAR) != \'\' AND '
                            f'TRY_CAST("{field}" AS VARCHAR) != \'NULL\''
                        ).fetchone()
                    else:
                        count_row = con.execute(
                            f'SELECT COUNT(*) FROM {metrics_table} WHERE '
                            f'"{field}" IS NOT NULL AND "{field}" != \'\' AND '
                            f'"{field}" != \'NULL\''
                        ).fetchone()
                    count = count_row[0] if count_row is not None else 0
                    if count > 0:
                        if is_deduped and denominator > 0:
                            pct = 100.0 * count / denominator
                            metrics[field] = f"{count} ({pct:.1f}%)"
                        else:
                            metrics[field] = count

            result = MetricsResult(
                source_name=usv_path.name,
                metrics=metrics,
                used_fallback=False,
            )
        except Exception as e:
            logger.debug("DuckDB metrics approach failed: %s", e)
            _emit(log_callback, "Falling back to Python processing...")
            result = self._compute_metrics_fallback(usv_path, schema_fields)
        finally:
            con.close()

        if output_path:
            suffix = " (fallback)" if result.used_fallback else ""
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(f"# Metrics: {result.source_name}{suffix}\n\n")
                f.write("| Metric | Count |\n")
                f.write("| :--- | :--- |\n")
                for metric, count in result.metrics.items():
                    f.write(f"| {metric} | {count} |\n")
            result.output_path = output_path
            result.message = f"Metrics report written to {output_path}"

        return result

    @staticmethod
    def _compute_metrics_fallback(
        usv_path: Path, schema_fields: Sequence[str]
    ) -> MetricsResult:
        """Pure-Python metrics when DuckDB load/query fails.

        Same reduce-before-counting semantics as the DuckDB path (see
        compute_metrics): a place_id-keyed dataset can have multiple rows
        per place, so a field is "present" for a place if ANY of that
        place's rows had it, not counted once per row.
        """
        csv.field_size_limit(sys.maxsize)
        field_index = {name: i for i, name in enumerate(schema_fields)}
        place_idx = field_index.get("place_id")
        total_rows = 0
        place_ids: set[str] = set()
        # Per-place-id-keyed dataset: which places have a non-empty value
        # for each field, on ANY of their (possibly duplicate) rows.
        field_places_with_value: Dict[str, set[str]] = {f: set() for f in schema_fields}
        # No place_id column at all: nothing to dedupe on, count per row.
        field_row_counts: Dict[str, int] = {f: 0 for f in schema_fields}

        with open(usv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter="\x1f")
            for row in reader:
                if not row or not any(row):
                    continue
                total_rows += 1
                place_id_val = (
                    row[place_idx] if place_idx is not None and place_idx < len(row) else None
                )
                if place_id_val is not None:
                    place_ids.add(place_id_val)
                for field_name, idx in field_index.items():
                    if idx < len(row):
                        val = row[idx].strip()
                        if val and val.lower() != "null":
                            field_row_counts[field_name] += 1
                            if place_id_val is not None:
                                field_places_with_value[field_name].add(place_id_val)

        if place_idx is not None:
            denominator = len(place_ids)
            metrics: Dict[str, Any] = {"Distinct Places": denominator}
            for field in schema_fields:
                count = len(field_places_with_value[field])
                if count and denominator > 0:
                    pct = 100.0 * count / denominator
                    metrics[field] = f"{count} ({pct:.1f}%)"
        else:
            metrics = {"Total Rows": total_rows}
            for field, count in field_row_counts.items():
                if count:
                    metrics[field] = count

        return MetricsResult(
            source_name=usv_path.name,
            metrics=metrics,
            used_fallback=True,
        )

    def search_usv(
        self,
        file_path: Path,
        query: str,
        columns: str = "slug, phone, reviews_count",
    ) -> SearchResult:
        """Schema-aware DuckDB search over a USV file."""
        from cocli.utils.duckdb_utils import (
            find_datapackage,
            get_schema_field_names,
            load_usv_to_duckdb,
            normalize_column_names,
            validate_query_columns,
        )

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        schema_warning: Optional[str] = None
        valid_preview: List[str] = []
        dp_path = find_datapackage(file_path)
        if not dp_path:
            schema_warning = (
                "No datapackage.json found. Schema validation disabled."
            )
            schema_fields: List[str] = []
        else:
            schema_fields = get_schema_field_names(dp_path)
            invalid_cols = validate_query_columns(query, schema_fields)
            if invalid_cols:
                raise UnknownColumnError(
                    invalid_cols, list(schema_fields[:10])
                )
            columns = normalize_column_names(columns, schema_fields)
            valid_preview = list(schema_fields[:10])

        con = duckdb.connect(database=":memory:")
        try:
            load_usv_to_duckdb(con, "search_table", file_path)
            sql = f"SELECT {columns} FROM search_table WHERE {query}"
            cursor = con.execute(sql)
            results = cursor.fetchall()
            result_cols = [desc[0] for desc in cursor.description] if results else []
            if not result_cols:
                result_cols = [
                    c.strip() for c in columns.split(",") if c.strip() != "*"
                ]
            return SearchResult(
                query=query,
                columns=result_cols,
                rows=[list(row) for row in results],
                row_count=len(results),
                schema_warning=schema_warning,
                valid_columns_preview=valid_preview,
            )
        finally:
            con.close()

    def inspect_row(self, file_path: Path, row_number: int = 1) -> InspectRowResult:
        """Inspect a specific 1-indexed USV row against its datapackage schema."""
        from cocli.utils.duckdb_utils import find_datapackage, match_resource_path
        from cocli.utils.usv_utils import USVReader

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        dp_path = find_datapackage(file_path)
        if not dp_path:
            raise ValueError(
                f"Could not find authoritative datapackage.json for: {file_path}"
            )

        with open(dp_path, "r") as f:
            pkg = json.load(f)

        resource = None
        filename = file_path.name
        for res in pkg.get("resources", []):
            if match_resource_path(filename, res.get("path", "")):
                resource = res
                break

        if not resource:
            raise ValueError(f"No resource found in {dp_path} for: {filename}")

        fields = resource.get("schema", {}).get("fields", [])

        with open(file_path, "r", encoding="utf-8") as f:
            reader = USVReader(f)
            row = None
            for i, r in enumerate(reader):
                if i == row_number - 1:
                    row = r
                    break

            if row is None:
                raise ValueError(f"Row {row_number} not found in {file_path.name}")

        field_values: List[Tuple[int, str, str]] = []
        for i, field in enumerate(fields):
            val = row[i] if i < len(row) else ""
            field_values.append((i, field["name"], str(val)))

        return InspectRowResult(
            file_name=file_path.name,
            row_number=row_number,
            fields=field_values,
        )

    def compact_queue(
        self, queue_name: str, campaign_name: Optional[str] = None
    ) -> QueueCompactResult:
        """Compact a queue's results into a unified dataset (e.g. gm-list)."""
        from cocli.core.transformers.gm_list_to_checkpoint import (
            compact_gm_list_results,
        )

        name = campaign_name or self.campaign_name
        if queue_name == "gm-list":
            count = compact_gm_list_results(name)
            return QueueCompactResult(
                campaign_name=name,
                queue_name=queue_name,
                success=True,
                message=f"Compaction complete. Merged {count} records.",
                records_merged=count,
            )
        raise ValueError(
            f"Unknown queue '{queue_name}'. Currently supported: gm-list"
        )
