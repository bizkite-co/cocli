import time
import socket
import logging
import threading
import os
from pathlib import Path
from typing import Dict, Any, Optional
from zeroconf import Zeroconf, ServiceInfo, ServiceBrowser, ServiceListener
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from .wal import get_node_id
from ..models.wal.record import DatagramRecord, RS, QueueDatagram, HeartbeatDatagram, ConfigDatagram
from .paths import paths

logger = logging.getLogger(__name__)

GOSSIP_PORT = 9999
SERVICE_TYPE = "_cocli-gossip._udp.local."

class GossipListener(ServiceListener):
    def __init__(self, bridge: "GossipBridge") -> None:
        self.bridge = bridge

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        if info:
            # address = socket.inet_ntoa(info.addresses[0]) # addresses is bytes
            import ipaddress
            address = str(ipaddress.ip_address(info.addresses[0]))
            
            node_id_bytes = info.properties.get(b"node_id", b"unknown")
            node_id = node_id_bytes.decode("utf-8") if node_id_bytes else "unknown"
            if node_id != self.bridge.node_id:
                logger.info(f"Discovered peer: {node_id} at {address}")
                self.bridge.peers[node_id] = address

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        pass

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        pass

class WalEventHandler(FileSystemEventHandler):
    def __init__(self, bridge: "GossipBridge") -> None:
        self.bridge = bridge

    def on_modified(self, event: Any) -> None:
        # Only broadcast .usv files in the root WAL directory
        if not event.is_directory and str(event.src_path).endswith(".usv"):
            # A WAL file was modified, broadcast the new records
            self.bridge.broadcast_file(Path(event.src_path))

    def on_created(self, event: Any) -> None:
        if not event.is_directory and str(event.src_path).endswith(".usv"):
            self.bridge.broadcast_file(Path(event.src_path))

class GossipBridge:
    def __init__(self) -> None:
        self.wal_dir = paths.wal
        self.node_id = get_node_id()
        self.zeroconf: Optional[Zeroconf] = None
        self.browser: Optional[ServiceBrowser] = None
        self.peers: Dict[str, str] = {} # node_id -> ip_address
        self.running = False
        self.sock: Optional[socket.socket] = None
        self.observer = Observer()
        self.handler = WalEventHandler(self)
        
        # Persistent offsets to survive restarts
        self.offset_file = self.wal_dir / ".gossip_offsets.json"
        self._sent_offsets: Dict[str, int] = self._load_offsets()
        
        # Real-time cluster status
        self.heartbeats: Dict[str, Dict[str, Any]] = {}

    def _load_offsets(self) -> Dict[str, int]:
        if self.offset_file.exists():
            try:
                import json
                with open(self.offset_file, "r") as f:
                    from typing import cast
                    return cast(Dict[str, int], json.load(f))
            except Exception:
                pass
        return {}

    def _save_offsets(self) -> None:
        try:
            import json
            with open(self.offset_file, "w") as f:
                json.dump(self._sent_offsets, f)
        except Exception:
            pass

    def broadcast_file(self, wal_path: Path) -> None:
        """Reads new records from a WAL file and sends them to all known peers via Unicast."""
        if not self.sock or not self.peers:
            return
        
        # 1. Freshness Check: Only gossip today's journals
        from datetime import datetime
        today_prefix = datetime.now().strftime("%Y%m%d")
        if not wal_path.name.startswith(today_prefix):
            return

        # 2. Loop Prevention: Don't broadcast remote files
        if wal_path.name.startswith("remote_"):
            return

        try:
            offset = self._sent_offsets.get(str(wal_path), 0)
            file_size = wal_path.stat().st_size
            
            if file_size <= offset:
                return

            with open(wal_path, "r") as f:
                f.seek(offset)
                new_data = f.read()
                
            # Split into individual records
            records = [r + RS for r in new_data.split(RS) if r.strip()]
            if not records:
                # Update offset even if no records to avoid re-reading empty space
                self._sent_offsets[str(wal_path)] = file_size
                return

            # Rate Limit: Only send up to 50 records per cycle
            send_limit = 50
            sent_count = 0
            bytes_sent = 0
            for msg in records[:send_limit]:
                self.broadcast_msg(msg)
                sent_count += 1
                bytes_sent += len(msg)
            
            # Update offset precisely based on how many records we actually sent
            self._sent_offsets[str(wal_path)] = offset + bytes_sent
            self._save_offsets()
            
            if len(records) > send_limit:
                logger.debug(f"Rate limited {wal_path}: sent {send_limit}/{len(records)} records")
        except Exception as e:
            logger.error(f"Error broadcasting {wal_path}: {e}")

    def broadcast_msg(self, msg: str) -> None:
        """Sends a raw message to all known peers via Unicast UDP."""
        if not self.sock or not self.peers:
            return
            
        data = msg.encode('utf-8')
        for node_id, ip in list(self.peers.items()):
            try:
                self.sock.sendto(data, (ip, GOSSIP_PORT))
                logger.info(f"Broadcasted gossip msg ({msg[0]}) to {node_id} ({ip})")
            except Exception as send_err:
                logger.warning(f"Failed to send to {node_id} at {ip}: {send_err}")

    def _listen_loop(self) -> None:
        """Background thread to receive unicast gossip."""
        if not self.sock:
            return
        while self.running:
            try:
                self.sock.settimeout(1.0)
                data, addr = self.sock.recvfrom(65535)
                msg = data.decode('utf-8')
                logger.info(f"RAW GOSSIP RECEIVED from {addr}: {msg[:50]}...")
                self.handle_gossip(msg, addr)

            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"Gossip listen error: {e}")

    def handle_gossip(self, msg: str, addr: tuple[str, int]) -> None:
        """Processes an incoming USV datagram and writes it locally via paths authority."""
        try:
            sender_ip = addr[0]
            
            # 0. Self-Learning Discovery: Add unknown peers from our subnet
            if sender_ip.startswith("10.0.0.") and sender_ip not in self.peers.values():
                # We don't have a hostname, so we use a synthetic node_id
                node_hint = f"discovered_{sender_ip.split('.')[-1]}"
                self.peers[node_hint] = sender_ip
                logger.info(f"Learned new gossip peer: {node_hint} at {sender_ip}")

            # 1. Handle Queue Synchronization
            if msg.startswith("Q"):
                q_record = QueueDatagram.from_usv(msg)
                if not q_record or q_record.node_id == self.node_id:
                    return
                
                logger.info(f"Received queue sync: {q_record.queue_name}/{q_record.task_id} [{q_record.status}] from {q_record.node_id}")
                
                from .config import get_campaign
                campaign = get_campaign()
                if not campaign:
                    return
                
                # Write marker to local filesystem
                queue = paths.campaign(campaign).queue(q_record.queue_name)
                if q_record.status == "completed":
                    dest = queue.completed / "results" / f"{q_record.task_id}.json"
                else:
                    dest = queue.path / q_record.status / f"{q_record.task_id}.json"
                
                if not dest.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    import json
                    with open(dest, "w") as f:
                        json.dump({
                            "id": q_record.task_id, 
                            "status": q_record.status, 
                            "synced_via": "gossip", 
                            "remote_node": q_record.node_id,
                            "timestamp": q_record.timestamp
                        }, f)
                return

            # 2. Handle Heartbeats
            if msg.startswith("H"):
                h_record = HeartbeatDatagram.from_usv(msg)
                if not h_record or h_record.node_id == self.node_id:
                    return
                
                # Update in-memory status
                self.heartbeats[h_record.node_id] = h_record.model_dump()
                logger.info(f"Received heartbeat from {h_record.node_id}: Load {h_record.load_avg:.2f}")
                return

            # 3. Handle Configuration Updates
            if msg.startswith("C"):
                c_record = ConfigDatagram.from_usv(msg)
                if not c_record:
                    return
                
                # Ignore if not for us (and not a broadcast)
                if c_record.node_id != self.node_id and c_record.node_id != "*":
                    return
                
                logger.info("Received remote config update from gossip.")
                
                # Save update to a dedicated location for WorkerService to pick up
                update_path = paths.root / "remote_updates" / f"config_{int(time.time())}.json"
                update_path.parent.mkdir(parents=True, exist_ok=True)
                with open(update_path, "w") as f:
                    f.write(c_record.config_json)
                return

            # 4. Handle standard WAL Records
            record = DatagramRecord.from_usv(msg)
            if record.node_id == self.node_id:
                return # Ignore self
            
            logger.info(f"Received gossip for {record.target}.{record.field} from {record.node_id}")
            
            # Save received updates in a remote-node specific file via paths authority
            remote_wal = paths.wal_remote_journal(record.node_id)
            
            # Ensure WAL dir exists (path authority doesn't create it automatically on path return)
            remote_wal.parent.mkdir(parents=True, exist_ok=True)
            
            with open(remote_wal, "a") as f:
                f.write(msg)
                
        except Exception as e:
            logger.error(f"Failed to handle gossip: {e}")

    def start(self) -> None:
        if self.running:
            return
            
        try:
            # Setup Unicast UDP Socket
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(('0.0.0.0', GOSSIP_PORT))
        except Exception as e:
            logger.error(f"Gossip Bridge failed to initialize socket: {e}")
            return

        self.running = True
        
        # 1. Discover Peers from Config
        self.discover_peers()

        # 2. Send immediate 'hello' heartbeat to announce ourselves to all peers
        try:
            from datetime import datetime, UTC
            from ..models.wal.record import HeartbeatDatagram
            hello = HeartbeatDatagram(
                node_id=self.node_id,
                timestamp=datetime.now(UTC).isoformat(),
                load_avg=0.0,
                memory_percent=0.0,
                worker_count=0,
                active_tasks=0
            )
            self.broadcast_msg(hello.to_usv())
            logger.info("Proactive 'hello' heartbeat broadcasted to announce node.")
        except Exception as e:
            logger.debug(f"Proactive hello skipped: {e}")

        # 3. Start Gossip Listener
        self.listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.listener_thread.start()

        # 4. Register ourselves in S3
        self.register_self()
        
        # 5. Start File Observer on the centralized WAL directory
        if self.wal_dir.exists():
            try:
                self.observer.schedule(self.handler, str(self.wal_dir), recursive=False)
                self.observer.start()
                
                # One-time startup catch-up for today's journals
                from datetime import datetime
                today_prefix = datetime.now().strftime("%Y%m%d")
                logger.info(f"Startup catch-up: Scanning for today's journals ({today_prefix}*)...")
                for wal_file in self.wal_dir.glob(f"{today_prefix}*.usv"):
                    self.broadcast_file(wal_file)
                
            except Exception as e:
                logger.error(f"Gossip Bridge failed to start observer: {e}")

        # Register mDNS & Start Browser
        try:
            self.zeroconf = Zeroconf()
            local_ip = "0.0.0.0"
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(('8.8.8.8', 1))
                local_ip = s.getsockname()[0]
                s.close()
            except Exception:
                pass

            info = ServiceInfo(
                SERVICE_TYPE,
                f"{self.node_id}.{SERVICE_TYPE}",
                addresses=[socket.inet_aton(local_ip)],
                port=GOSSIP_PORT,
                properties={"node_id": self.node_id}
            )
            self.zeroconf.register_service(info)
            self.browser = ServiceBrowser(self.zeroconf, SERVICE_TYPE, GossipListener(self))
        except Exception as e:
            logger.warning(f"mDNS setup failed: {e}")
            
        logger.info(f"Gossip Bridge (Unicast) started on node {self.node_id}")

    def discover_peers(self) -> None:
        """Populates the peers list from S3 registry and campaign config."""
        # 1. S3 Registry Discovery (Primary)
        try:
            from .config import load_campaign_config, get_campaign
            from .reporting import get_boto3_session
            campaign_name = os.getenv("CAMPAIGN_NAME") or get_campaign()
            if campaign_name:
                config = load_campaign_config(campaign_name)
                bucket = config.get("aws", {}).get("data_bucket_name")
                if bucket:
                    # Use IoT profile if available, else default
                    profile = f"{campaign_name}-iot" if os.path.exists("/home/mstouffer/.cocli/iot/get_tokens.sh") else None
                    session = get_boto3_session(config, profile_name=profile)
                    s3 = session.client("s3")

                    prefix = "cluster/registry/"
                    response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)

                    for obj in response.get("Contents", []):
                        key = obj["Key"]
                        if not key.endswith(".json"):
                            continue

                        peer_id = key.replace(prefix, "").replace(".json", "")
                        if peer_id == self.node_id:
                            continue

                        # Fetch IP from small JSON file
                        data_resp = s3.get_object(Bucket=bucket, Key=key)
                        import json
                        peer_data = json.loads(data_resp["Body"].read().decode("utf-8"))
                        ip = peer_data.get("ip")
                        if ip:
                            self.peers[peer_id] = ip
                            logger.info(f"S3-discovered peer: {peer_id} at {ip}")
        except Exception as e:
            logger.debug(f"S3 peer discovery skipped: {e}")

        # 2. Static Config Fallback
        try:
            from .config import load_campaign_config, get_campaign
            campaign_name = os.getenv("CAMPAIGN_NAME") or get_campaign()
            if campaign_name:
                config = load_campaign_config(campaign_name)
                scaling = config.get("prospecting", {}).get("scaling", {})
                for host_key in scaling.keys():
                    if host_key == "fargate" or host_key == self.node_id or host_key in self.peers:
                        continue

                    # Resolve IP
                    peer_ips = []
                    if host_key == "laptop":
                        peer_ips = ["10.0.0.4"]
                    else:
                        for suffix in [".pi", ".local", ""]:
                            try:
                                ip = socket.gethostbyname(host_key + suffix)
                                if ip and ip != "127.0.0.1":
                                    peer_ips.append(ip)
                            except socket.gaierror:
                                continue

                    if peer_ips:
                        self.peers[host_key] = peer_ips[0]
                        logger.info(f"Config-discovered peer: {host_key} at {peer_ips[0]}")
        except Exception as e:
            logger.debug(f"Static peer discovery failed: {e}")

    def register_self(self) -> None:
        """Registers the local IP in the S3 cluster registry."""
        try:
            from .config import load_campaign_config, get_campaign
            from .reporting import get_boto3_session
            import json

            campaign_name = os.getenv("CAMPAIGN_NAME") or get_campaign()
            if not campaign_name:
                return

            config = load_campaign_config(campaign_name)
            bucket = config.get("aws", {}).get("data_bucket_name")
            if not bucket:
                return

            # Determine local IP
            local_ip = "0.0.0.0"
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(('8.8.8.8', 1))
                local_ip = s.getsockname()[0]
                s.close()
            except Exception:
                pass

            if local_ip == "0.0.0.0":
                return

            # Use IoT profile if available, else default
            profile = f"{campaign_name}-iot" if os.path.exists("/home/mstouffer/.cocli/iot/get_tokens.sh") else None
            session = get_boto3_session(config, profile_name=profile)
            s3 = session.client("s3")

            key = f"cluster/registry/{self.node_id}.json"
            payload = json.dumps({"ip": local_ip, "timestamp": time.time()})
            s3.put_object(Bucket=bucket, Key=key, Body=payload)
            logger.info(f"Registered node {self.node_id} at {local_ip} in S3 registry.")
        except Exception as e:
            logger.warning(f"Failed to register node in S3: {e}")


    def stop(self) -> None:
        self.running = False
        if self.observer.is_alive():
            self.observer.stop()
            self.observer.join()
        if self.zeroconf:
            try:
                self.zeroconf.unregister_all_services()
                self.zeroconf.close()
            except Exception:
                pass
        if self.sock:
            self.sock.close()

# Authoritative Global Instance
bridge = GossipBridge()

if __name__ == "__main__":
    # Standalone test mode
    logging.basicConfig(level=logging.INFO)
    bridge = GossipBridge()
    bridge.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        bridge.stop()
