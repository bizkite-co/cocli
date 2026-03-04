from textual.app import ComposeResult
from textual.widgets import Label, DataTable
from textual.containers import VerticalScroll, Horizontal
from typing import Any, Dict, TYPE_CHECKING
import asyncio
from datetime import datetime, UTC

from cocli.core.gossip_bridge import bridge

if TYPE_CHECKING:
    pass

class ClusterView(VerticalScroll):
    """Real-time cluster dashboard using Gossip Bridge data."""

    BINDINGS = [
        ("R", "refresh_cluster", "Refresh Now"),
        ("D", "delete_node", "Delete Selected Registry"),
        ("P", "prune_heartbeat", "Prune Selected Heartbeat"),
    ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.can_focus = True
        self.registry_data: Dict[str, Any] = {}
        self.heartbeat_data: Dict[str, Any] = {}

    def compose(self) -> ComposeResult:
        with Horizontal(id="cluster_header"):
            yield Label("Live Status (Gossip)", id="cluster_title")
            yield Label("", id="cluster_last_updated")
        
        yield DataTable(id="cluster_table")

        with Horizontal(id="registry_header"):
            yield Label("S3 Cluster Registry (Persistent)", id="registry_title")
        
        yield DataTable(id="registry_table")

        with Horizontal(id="status_header"):
            yield Label("Legacy S3 Status (Heartbeats)", id="status_title")
        
        yield DataTable(id="status_table")

    def on_mount(self) -> None:
        table = self.query_one("#cluster_table", DataTable)
        table.add_columns("Node ID", "CPU Load", "Memory %", "Workers", "Active Tasks", "Last Seen")
        table.cursor_type = "row"

        r_table = self.query_one("#registry_table", DataTable)
        r_table.add_columns("Node ID", "IP Address", "Last Registered")
        r_table.cursor_type = "row"

        s_table = self.query_one("#status_table", DataTable)
        s_table.add_columns("Node ID", "Workers (S/D/E)", "Last Seen")
        s_table.cursor_type = "row"
        
        # Start the live refresh loop (non-blocking)
        self.run_worker(self._refresh_loop())

    async def _refresh_loop(self) -> None:
        """Background loop to update the tables."""
        await asyncio.sleep(0.5)
        while True:
            self.update_table()
            self.run_worker(self._refresh_registry())
            self.run_worker(self._refresh_s3_status())
            await asyncio.sleep(10)

    async def _refresh_registry(self) -> None:
        """Fetch registry from S3."""
        from cocli.core.config import get_campaign, load_campaign_config
        from cocli.core.reporting import get_boto3_session
        import json
        
        campaign = get_campaign()
        if not campaign:
            return
        
        try:
            config = load_campaign_config(campaign)
            bucket = config.get("aws", {}).get("data_bucket_name")
            if not bucket:
                return
            
            # Run S3 call in thread to avoid blocking UI
            def _get_s3() -> Dict[str, Any]:
                session = get_boto3_session(config)
                s3 = session.client("s3")
                prefix = "cluster/registry/"
                resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
                nodes = {}
                for obj in resp.get("Contents", []):
                    key = obj["Key"]
                    if not key.endswith(".json"):
                        continue
                    node_id = key.replace(prefix, "").replace(".json", "")
                    data_resp = s3.get_object(Bucket=bucket, Key=key)
                    peer_data = json.loads(data_resp["Body"].read().decode("utf-8"))
                    nodes[node_id] = peer_data
                return nodes

            self.registry_data = await asyncio.to_thread(_get_s3)
            self.update_registry_table()
        except Exception:
            pass

    async def _refresh_s3_status(self) -> None:
        """Fetch legacy heartbeats from status/ prefix in S3."""
        from cocli.core.config import get_campaign, load_campaign_config
        from cocli.core.reporting import get_boto3_session
        import json
        
        campaign = get_campaign()
        if not campaign:
            return
        
        try:
            config = load_campaign_config(campaign)
            bucket = config.get("aws", {}).get("data_bucket_name")
            if not bucket:
                return
            
            def _get_s3_status() -> Dict[str, Any]:
                session = get_boto3_session(config)
                s3 = session.client("s3")
                prefix = "status/"
                resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
                nodes = {}
                for obj in resp.get("Contents", []):
                    key = obj["Key"]
                    if not key.endswith(".json"):
                        continue
                    node_id = key.replace(prefix, "").replace(".json", "")
                    try:
                        data_resp = s3.get_object(Bucket=bucket, Key=key)
                        peer_data = json.loads(data_resp["Body"].read().decode("utf-8"))
                        peer_data["last_modified"] = obj["LastModified"]
                        nodes[node_id] = peer_data
                    except Exception:
                        continue
                return nodes

            self.heartbeat_data = await asyncio.to_thread(_get_s3_status)
            self.update_status_table()
        except Exception:
            pass

    def update_status_table(self) -> None:
        try:
            table = self.query_one("#status_table", DataTable)
        except Exception:
            return
        
        table.clear()
        for node_id, data in sorted(self.heartbeat_data.items()):
            workers = data.get("workers", {})
            w_str = f"{workers.get('scrape',0)}/{workers.get('details',0)}/{workers.get('enrichment',0)}"
            lm = data.get("last_modified")
            lm_str = lm.strftime("%m-%d %H:%M") if lm else "N/A"
            table.add_row(node_id, w_str, lm_str, key=node_id)

    async def action_prune_heartbeat(self) -> None:
        """Deletes the selected heartbeat from S3 status/."""
        table = self.query_one("#status_table", DataTable)
        if table.cursor_row is None:
            return
        
        node_id = table.get_row_at(table.cursor_row)[0]
        if not node_id:
            return

        from cocli.core.config import get_campaign, load_campaign_config
        from cocli.core.reporting import get_boto3_session
        
        campaign = get_campaign()
        if not campaign:
            return
        
        try:
            config = load_campaign_config(campaign)
            bucket = config.get("aws", {}).get("data_bucket_name")
            if not bucket:
                return
            
            def _delete_status() -> None:
                session = get_boto3_session(config)
                s3 = session.client("s3")
                key = f"status/{node_id}.json"
                s3.delete_object(Bucket=bucket, Key=key)
            
            await asyncio.to_thread(_delete_status)
            await self._refresh_s3_status()
            self.notify(f"Pruned heartbeat for {node_id} from S3.")
        except Exception as e:
            self.notify(f"Failed to prune heartbeat: {e}", severity="error")

    def update_registry_table(self) -> None:
        try:
            table = self.query_one("#registry_table", DataTable)
        except Exception:
            return
        
        table.clear()
        for node_id, data in sorted(self.registry_data.items()):
            ts = data.get("timestamp", 0)
            ts_str = datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d %H:%M")
            table.add_row(node_id, data.get("ip", "N/A"), ts_str, key=node_id)

    def update_table(self) -> None:
        try:
            table = self.query_one("#cluster_table", DataTable)
        except Exception:
            # Table not mounted yet
            return
            
        table.clear()
        
        if not bridge or not bridge.heartbeats:
            # Add a placeholder if no nodes seen
            return

        now = datetime.now(UTC)
        
        for node_id, hb in sorted(bridge.heartbeats.items()):
            # Calculate freshness
            ts_str = hb.get("timestamp", "")
            freshness = "Unknown"
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    diff = (now - ts).total_seconds()
                    if diff < 15:
                        freshness = "[bold green]LIVE[/bold green]"
                    else:
                        freshness = f"[yellow]{int(diff)}s ago[/yellow]"
                except Exception:
                    pass

            table.add_row(
                node_id,
                f"{hb.get('load_avg', 0.0):.2f}",
                f"{hb.get('memory_percent', 0.0):.1f}%",
                str(hb.get("worker_count", 0)),
                str(hb.get("active_tasks", 0)),
                freshness
            )
        
        self.query_one("#cluster_last_updated", Label).update(f"Updated: {now.strftime('%H:%M:%S')}")

    def action_refresh_cluster(self) -> None:
        self.update_table()
        self.run_worker(self._refresh_registry())

    async def action_delete_node(self) -> None:
        """Deletes the selected node from the S3 registry."""
        table = self.query_one("#registry_table", DataTable)
        if table.cursor_row is None:
            return
        
        node_id = table.get_row_at(table.cursor_row)[0]
        if not node_id:
            return

        from cocli.core.config import get_campaign, load_campaign_config
        from cocli.core.reporting import get_boto3_session
        
        campaign = get_campaign()
        if not campaign:
            return
        
        try:
            config = load_campaign_config(campaign)
            bucket = config.get("aws", {}).get("data_bucket_name")
            if not bucket:
                return
            
            def _delete_s3() -> None:
                session = get_boto3_session(config)
                s3 = session.client("s3")
                key = f"cluster/registry/{node_id}.json"
                s3.delete_object(Bucket=bucket, Key=key)
            
            await asyncio.to_thread(_delete_s3)
            await self._refresh_registry()
            self.notify(f"Deleted node {node_id} from S3 registry.")
        except Exception as e:
            self.notify(f"Failed to delete node: {e}", severity="error")
