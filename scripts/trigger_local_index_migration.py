from cocli.core.website_domain_csv_manager import WebsiteDomainCsvManager

def migrate() -> None:
    print("Initializing WebsiteDomainCsvManager...")
    manager = WebsiteDomainCsvManager()
    
    print("Saving to optimized sharded index...")
    manager.save()
    
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
