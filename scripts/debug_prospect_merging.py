from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
from cocli.models.campaigns.indexes.google_maps_raw import GoogleMapsRawResult

def test_merging() -> None:
    print("--- Testing Prospect Merging ---")
    
    # 1. Existing prospect with GOOD data
    raw_existing = GoogleMapsRawResult(
        Place_ID="ChIJ1234567890123456789",
        Name="Old Name",
        Phone_1="(305) 555-1212",
        Website="https://old.com",
        Reviews_count=100,
        Average_rating=4.5
    )
    existing = GoogleMapsProspect.from_raw(raw_existing)
    
    # 2. Newly scraped prospect with SOME data and SOME nulls
    raw_new = GoogleMapsRawResult(
        Place_ID="ChIJ1234567890123456789",
        Name="New Name",
        Phone_1="", # Should NOT overwrite
        Website="", # Should NOT overwrite
        Reviews_count=150, # Should overwrite
        Average_rating=0 # Should NOT overwrite (interpreted as None/Empty in merge logic if we tighten it)
    )
    new_scraped = GoogleMapsProspect.from_raw(raw_new)
    # Force some nulls for the test
    new_scraped.average_rating = None
    
    merged = new_scraped.merge_with_existing(existing)
    
    print(f"Merged Name: {merged.name} (Expected: New Name)")
    print(f"Merged Phone: {merged.phone} (Expected: 13055551212)")
    print(f"Merged Website: {merged.website} (Expected: https://old.com)")
    print(f"Merged Reviews: {merged.reviews_count} (Expected: 150)")
    print(f"Merged Rating: {merged.average_rating} (Expected: 4.5)")
    
    assert merged.name == "New Name"
    assert str(merged.phone) == "13055551212"
    assert merged.website == "https://old.com"
    assert merged.reviews_count == 150
    assert merged.average_rating == 4.5
    
    print("\n[SUCCESS] Non-destructive merging verified.")

if __name__ == "__main__":
    test_merging()
