import json
import csv
from pathlib import Path

from cocli.core.config import get_campaign_exports_dir

base_dir = Path("data/campaigns/turboship/indexes/emails")
output_file = get_campaign_exports_dir("turboship") / "anomalous_emails.csv"

def is_anomalous(email: str) -> bool:
    # Standard common domains
    standard_tlds = {".com", ".net", ".org", ".edu", ".gov", ".io", ".biz", ".info", ".us", ".me"}
    email_lower = email.lower()
    
    # Check for image/resource extensions
    junk_extensions = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".js", ".css", ".pdf"}
    if any(email_lower.endswith(ext) for ext in junk_extensions):
        return True
        
    # Check for missing typical TLD
    if not any(email_lower.endswith(tld) for tld in standard_tlds):
        # Could be a country code or something else, but let's flag it if it looks weird
        if "." not in email.split("@")[-1]:
            return True
            
    return False

anomalies = []

if base_dir.exists():
    for domain_dir in base_dir.iterdir():
        if domain_dir.is_dir():
            for json_file in domain_dir.glob("*.json"):
                try:
                    with open(json_file, 'r') as f:
                        data = json.load(f)
                        email = data.get("email", "")
                        if is_anomalous(email):
                            anomalies.append({
                                "email": email,
                                "path": str(json_file),
                                "source": data.get("source"),
                                "domain": data.get("domain")
                            })
                except Exception as e:
                    print(f"Error reading {json_file}: {e}")

with open(output_file, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=["email", "path", "source", "domain"])
    writer.writeheader()
    writer.writerows(anomalies)

print(f"Found {len(anomalies)} anomalous emails. Saved to {output_file}")
