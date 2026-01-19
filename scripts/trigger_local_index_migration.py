from cocli.core.website_domain_csv_manager import WebsiteDomainCsvManager
import os

def migrate() -> None:
    print("Initializing WebsiteDomainCsvManager...")
    manager = WebsiteDomainCsvManager()
    
    print(f"Index file: {manager.csv_file}")
    print(f"Loaded {len(manager.data)} domains.")
    
    print("Saving to domains_master.csv (optimized)...")
    manager.save()
    
    if os.path.exists(manager.csv_file):
        size = os.path.getsize(manager.csv_file)
        print(f"New domains_master.csv size: {size} bytes")

if __name__ == "__main__":
    migrate()
