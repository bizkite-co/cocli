import time
import socket
import logging
import threading
from pathlib import Path
from typing import Dict, Any
from zeroconf import Zeroconf, ServiceInfo
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from .wal import DatagramRecord, get_node_id, RS
from .config import get_companies_dir

logger = logging.getLogger(__name__)

GOSSIP_PORT = 9999
MCAST_GRP = '224.1.1.1'
SERVICE_TYPE = "_cocli_gossip._udp.local."

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
        self.zeroconf = Zeroconf()
        self.running = False
        self._sent_offsets: Dict[str, int] = {} # track how much of each file we've sent
        
        # Setup UDP Multicast Socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.sock.bind(('', GOSSIP_PORT))
        except OSError:
            # Fallback if port is busy
            self.sock.bind(('0.0.0.0', GOSSIP_PORT))
        
        mreq = socket.inet_aton(MCAST_GRP) + socket.inet_aton('0.0.0.0')
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        
        self.observer = Observer()
        self.handler = WalEventHandler(self)

    def broadcast_file(self, wal_path: Path) -> None:
        """Reads new records from a WAL file and sends them."""
        try:
            offset = self._sent_offsets.get(str(wal_path), 0)
            file_size = wal_path.stat().st_size
            
            if file_size <= offset:
                return

            with open(wal_path, "r") as f:
                f.seek(offset)
                new_data = f.read()
                
            self._sent_offsets[str(wal_path)] = file_size
            
            # Split into individual records and broadcast
            for record_str in new_data.split(RS):
                if record_str.strip():
                    full_msg = record_str + RS
                    self.sock.sendto(full_msg.encode('utf-8'), (MCAST_GRP, GOSSIP_PORT))
                    logger.debug(f"Broadcasted record from {wal_path}")
        except Exception as e:
            logger.error(f"Error broadcasting {wal_path}: {e}")

    def _listen_loop(self) -> None:
        """Background thread to receive gossip."""
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
                # We might not have this company yet. In a full IPFS/distributed system 
                # we'd fetch it. For now, we only update what we have.
                logger.debug(f"Received update for unknown company {record.target}, ignoring.")
                return

            updates_dir = company_dir / "updates"
            updates_dir.mkdir(parents=True, exist_ok=True)
            
            # Save received updates in a separate file to prevent broadcast loops
            # if the observer is also watching this file.
            remote_wal = updates_dir / f"remote_{record.node_id}.usv"
            
            # Note: Writing to this file MIGHT trigger our own observer if we aren't careful.
            # However, broadcast_file ignores self-node records based on node_id check.
            with open(remote_wal, "a") as f:
                f.write(msg)
                
        except Exception as e:
            logger.error(f"Failed to handle gossip: {e}")

    def start(self) -> None:
        self.running = True
        
        # Start Gossip Listener
        self.listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.listener_thread.start()
        
        # Start File Observer
        # We watch the entire companies directory for changes in 'updates' folders
        if self.companies_dir.exists():
            self.observer.schedule(self.handler, str(self.companies_dir), recursive=True)
            self.observer.start()
        
        # Register mDNS
        try:
            info = ServiceInfo(
                SERVICE_TYPE,
                f"{self.node_id}.{SERVICE_TYPE}",
                addresses=[socket.inet_aton("0.0.0.0")],
                port=GOSSIP_PORT,
                properties={"node_id": self.node_id}
            )
            self.zeroconf.register_service(info)
        except Exception as e:
            logger.warning(f"mDNS registration failed: {e}")
            
        logger.info(f"Gossip Bridge started on node {self.node_id}")

    def stop(self) -> None:
        self.running = False
        if self.observer.is_alive():
            self.observer.stop()
            self.observer.join()
        self.zeroconf.unregister_all_services()
        self.zeroconf.close()
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
