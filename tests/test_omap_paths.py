from cocli.core.paths import paths
from cocli.models.company import Company
from cocli.models.person import Person
from cocli.core.ordinant import Ordinant

def test_hierarchical_paths():
    # Test dot-notation for campaigns
    camp = paths.campaign("test-campaign")
    assert str(camp.indexes).endswith("campaigns/test-campaign/indexes")
    assert str(camp.index("google_maps_prospects").checkpoint).endswith("campaigns/test-campaign/indexes/google_maps_prospects/prospects.checkpoint.usv")
    
    # Test dot-notation for queues
    q = camp.queue("enrichment")
    assert str(q.pending).endswith("campaigns/test-campaign/queues/enrichment/pending")
    
    # Test dot-notation for global collections
    assert str(paths.companies.path).endswith("companies")
    assert str(paths.companies.entry("apple")).endswith("companies/apple")

def test_company_ordinant():
    company = Company(name="Apple", slug="apple")
    assert isinstance(company, Ordinant)
    assert company.collection == "companies"
    assert str(company.get_local_path()).endswith("companies/apple")
    assert company.get_remote_key() == "companies/apple/"

def test_person_ordinant():
    person = Person(name="Steve Jobs", slug="steve-jobs")
    assert isinstance(person, Ordinant)
    assert person.collection == "people"
    assert str(person.get_local_path()).endswith("people/steve-jobs")
    assert person.get_remote_key() == "people/steve-jobs/"

def test_ensure_method(tmp_path):
    # Test that .ensure() creates directories
    paths.root = tmp_path
    camp = paths.campaign("brand-new")
    idx_path = camp.index("domains").ensure()
    
    assert idx_path.exists()
    assert idx_path.is_dir()
    assert str(idx_path).endswith("campaigns/brand-new/indexes/domains")
