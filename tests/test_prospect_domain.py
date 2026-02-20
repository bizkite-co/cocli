
from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
from cocli.core.utils import UNIT_SEP

def test_prospect_domain_extraction():
    # Example line with website but no domain
    # Column order check from model:
    # 0: place_id, 1: company_slug, 2: name, 3: phone, 4: created_at, 5: updated_at, 6: version, 
    # 7: processed_by, 8: company_hash, 9: keyword, 10: full_address, 11: street_address, 
    # 12: city, 13: zip, 14: municipality, 15: state, 16: country, 17: timezone, 
    # 18: phone_standard_format, 19: website, 20: domain ...
    
    parts = [""] * 60
    parts[0] = "ChIJ-QOEhLWw6IgRSRs6Nkt2fPM"
    parts[1] = "test-company"
    parts[2] = "Test Company"
    parts[19] = "https://www.example.com/page?query=1"
    parts[20] = "" # Domain is empty in USV
    
    usv_line = UNIT_SEP.join(parts)
    
    prospect = GoogleMapsProspect.from_usv(usv_line)
    
    assert prospect.website == "https://www.example.com/page?query=1"
    # This might fail if the validator isn't there yet
    assert prospect.domain == "example.com"

def test_prospect_from_checkpoint_line():
    # Real line from the checkpoint (shortened for test)
    raw = 'ChIJ05olcAbVTYYRK3_zk8ZWOTk^_pinnacle-wealth-partners^_Pinnacle Wealth Partners^_18173304755^_2026-02-13T19:39:33.137729+00:00^_2026-02-13T11:39:36.339391^_1^_cocli5x1^_pinnacle-none-00000^_^_905 OLD GLADE RD, Colleyville, TX 76034^_^_^_^_^_^_^_^_^_http://www.pinnaclewealthpartnersdfw.com/^_^_^_^_^_^_^_^_^_^_^_^_^_^_^_^_^_^_^_^_https://www.google.com/maps/place/?q=place_id:ChIJ05olcAbVTYYRK3_zk8ZWOTk^_^_^_^_^_^_^_^_^_^_^_^_^_^_wealth-manager^_32.88_-97.1471_wealth-manager'
    
    # Standardize to UNIT_SEP
    line = raw.replace("^_", UNIT_SEP)
    
    prospect = GoogleMapsProspect.from_usv(line)
    assert prospect.name == "Pinnacle Wealth Partners"
    assert prospect.website == "http://www.pinnaclewealthpartnersdfw.com/"
    assert prospect.domain == "pinnaclewealthpartnersdfw.com"
