from __future__ import annotations
import json
import logging
import math
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, cast

import toml
from pydantic import BaseModel, Field

from ..core.config import get_campaign, get_campaign_dir, get_context
from ..core.reporting import get_campaign_stats

logger = logging.getLogger(__name__)

LogCallback = Callable[[str], None]


def _emit(log_callback: Optional[LogCallback], message: str) -> None:
    logger.info(message)
    if log_callback is not None:
        log_callback(message)


class VizExportResult(BaseModel):
    """Result of a KML / resources export write."""

    campaign_name: str
    success: bool = True
    message: str = ""
    export_dir: Optional[Path] = None
    files: list[Path] = Field(default_factory=list)
    count: int = 0


class PublishKmlResult(BaseModel):
    """Result of generating and publishing campaign KML layers to S3."""

    campaign_name: str
    success: bool = True
    message: str = ""
    bucket_name: str = ""
    domain: str = ""
    uploaded_keys: list[str] = Field(default_factory=list)
    layers_key: str = "kml/layers.json"


class ReportingService:
    def __init__(self, campaign_name: Optional[str] = None):
        self.campaign_name = campaign_name or get_campaign() or ""

    def get_environment_status(self) -> dict[str, Any]:
        """
        Returns the current status of the cocli environment.
        Corresponds to 'cocli status'.
        """
        import os
        
        campaign_name = self.campaign_name
        context_filter = get_context()
        
        # Scrape Strategy Detection
        is_fargate = os.getenv("COCLI_RUNNING_IN_FARGATE") == "true"
        aws_profile = os.getenv("AWS_PROFILE")
        local_dev = os.getenv("LOCAL_DEV")
        
        strategy = "Unknown"
        details = []

        if is_fargate:
            strategy = "Cloud / Fargate"
            details.append("Running inside AWS Fargate container")
            details.append("Using IAM Task Role for permissions")
        elif local_dev:
            strategy = "Local Docker (Hybrid)"
            details.append("Running in local Docker container")
            if aws_profile:
                 details.append(f"Using AWS Profile: {aws_profile}")
        else:
            strategy = "Local Host"
            details.append("Running directly on host machine")
            if aws_profile:
                 details.append(f"Using AWS Profile: {aws_profile}")
            else:
                 details.append("Using default AWS credentials chain")

        queue_url = os.getenv("COCLI_ENRICHMENT_QUEUE_URL")
        
        from ..core.paths import paths
        from ..core.config import load_campaign_config
        
        s3_bucket = "N/A"
        if campaign_name:
            try:
                config = load_campaign_config(campaign_name)
                s3_bucket = f"s3://{config.get('aws', {}).get('data_bucket_name', 'unknown')}"
            except Exception:
                pass

        return {
            "campaign": campaign_name,
            "context": context_filter,
            "strategy": strategy,
            "strategy_details": details,
            "enrichment_queue_url": queue_url,
            "data_root": str(paths.root),
            "s3_data_root": s3_bucket
        }

    def get_campaign_stats(self, campaign_name: Optional[str] = None) -> dict[str, Any]:
        """
        Returns a comprehensive dictionary of campaign statistics.
        Caches the result to disk.
        """
        target_campaign = campaign_name or self.campaign_name
        try:
            stats = get_campaign_stats(target_campaign)
            stats['last_updated'] = datetime.now(timezone.utc).isoformat()
            stats['campaign_name'] = target_campaign
            
            # Cache to disk
            self.save_cached_report(target_campaign, "status", stats)
            
            return stats
        except Exception as e:
            logger.error(f"Failed to get campaign stats for {target_campaign}: {e}")
            return {
                "error": str(e),
                "campaign_name": target_campaign,
                "last_updated": datetime.now(timezone.utc).isoformat()
            }

    async def get_cluster_health(self) -> list[dict[str, Any]]:
        """
        Returns health status of all workers in the cluster.
        This is an SSH-based real-time check.
        """
        # We might need to resolve the worker service from the global container 
        # or instantiate a new one for this campaign.
        # Given ServiceContainer's factory pattern, we can just create one.
        from .worker_service import WorkerService
        ws = WorkerService(campaign_name=self.campaign_name)
        return await ws.get_cluster_health()

    def get_index_stats(self, campaign_name: Optional[str] = None) -> dict[str, Any]:
        """Returns record counts and paths for core system indexes."""
        from ..core.paths import paths
        import subprocess
        
        target_campaign = campaign_name or self.campaign_name
        campaign_node = paths.campaign(target_campaign)
        
        def count_lines(path: Path) -> int:
            if not path.exists():
                return 0
            try:
                # Use 'wc -l' for speed on USV files
                res = subprocess.run(["wc", "-l", str(path)], capture_output=True, text=True)
                if res.returncode == 0:
                    # Subtract 1 for header
                    return max(0, int(res.stdout.strip().split()[0]) - 1)
            except Exception:
                pass
            return 0

        from ..core.email_index_manager import EmailIndexManager
        email_manager = EmailIndexManager(target_campaign)
        email_root = email_manager.index_root
        
        # Calculate email count across all shards and inbox
        email_count = 0
        try:
            for p in email_manager.inbox_dir.rglob("*.usv"):
                email_count += 1
            for p in email_manager.shards_dir.glob("*.usv"):
                email_count += count_lines(p)
        except Exception:
            pass

        # Shared Domain Index (Sharded)
        domain_root = paths.indexes / "domains"
        domain_count = 0
        if domain_root.exists():
            try:
                # Count files in inbox
                for p in (domain_root / "inbox").rglob("*.usv"):
                    domain_count += 1
                # Count lines in shards
                for p in (domain_root / "shards").glob("*.usv"):
                    domain_count += count_lines(p)
            except Exception:
                pass
        
        # Exclusion Index (Campaign Specific)
        from cocli.core.ordinant import IndexIdentity
        exclusion_index_path = campaign_node.index(IndexIdentity.EXCLUSIONS).checkpoint



        return {
            "gm_prospects": {
                "count": count_lines(campaign_node.index("google_maps_prospects").checkpoint),
                "path": str(campaign_node.index("google_maps_prospects").checkpoint.relative_to(paths.root))
            },
            "email_index": {
                "count": email_count,
                "path": str(email_root.relative_to(paths.root))
            },
            "domain_index": {
                "count": domain_count,
                "path": str(domain_root.relative_to(paths.root)) if domain_root.exists() else "N/A"
            },
            "lifecycle": {
                "count": count_lines(campaign_node.lifecycle),
                "path": str(campaign_node.lifecycle.relative_to(paths.root))
            },
            "exclusions": {
                "count": count_lines(exclusion_index_path),
                "path": str(exclusion_index_path.relative_to(paths.root)) if exclusion_index_path.exists() else "N/A"
            }
        }

    def save_cached_report(self, campaign_name: str, report_type: str, data: dict[str, Any]) -> None:
        """Saves a report to the local reports cache and the campaign exports dir."""
        from ..core.config import get_cocli_app_data_dir, get_campaigns_dir
        
        # 1. Save to User App Data Cache (Hidden fallback)
        report_dir = get_cocli_app_data_dir() / "reports" / campaign_name
        report_dir.mkdir(parents=True, exist_ok=True)
        
        import json
        with open(report_dir / f"{report_type}.json", "w") as f:
            json.dump(data, f, indent=2)

        # 2. Save to Campaign Exports Directory (Primary location)
        exports_dir = get_campaigns_dir() / campaign_name / "exports"
        if exports_dir.exists():
            with open(exports_dir / f"{report_type}.json", "w") as f:
                json.dump(data, f, indent=2)

    def load_cached_report(self, campaign_name: str, report_type: str) -> Optional[dict[str, Any]]:
        """Loads a report from the campaign exports dir or the user cache fallback."""
        from ..core.config import get_cocli_app_data_dir, get_campaigns_dir
        import json

        # 1. Try Campaign Exports first
        report_file = get_campaigns_dir() / campaign_name / "exports" / f"{report_type}.json"
        if report_file.exists():
            try:
                with open(report_file, "r") as f:
                    return cast(dict[str, Any], json.load(f))
            except Exception:
                pass

        # 2. Fallback to User App Data Cache
        fallback_file = get_cocli_app_data_dir() / "reports" / campaign_name / f"{report_type}.json"
        if fallback_file.exists():
            try:
                with open(fallback_file, "r") as f:
                    return cast(dict[str, Any], json.load(f))
            except Exception:
                return None
        return None

    def get_email_analysis(self, campaign_name: Optional[str] = None) -> dict[str, Any]:
        """
        Returns deep analysis on emails for the campaign.
        Corresponds to 'make analyze-emails' / 'scripts/debug_stats.py'.
        """
        target_campaign = campaign_name or self.campaign_name
        # For now, we'll just return some placeholder data or 
        # a subset of what get_campaign_stats provides until 
        # we migrate more of debug_stats.py
        stats = self.get_campaign_stats(target_campaign)
        return {
            "total_emails": stats.get("emails_found_count", 0),
            "companies_with_emails": stats.get("companies_with_emails_count", 0),
            "campaign_name": target_campaign
        }

    # ------------------------------------------------------------------
    # Campaign visualization / KML exports (from commands/campaign/viz.py)
    # ------------------------------------------------------------------

    def _require_campaign_dir(self, campaign_name: Optional[str] = None) -> tuple[str, Path]:
        name = campaign_name or self.campaign_name
        if not name:
            raise ValueError("No campaign name provided and no campaign context is set.")
        campaign_dir = get_campaign_dir(name)
        if not campaign_dir:
            raise ValueError(f"Campaign directory not found for {name}")
        return name, campaign_dir

    @staticmethod
    def _parse_sw_tile_id(tile_id: str) -> Optional[tuple[float, float]]:
        """Parse a southwest-corner 0.1-degree tile id (``30.0_-90.0``)."""
        parts = tile_id.split("_")
        if len(parts) < 2:
            return None
        try:
            lat = math.floor(round(float(parts[0]), 6) * 10) / 10.0
            lon = math.floor(round(float(parts[1]), 6) * 10) / 10.0
        except ValueError:
            return None
        return lat, lon

    @staticmethod
    def _collect_map_tile_ids(campaign_dir: Path) -> list[str]:
        """Unique tile ids from ``queues/map-tile/{pending,completed}``."""
        queue_root = campaign_dir / "queues" / "map-tile"
        seen: dict[str, None] = {}
        for phase in ("pending", "completed"):
            phase_dir = queue_root / phase
            if not phase_dir.is_dir():
                continue
            for path in phase_dir.rglob("*.usv"):
                parsed = ReportingService._parse_sw_tile_id(path.stem)
                if parsed is None:
                    continue
                seen[f"{parsed[0]:.1f}_{parsed[1]:.1f}"] = None
        return list(seen.keys())

    @staticmethod
    def _tile_status(data: dict[str, Any]) -> str:
        if data.get("wilderness"):
            return "wilderness"
        scraped_count = int(data.get("scraped_count") or 0)
        phrase_count = int(data.get("phrase_count") or 0)
        if phrase_count > 0 and scraped_count >= phrase_count:
            return "scraped"
        if scraped_count > 0:
            return "partial"
        return "unscraped"

    @staticmethod
    def _tile_polygon_coords(lat: float, lon: float) -> str:
        lat_max, lon_max = lat + 0.1, lon + 0.1
        return (
            f"{lon},{lat},0 {lon_max},{lat},0 "
            f"{lon_max},{lat_max},0 {lon},{lat_max},0 {lon},{lat},0"
        )

    @staticmethod
    def _tile_fill_color(data: dict[str, Any]) -> str:
        """KML PolyStyle color (aabbggrr) for scrape status + item count."""
        status = ReportingService._tile_status(data)
        if status == "wilderness":
            return "33ffffff"
        if status == "unscraped":
            return "4000a5ff"
        if status == "partial":
            return "4000ffff"
        if int(data.get("total_items") or 0) > 0:
            return "4000ff00"
        return "40808080"

    @staticmethod
    def _tile_description(tile_id: str, data: dict[str, Any]) -> str:
        status = ReportingService._tile_status(data)
        phrases: dict[str, Any] = data.get("phrases") or {}
        rows = [
            f"<b>Tile: {tile_id}</b><br>",
            f"Status: {status}<br><br>",
            "<table border='1' cellspacing='0' cellpadding='3'>",
            "<tr><th align='left'>Search Phrase</th><th align='right'>Found</th></tr>",
        ]
        sorted_phrases = sorted(
            phrases.items(),
            key=lambda item: (-1 if item[1] is None else int(item[1])),
            reverse=True,
        )
        for phrase, count in sorted_phrases:
            display = "not scraped" if count is None else str(count)
            rows.append(
                f"<tr><td>{phrase}</td><td align='right'>{display}</td></tr>"
            )
        rows.append(
            f"<tr><td><b>Total</b></td>"
            f"<td align='right'><b>{data.get('total_items', 0)}</b></td></tr>"
        )
        rows.append("</table>")
        return "".join(rows)

    @staticmethod
    def _tiles_to_geojson(aggregated_tiles: dict[str, dict[str, Any]]) -> dict[str, Any]:
        features: list[dict[str, Any]] = []
        for tile_id, data in aggregated_tiles.items():
            lat = float(data["lat"])
            lon = float(data["lon"])
            status = ReportingService._tile_status(data)
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "tile_id": tile_id,
                        "status": status,
                        "scraped": status == "scraped",
                        "wilderness": bool(data.get("wilderness")),
                        "total_items": int(data.get("total_items") or 0),
                        "phrases": data.get("phrases") or {},
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [lon, lat],
                                [lon + 0.1, lat],
                                [lon + 0.1, lat + 0.1],
                                [lon, lat + 0.1],
                                [lon, lat],
                            ]
                        ],
                    },
                }
            )
        return {"type": "FeatureCollection", "features": features}

    def generate_coverage_kml(
        self, campaign_name: Optional[str] = None
    ) -> VizExportResult:
        """
        Generate map-tile coverage KML + GeoJSON for the KML viewer.

        Universe of tiles is ``queues/map-tile/`` (pending + completed).
        Item counts and scrape status come from the ``scraped-tiles`` witness
        index. Falls back to a scrape-index scan when the map-tile queue is
        empty (legacy scraped-areas data).

        Writes under ``{campaign}/exports/``:
        - ``coverage_{phrase}.kml``
        - ``coverage_grid_aggregated.kml``
        - ``map_tiles.geojson``
        """
        from cocli.core.scrape_index import ScrapeIndex
        from cocli.core.text_utils import slugify

        name, campaign_dir = self._require_campaign_dir(campaign_name)
        export_dir = campaign_dir / "exports"
        export_dir.mkdir(exist_ok=True)

        config_path = campaign_dir / "config.toml"
        with open(config_path, "r") as f:
            config = toml.load(f)

        search_phrases: list[str] = list(
            config.get("prospecting", {}).get("queries", [])
        )
        scrape_index = ScrapeIndex()
        aggregated_tiles: dict[str, dict[str, Any]] = {}
        areas_by_phrase: dict[str, list[tuple[str, float, float]]] = {}

        map_tile_ids = self._collect_map_tile_ids(campaign_dir)
        if map_tile_ids:
            for tile_id in map_tile_ids:
                parsed = self._parse_sw_tile_id(tile_id)
                if parsed is None:
                    continue
                lat, lon = parsed
                phrases_map: dict[str, Optional[int]] = {}
                total_items = 0
                scraped_count = 0
                for phrase in search_phrases:
                    area = scrape_index.is_tile_scraped(phrase, tile_id)
                    if area is None:
                        phrases_map[phrase] = None
                        continue
                    scraped_count += 1
                    phrases_map[phrase] = area.items_found
                    total_items += area.items_found
                    areas_by_phrase.setdefault(phrase, []).append(
                        (tile_id, lat, lon)
                    )
                aggregated_tiles[tile_id] = {
                    "lat": lat,
                    "lon": lon,
                    "total_items": total_items,
                    "phrases": phrases_map,
                    "scraped_count": scraped_count,
                    "phrase_count": len(search_phrases),
                    "wilderness": scrape_index.is_wilderness_tile(tile_id),
                }
        else:
            scraped_areas = scrape_index.get_all_areas_for_phrases(search_phrases)
            for area in scraped_areas:
                center_lat = (area.lat_min + area.lat_max) / 2
                center_lon = (area.lon_min + area.lon_max) / 2
                parsed = self._parse_sw_tile_id(f"{center_lat}_{center_lon}")
                if parsed is None:
                    continue
                lat, lon = parsed
                tile_id = f"{lat:.1f}_{lon:.1f}"
                if tile_id not in aggregated_tiles:
                    aggregated_tiles[tile_id] = {
                        "lat": lat,
                        "lon": lon,
                        "total_items": 0,
                        "phrases": {},
                        "scraped_count": 0,
                        "phrase_count": 0,
                        "wilderness": scrape_index.is_wilderness_tile(tile_id),
                    }
                tile = aggregated_tiles[tile_id]
                tile["total_items"] = int(tile["total_items"]) + area.items_found
                phrases_map = cast(dict[str, Optional[int]], tile["phrases"])
                previous = phrases_map.get(area.phrase) or 0
                phrases_map[area.phrase] = previous + area.items_found
                tile["scraped_count"] = len(phrases_map)
                tile["phrase_count"] = len(phrases_map)
                areas_by_phrase.setdefault(area.phrase, []).append(
                    (tile_id, lat, lon)
                )

        for tile_id, data in aggregated_tiles.items():
            data["wilderness"] = bool(
                data.get("wilderness") or scrape_index.is_wilderness_tile(tile_id)
            )

        if not aggregated_tiles:
            return VizExportResult(
                campaign_name=name,
                success=True,
                message="No map tiles found.",
                export_dir=export_dir,
                count=0,
            )

        colors = ["ff0000ff", "ff00ff00", "ffff0000", "ff00ffff", "ffff00ff", "ffffff00"]
        phrase_list = sorted(areas_by_phrase.keys())
        phrase_colors = {
            phrase: colors[i % len(colors)] for i, phrase in enumerate(phrase_list)
        }

        written: list[Path] = []
        for phrase, tiles in areas_by_phrase.items():
            kml_placemarks: list[str] = []
            color = phrase_colors.get(phrase, "ffffffff")
            for tile_id, lat, lon in tiles:
                coordinates = self._tile_polygon_coords(lat, lon)
                placemark = f'''        <Placemark>
                <name>{phrase}</name>
                <Style><LineStyle><width>0</width></LineStyle><PolyStyle><color>80{color[2:]}</color></PolyStyle></Style>
                <Polygon><outerBoundaryIs><LinearRing><coordinates>{coordinates}</coordinates></LinearRing></outerBoundaryIs></Polygon>
            </Placemark>'''
                kml_placemarks.append(placemark)

            kml_content = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<kml xmlns="http://www.opengis.net/kml/2.2">'
                f"<Document>{chr(10).join(kml_placemarks)}</Document></kml>"
            )
            out_path = export_dir / f"coverage_{slugify(phrase)}.kml"
            out_path.write_text(kml_content)
            written.append(out_path)

        agg_placemarks: list[str] = []
        for tile_id, data in aggregated_tiles.items():
            coordinates = self._tile_polygon_coords(
                float(data["lat"]), float(data["lon"])
            )
            description = self._tile_description(tile_id, data)
            color = self._tile_fill_color(data)
            if self._tile_status(data) == "wilderness":
                line_style = "<LineStyle><color>ffffffff</color><width>1.5</width></LineStyle>"
            else:
                line_style = "<LineStyle><width>0</width></LineStyle>"
            placemark = f'''        <Placemark>
            <name>{tile_id}</name>
            <description><![CDATA[{description}]]></description>
            <Style>
                {line_style}
                <PolyStyle><color>{color}</color></PolyStyle>
            </Style>
            <Polygon>
                <outerBoundaryIs><LinearRing><coordinates>{coordinates}</coordinates></LinearRing></outerBoundaryIs>
            </Polygon>
        </Placemark>'''
            agg_placemarks.append(placemark)

        agg_path = export_dir / "coverage_grid_aggregated.kml"
        agg_path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<kml xmlns="http://www.opengis.net/kml/2.2">'
            f"<Document>{chr(10).join(agg_placemarks)}</Document></kml>"
        )
        written.append(agg_path)

        geojson_path = export_dir / "map_tiles.geojson"
        geojson_path.write_text(
            json.dumps(self._tiles_to_geojson(aggregated_tiles), indent=2)
        )
        written.append(geojson_path)

        wilderness_path = export_dir / "wilderness-tiles.json"
        wilderness_path.write_text(
            json.dumps(sorted(scrape_index.list_wilderness_tile_ids()), indent=2)
        )
        written.append(wilderness_path)

        return VizExportResult(
            campaign_name=name,
            success=True,
            message=(
                f"Map tile visualization complete ({len(aggregated_tiles)} tiles). "
                f"Files saved in: {export_dir}"
            ),
            export_dir=export_dir,
            files=written,
            count=len(aggregated_tiles),
        )

    def generate_legacy_scrapes_kml(
        self, campaign_name: Optional[str] = None
    ) -> VizExportResult:
        """Generate KML for legacy (non-grid-aligned) scraped areas."""
        from cocli.core.scrape_index import ScrapeIndex

        name, campaign_dir = self._require_campaign_dir(campaign_name)
        export_dir = campaign_dir / "exports"
        export_dir.mkdir(exist_ok=True)

        scrape_index = ScrapeIndex()
        legacy_areas = [a for a in scrape_index.get_all_scraped_areas() if not a.tile_id]

        if not legacy_areas:
            return VizExportResult(
                campaign_name=name,
                success=True,
                message="No legacy scraped areas found.",
                export_dir=export_dir,
                count=0,
            )

        kml_placemarks: list[str] = []
        for area in legacy_areas:
            coordinates = (
                f"{area.lon_min},{area.lat_min},0 {area.lon_max},{area.lat_min},0 "
                f"{area.lon_max},{area.lat_max},0 {area.lon_min},{area.lat_max},0 "
                f"{area.lon_min},{area.lat_min},0"
            )
            placemark = (
                f"<Placemark><name>Legacy: {area.phrase}</name>"
                "<Style><LineStyle><color>ffffaa00</color></LineStyle>"
                "<PolyStyle><color>20ffaa00</color></PolyStyle></Style>"
                "<Polygon><outerBoundaryIs><LinearRing>"
                f"<coordinates>{coordinates}</coordinates>"
                "</LinearRing></outerBoundaryIs></Polygon></Placemark>"
            )
            kml_placemarks.append(placemark)

        out_path = export_dir / "legacy_scrapes.kml"
        out_path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<kml xmlns="http://www.opengis.net/kml/2.2">'
            f"<Document>{''.join(kml_placemarks)}</Document></kml>"
        )

        return VizExportResult(
            campaign_name=name,
            success=True,
            message="Legacy coverage KML saved.",
            export_dir=export_dir,
            files=[out_path],
            count=len(legacy_areas),
        )

    def resolve_publish_config(
        self,
        profile: Optional[str] = None,
        bucket_name: Optional[str] = None,
        domain: Optional[str] = None,
        campaign_name: Optional[str] = None,
    ) -> dict[str, str]:
        """Resolve AWS profile / domain / bucket for KML publish from campaign config."""
        name, campaign_dir = self._require_campaign_dir(campaign_name)
        config_path = campaign_dir / "config.toml"
        config: dict[str, Any] = {}
        if config_path.exists():
            with open(config_path, "r") as f:
                config = toml.load(f)

        aws_config = config.get("aws", {})
        if not profile:
            profile = (
                aws_config.get("profile")
                or aws_config.get("aws-profile")
                or config.get("aws-profile")
            )
        if not profile:
            raise ValueError(
                "AWS profile required (--profile or '[aws] profile' in config.toml)."
            )

        hosted_zone_domain = aws_config.get("hosted-zone-domain") or config.get(
            "hosted-zone-domain"
        )
        if not domain:
            if hosted_zone_domain:
                domain = f"cocli.{hosted_zone_domain}"
            else:
                raise ValueError(
                    "Domain required (--domain or config 'hosted-zone-domain')."
                )

        if not bucket_name:
            if hosted_zone_domain:
                bucket_slug = str(hosted_zone_domain).replace(".", "-")
                bucket_name = f"cocli-web-assets-{bucket_slug}"
            else:
                raise ValueError(
                    "Bucket required (--bucket or derived from config 'hosted-zone-domain')."
                )

        return {
            "campaign_name": name,
            "profile": str(profile),
            "domain": str(domain),
            "bucket_name": str(bucket_name),
        }

    def generate_publish_kmls(
        self,
        campaign_name: Optional[str] = None,
        log_callback: Optional[LogCallback] = None,
    ) -> None:
        """Run the cocli KML generation pipeline used by publish-kml."""
        name, _ = self._require_campaign_dir(campaign_name)
        _emit(log_callback, "Generating KML files...")
        base_cmd = [sys.executable, "-m", "cocli.main"]
        steps = [
            ["campaign", "set", name],
            ["campaign", "generate-grid"],
            ["campaign", "visualize-coverage", name],
            ["render-prospects-kml", name],
            ["render", "kml", name],
        ]
        for args in steps:
            subprocess.run(base_cmd + args, check=True, capture_output=True)

    def upload_kml_layers(
        self,
        profile: str,
        bucket_name: str,
        domain: str,
        campaign_name: Optional[str] = None,
        log_callback: Optional[LogCallback] = None,
    ) -> PublishKmlResult:
        """Upload generated KML files and write ``kml/layers.json`` to S3."""
        import boto3

        name, campaign_dir = self._require_campaign_dir(campaign_name)
        kml_type = "application/vnd.google-earth.kml+xml"
        files_to_upload = [
            (
                campaign_dir / "exports" / "map_tiles.geojson",
                f"kml/{name}_map_tiles.geojson",
                "application/geo+json",
            ),
            (
                campaign_dir / "exports" / "wilderness-tiles.json",
                "kml/wilderness-tiles.json",
                "application/json",
            ),
            (
                campaign_dir / "exports" / "coverage_grid_aggregated.kml",
                f"kml/{name}_aggregated.kml",
                kml_type,
            ),
            (
                campaign_dir / "exports" / "target-areas.geojson",
                f"kml/{name}_targets.geojson",
                "application/geo+json",
            ),
            (
                campaign_dir / "exports" / "target-areas.kml",
                f"kml/{name}_targets.kml",
                kml_type,
            ),
            (campaign_dir / f"{name}_prospects.kml", f"kml/{name}_prospects.kml", kml_type),
            (campaign_dir / f"{name}_customers.kml", f"kml/{name}_customers.kml", kml_type),
        ]

        session = boto3.Session(profile_name=profile)
        s3 = session.client("s3")
        uploaded: list[str] = []

        for local_path, remote_key, content_type in files_to_upload:
            if local_path.exists():
                s3.upload_file(
                    str(local_path),
                    bucket_name,
                    remote_key,
                    ExtraArgs={"ContentType": content_type},
                )
                uploaded.append(remote_key)
                _emit(log_callback, f"✓ Uploaded {remote_key}")

        layers = [
            {
                "name": "Target Areas",
                "url": f"https://{domain}/kml/{name}_targets.geojson",
                "default": False,
                "format": "geojson",
            },
            {
                "name": "Map Tiles",
                "url": f"https://{domain}/kml/{name}_map_tiles.geojson",
                "default": True,
                "format": "geojson",
            },
            {
                "name": "Prospects",
                "url": f"https://{domain}/kml/{name}_prospects.kml",
                "default": True,
            },
            {
                "name": "Customers",
                "url": f"https://{domain}/kml/{name}_customers.kml",
                "default": True,
            },
        ]
        layers_key = "kml/layers.json"
        s3.put_object(
            Bucket=bucket_name,
            Key=layers_key,
            Body=json.dumps(layers, indent=2),
            ContentType="application/json",
        )
        _emit(log_callback, "Published layers.json")

        return PublishKmlResult(
            campaign_name=name,
            success=True,
            message="KML publish complete.",
            bucket_name=bucket_name,
            domain=domain,
            uploaded_keys=uploaded,
            layers_key=layers_key,
        )

    def publish_kml(
        self,
        profile: Optional[str] = None,
        bucket_name: Optional[str] = None,
        domain: Optional[str] = None,
        campaign_name: Optional[str] = None,
        log_callback: Optional[LogCallback] = None,
        generate: bool = True,
    ) -> PublishKmlResult:
        """Generate all campaign KMLs and publish layers to S3."""
        cfg = self.resolve_publish_config(
            profile=profile,
            bucket_name=bucket_name,
            domain=domain,
            campaign_name=campaign_name,
        )
        if generate:
            try:
                self.generate_publish_kmls(
                    campaign_name=cfg["campaign_name"], log_callback=log_callback
                )
            except subprocess.CalledProcessError as e:
                msg = f"Error generating KMLs: {e}"
                _emit(log_callback, msg)
                return PublishKmlResult(
                    campaign_name=cfg["campaign_name"],
                    success=False,
                    message=msg,
                    bucket_name=cfg["bucket_name"],
                    domain=cfg["domain"],
                )

        return self.upload_kml_layers(
            profile=cfg["profile"],
            bucket_name=cfg["bucket_name"],
            domain=cfg["domain"],
            campaign_name=cfg["campaign_name"],
            log_callback=log_callback,
        )

    def place_kml_for_turboship(
        self,
        campaign_name: Optional[str] = None,
        turboship_kml_exports_path: Path = Path(
            "../turboheatweldingtools/turboship/data/kml-exports"
        ),
        kml_filename: str = "turboship_coverage.kml",
        kml_type: str = "customers",
    ) -> VizExportResult:
        """Legacy: copy/render a campaign KML into a turboship repo exports path."""
        from cocli.renderers.kml import render_kml_for_campaign

        name, campaign_data_dir = self._require_campaign_dir(campaign_name)
        resolved_exports_dir = (Path.cwd() / turboship_kml_exports_path).resolve()
        resolved_exports_dir.mkdir(parents=True, exist_ok=True)

        if kml_type == "grid":
            source_path = campaign_data_dir / "exports" / "target-areas.kml"
        elif kml_type == "result-grid":
            source_path = campaign_data_dir / "exports" / "coverage_grid_aggregated.kml"
        else:
            render_kml_for_campaign(name, output_dir=resolved_exports_dir)
            source_path = resolved_exports_dir / f"{name}_customers.kml"

        final_kml_path = resolved_exports_dir / kml_filename
        if not source_path.exists():
            return VizExportResult(
                campaign_name=name,
                success=False,
                message=f"Source KML not found: {source_path}",
                export_dir=resolved_exports_dir,
                count=0,
            )

        shutil.copy(str(source_path), str(final_kml_path))
        return VizExportResult(
            campaign_name=name,
            success=True,
            message=f"KML placed at {final_kml_path}",
            export_dir=resolved_exports_dir,
            files=[final_kml_path],
            count=1,
        )

    def export_value_resources(
        self, campaign_name: Optional[str] = None
    ) -> VizExportResult:
        """
        Aggregate value-first resources from prospect/venue indexes.

        Intermediate artifact: ``{campaign}/exports/resources.json``.
        """
        from cocli.models.campaigns.indexes.google_maps_prospect import (
            GoogleMapsProspect,
        )
        from cocli.models.campaigns.indexes.google_maps_venue import GoogleMapsVenue
        from cocli.utils.usv_utils import USVDictReader

        name, campaign_dir = self._require_campaign_dir(campaign_name)
        from cocli.core.paths import paths
        from cocli.core.prospects_csv_manager import ProspectsIndexManager
        manager = ProspectsIndexManager(name)

        checkpoint = manager.checkpoint_path

        venue_checkpoint = (
            paths.campaign(name).index("google_maps_venues").checkpoint
        )


        targets: list[tuple[Path, Any]] = []
        if checkpoint.exists():
            targets.append((checkpoint, GoogleMapsProspect))
        if venue_checkpoint.exists():
            targets.append((venue_checkpoint, GoogleMapsVenue))

        if not targets:
            return VizExportResult(
                campaign_name=name,
                success=True,
                message="No index found. Run achieve-goal first.",
                count=0,
            )

        resources: list[dict[str, Any]] = []
        for path, model_cls in targets:
            with open(path, "r", encoding="utf-8") as f:
                reader = USVDictReader(f)
                for row in reader:
                    try:
                        item = model_cls.model_validate(row)
                        is_val = getattr(item, "is_value_resource", False)
                        if is_val:
                            resources.append(
                                {
                                    "name": item.name,
                                    "category": item.first_category,
                                    "fee_category": getattr(
                                        item, "fee_category", "Unknown"
                                    ),
                                    "address": item.full_address,
                                    "url": item.website or item.gmb_url,
                                    "description": getattr(item, "rationale", ""),
                                    "rating": item.average_rating,
                                    "reviews": item.reviews_count,
                                }
                            )
                    except Exception:
                        continue

        export_path = campaign_dir / "exports" / "resources.json"
        export_path.parent.mkdir(exist_ok=True)
        with open(export_path, "w") as f:
            json.dump(resources, f, indent=2)

        return VizExportResult(
            campaign_name=name,
            success=True,
            message=f"Exported {len(resources)} value resources to {export_path}",
            export_dir=export_path.parent,
            files=[export_path],
            count=len(resources),
        )
