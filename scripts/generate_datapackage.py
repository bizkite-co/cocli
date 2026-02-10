import sys
from cocli.models.google_maps_prospect import GoogleMapsProspect

def generate_datapackage(campaign_name: str):
    print(f"Generating datapackage.json for {campaign_name} using GoogleMapsProspect model...")
    try:
        path = GoogleMapsProspect.write_datapackage(campaign_name)
        print(f"Success! Saved to {path}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    campaign = sys.argv[1] if len(sys.argv) > 1 else "roadmap"
    generate_datapackage(campaign)