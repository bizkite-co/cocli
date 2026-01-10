import pytest
from pathlib import Path
from cocli.models.company import Company
from cocli.compilers.website_compiler import WebsiteCompiler
from cocli.core.utils import create_company_files

@pytest.fixture
def test_data_dir(tmp_path):
    """Creates a temporary directory structure for company data."""
    companies_dir = tmp_path / "companies"
    companies_dir.mkdir()
    return companies_dir

def test_enrichment_compilation_suite(test_data_dir):
    """
    Data-driven suite using ACTUAL files from tests/data/websites/enrichment/
    Ensures real-world failure cases remain fixed.
    """
    enrichment_data_dir = Path("tests/data/websites/enrichment")
    enrichment_files = list(enrichment_data_dir.glob("*.md"))
    
    assert len(enrichment_files) >= 3
    
    compiler = WebsiteCompiler()
    
    for enrichment_file in enrichment_files:
        company_slug = enrichment_file.stem
        company_dir = test_data_dir / company_slug
        company_dir.mkdir()
        (company_dir / "enrichments").mkdir()
        
        index_content = f"---\nname: {company_slug}\ndomain: {company_slug}.com\nslug: {company_slug}\n---"
        (company_dir / "_index.md").write_text(index_content)
        
        target_path = company_dir / "enrichments" / "website.md"
        target_path.write_text(enrichment_file.read_text())
        
        compiler.compile(company_dir)
        
        reloaded = Company.from_directory(company_dir)
        assert reloaded is not None
        
        if "beckerarena" in company_slug:
            # Tests malformed header handling
            assert len(reloaded.services) > 0, "Becker services should be populated"
            assert "Indoor Hockey" in reloaded.services
        elif "2020-flooring" in company_slug:
            # Tests products and basic compilation despite malformed header
            assert len(reloaded.products) > 0, "2020-Flooring products should be populated"
        elif "diamond-cut" in company_slug:
            # Tests junk email filtering
            if reloaded.email:
                assert not str(reloaded.email).endswith(".png"), "Primary email should be cleaned"
            for email in reloaded.all_emails:
                assert not str(email).endswith(".png"), "all_emails should be cleaned"

def test_categories_preservation(test_data_dir):
    """Self-contained unit test: Ensures categories are preserved and indexed correctly."""
    company_slug = "cat-test"
    company_dir = test_data_dir / company_slug
    company_dir.mkdir()
    (company_dir / "enrichments").mkdir()
    
    index_content = "---\nname: Cat Co\ndomain: cat.com\nslug: cat-test\n---"
    (company_dir / "_index.md").write_text(index_content)
    
    website_content = "---\nurl: cat.com\ncategories:\n  - Flooring Specialist\n  - Sports Surfaces\n---"
    (company_dir / "enrichments" / "website.md").write_text(website_content)
    
    compiler = WebsiteCompiler()
    compiler.compile(company_dir)
    
    reloaded = Company.from_directory(company_dir)
    assert "Flooring Specialist" in reloaded.categories
    
    content = (company_dir / "_index.md").read_text()
    assert "categories:" in content

def test_yaml_corruption_regression(test_data_dir):
    """Ensures saved YAML doesn't include !!python/object tags."""
    from cocli.models.email_address import EmailAddress
    
    company_slug = "yaml-tag-test"
    company_dir = test_data_dir / company_slug
    company_dir.mkdir()
    
    company = Company(
        name="Tag Test",
        domain="tag.com",
        slug="yaml-tag-test",
        email=EmailAddress("test@tag.com")
    )
    
    create_company_files(company, company_dir)
    
    content = (company_dir / "_index.md").read_text()
    assert "!!python/object" not in content
    assert "email: test@tag.com" in content

if __name__ == "__main__":
    pytest.main([__file__])