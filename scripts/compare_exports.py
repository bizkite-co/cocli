import csv
from pathlib import Path

old_file = Path("/home/mstouffer/.local/share/cocli_data/campaigns/roadmap/exports/20260217_1626_email_clients.usv")
new_file = Path("/home/mstouffer/.local/share/cocli_data/campaigns/roadmap/exports/enriched_emails_roadmap.usv")

def get_domains(file_path: Path, check_emails: bool = False) -> set[str]:
    domains: set[str] = set()
    if not file_path.exists():
        return domains
        
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\x1f')
        for row in reader:
            domain = row.get('domain')
            if domain:
                if check_emails:
                    if row.get('emails') and row['emails'].strip():
                        domains.add(domain.lower().strip())
                else:
                    domains.add(domain.lower().strip())
    return domains

old_domains = get_domains(old_file)
new_domains = get_domains(new_file, check_emails=True)

missing = old_domains - new_domains
print(f"Old Domains count: {len(old_domains)}")
print(f"New Domains (with emails) count: {len(new_domains)}")
print(f"Count of domains in old but missing in new: {len(missing)}")

if missing:
    print("\nSample missing domains:")
    for d in sorted(list(missing))[:10]:
        print(f"  - {d}")
