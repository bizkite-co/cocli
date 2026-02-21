from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect

def print_fields() -> None:
    fields = list(GoogleMapsProspect.model_fields.keys())
    for i, f in enumerate(fields):
        print(f"{i}: {f}")

if __name__ == "__main__":
    print_fields()
