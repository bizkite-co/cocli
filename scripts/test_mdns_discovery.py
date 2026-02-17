import socket
import logging
from zeroconf import ServiceBrowser, ServiceListener, Zeroconf, ServiceInfo

class CocliListener(ServiceListener):
    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        print(f"Service {name} updated")

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        print(f"Service {name} removed")

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        if info:
            addresses = [socket.inet_ntoa(addr) for addr in info.addresses]
            print(f"Service {name} added, service info: {info}")
            print(f"  Addresses: {', '.join(addresses)}")
            print(f"  Port: {info.port}")
            print(f"  Properties: {info.properties}")

def main() -> None:
    logging.basicConfig(level=logging.INFO)
    zeroconf = Zeroconf()
    
    # Register our own service for others to find
    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(f"{hostname}.local")
    except socket.gaierror:
        # Fallback if .local doesn't resolve locally
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # doesn't even have to be reachable
            s.connect(('10.255.255.255', 1))
            local_ip = s.getsockname()[0]
        except Exception:
            local_ip = '127.0.0.1'
        finally:
            s.close()

    print(f"Registering service for {hostname} at {local_ip}...")
    
    info = ServiceInfo(
        "_cocli._tcp.local.",
        f"{hostname}._cocli._tcp.local.",
        addresses=[socket.inet_aton(local_ip)],
        port=8000,
        properties={"version": "0.1.0", "node_id": hostname},
        server=f"{hostname}.local.",
    )
    
    zeroconf.register_service(info)
    
    print("Browsing for cocli services (Press Ctrl+C to exit)...")
    listener = CocliListener()
    _browser = ServiceBrowser(zeroconf, "_cocli._tcp.local.", listener)
    
    try:
        while True:
            pass
    except KeyboardInterrupt:
        pass
    finally:
        print("\nUnregistering...")
        zeroconf.unregister_service(info)
        zeroconf.close()

if __name__ == "__main__":
    main()
