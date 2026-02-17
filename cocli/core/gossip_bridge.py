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

from .wal import DatagramRecord, get_node_id, RS
from .config import get_companies_dir

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
        if not event.is_directory and str(event.src_path).endswith(".usv"):
            # A WAL file was modified, broadcast the new records
            self.bridge.broadcast_file(Path(event.src_path))

    def on_created(self, event: Any) -> None:
        if not event.is_directory and str(event.src_path).endswith(".usv"):
            self.bridge.broadcast_file(Path(event.src_path))

class GossipBridge:
    def __init__(self) -> None:
        self.companies_dir = get_companies_dir()
        self.node_id = get_node_id()
        self.zeroconf: Optional[Zeroconf] = None
        self.browser: Optional[ServiceBrowser] = None
        self.peers: Dict[str, str] = {} # node_id -> ip_address
        self.running = False
        self._sent_offsets: Dict[str, int] = {} # track how much of each file we've sent
        self.sock: Optional[socket.socket] = None
        self.observer = Observer()
        self.handler = WalEventHandler(self)

    def broadcast_file(self, wal_path: Path) -> None:
        """Reads new records from a WAL file and sends them to all known peers via Unicast."""
        if not self.sock or not self.peers:
            return
        try:
            offset = self._sent_offsets.get(str(wal_path), 0)
            file_size = wal_path.stat().st_size
            
            if file_size <= offset:
                return

            with open(wal_path, "r") as f:
                f.seek(offset)
                new_data = f.read()
                
            self._sent_offsets[str(wal_path)] = file_size
            
            # Split into individual records
            records = [r + RS for r in new_data.split(RS) if r.strip()]
            if not records:
                return

            for node_id, ip in list(self.peers.items()):
                for msg in records:
                    try:
                        self.sock.sendto(msg.encode('utf-8'), (ip, GOSSIP_PORT))
                        logger.debug(f"Sent record to {node_id} ({ip})")
                    except Exception as send_err:
                        logger.warning(f"Failed to send to {node_id} at {ip}: {send_err}")
        except Exception as e:
            logger.error(f"Error broadcasting {wal_path}: {e}")

    def _listen_loop(self) -> None:
        """Background thread to receive unicast gossip."""
        if not self.sock:
            return
        while self.running:
            try:
                self.sock.settimeout(1.0)
                data, addr = self.sock.recvfrom(1024 * 64)
                msg = data.decode('utf-8')
                self.handle_gossip(msg)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"Gossip listen error: {e}")

    def handle_gossip(self, msg: str) -> None:
        """Processes an incoming USV datagram and writes it locally."""
        try:
            record = DatagramRecord.from_usv(msg)
            if record.node_id == self.node_id:
                return # Ignore self
            
            logger.info(f"Received gossip for {record.target}.{record.field} from {record.node_id}")
            
            # Write this record to our local WAL for this company
            company_dir = self.companies_dir / record.target
            if not company_dir.exists():
                logger.debug(f"Received update for unknown company {record.target}, ignoring.")
                return

            updates_dir = company_dir / "updates"
            updates_dir.mkdir(parents=True, exist_ok=True)
            
            # Save received updates in a separate file to prevent broadcast loops
            remote_wal = updates_dir / f"remote_{record.node_id}.usv"
            
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
        
        # Start Gossip Listener
        self.listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.listener_thread.start()
        
        # Start File Observer (NON-RECURSIVE on root to avoid spam)
        if self.companies_dir.exists():
            try:
                self.observer.schedule(self.handler, str(self.companies_dir), recursive=False)
                self.observer.start()
                
                # Background WAL Scanner for nested updates/ directories
                def _scan_wal_loop() -> None:
                    while self.running:
                        try:
                            # Periodic scan of all updates/*.usv
                            for wal_file in self.companies_dir.glob("*/updates/*.usv"):
                                self.broadcast_file(wal_file)
                        except Exception as e:
                            logger.error(f"WAL scanner error: {e}")
                        time.sleep(30) # Scan every 30 seconds
                
                self.scanner_thread = threading.Thread(target=_scan_wal_loop, daemon=True)
                self.scanner_thread.start()
                
            except Exception as e:
                logger.error(f"Gossip Bridge failed to start observer: {e}")
        
        # Static Peer Discovery from Config (Robust Fallback)
        try:
            from .config import load_campaign_config, get_campaign
            
            # HARDCODED CLUSTER DEFAULTS (The ultimate fallback)
            for ip in ["10.0.0.12", "10.0.0.17", "10.0.0.16", "10.0.0.200"]:
                self.peers[f"hardcoded_{ip.split('.')[-1]}"] = ip

            campaign_name = os.getenv("CAMPAIGN_NAME") or get_campaign()
            if campaign_name:
                config = load_campaign_config(campaign_name)
                scaling = config.get("prospecting", {}).get("scaling", {})
                for host_key in scaling.keys():
                    if host_key == "fargate" or host_key == self.node_id:
                        continue
                    
                    # Resolve IP
                    # Try a few common ways to resolve
                    peer_ips = []
                    for suffix in [".pi", ".local", ""]:
                        peer_host = host_key + suffix
                        try:
                            ip = socket.gethostbyname(peer_host)
                            if ip and ip != "127.0.0.1":
                                peer_ips.append(ip)
                                break
                        except Exception:
                            continue
                    
                    if peer_ips:
                        peer_ip = peer_ips[0]
                        logger.info(f"Config-discovered peer: {host_key} at {peer_ip}")
                        self.peers[host_key] = peer_ip
                    else:
                        logger.debug(f"Could not resolve static peer {host_key}")
                
                # FINAL FALLBACK: Active Subnet Scan (last resort)
                if not self.peers:
                    logger.info("Static discovery failed. Attempting active subnet scan for peers...")
                    def _active_scan() -> None:
                        # We only scan if we have NO peers
                        import subprocess
                        # PI common range is 10.0.0.x
                        for i in range(2, 254):
                            if not self.running or self.peers:
                                break
                            ip = f"10.0.0.{i}"
                            # Very fast ping check
                            try:
                                res = subprocess.run(["ping", "-c", "1", "-W", "0.1", ip], capture_output=True)
                                if res.returncode == 0:
                                    # If it pings, we add it as a potential peer. 
                                    # UDP doesn't care if they aren't listening.
                                    self.peers[f"scanned_{i}"] = ip
                            except Exception:
                                pass
                    
                    # Run scan in a one-off thread
                    threading.Thread(target=_active_scan, daemon=True).start()

        except Exception as e:
            logger.warning(f"Static peer discovery failed: {e}")

        # Register mDNS & Start Browser
        try:
            self.zeroconf = Zeroconf()
            
            # Use 0.0.0.0 if specific IP resolution is tricky, 
            # zeroconf usually handles interface selection.
            # But let's try to get a real one first.
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
