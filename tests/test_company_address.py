import pytest
from cocli.models.company_address import CompanyAddress


def test_basic_address():
    """Test basic address without quotes."""
    ca = CompanyAddress.model_validate("123 Main St, Austin, TX 78701")
    assert str(ca) == "123 Main St, Austin, TX 78701"


def test_remove_outer_double_quotes():
    """Test removal of outer double quotes."""
    ca = CompanyAddress.model_validate('"123 Main St, Austin, TX 78701"')
    assert str(ca) == "123 Main St, Austin, TX 78701"


def test_preserves_single_quotes():
    """Single-quotes are preserved - only double-quotes (the confirmed real
    CSV/scraper corruption artifact) are stripped."""
    ca = CompanyAddress.model_validate("'123 Main St, Austin, TX 78701'")
    assert str(ca) == "'123 Main St, Austin, TX 78701'"


def test_remove_doubled_quotes():
    """Test removal of doubled quote characters."""
    # Doubled quotes from legacy data
    ca = CompanyAddress.model_validate('123 ""Main"" St, Austin, TX 78701')
    assert str(ca) == '123 Main St, Austin, TX 78701'


def test_remove_mixed_quotes():
    """Only double-quotes are stripped; an embedded single-quote survives."""
    ca = CompanyAddress.model_validate('"123 \'Main\' St, Austin, TX 78701"')
    assert str(ca) == "123 'Main' St, Austin, TX 78701"


def test_normalize_whitespace():
    """Test normalization of multiple spaces."""
    ca = CompanyAddress.model_validate("123  Main  St,  Austin,  TX  78701")
    assert str(ca) == "123 Main St, Austin, TX 78701"


def test_trim_whitespace():
    """Test trimming of leading and trailing whitespace."""
    ca = CompanyAddress.model_validate("  123 Main St, Austin, TX 78701  ")
    assert str(ca) == "123 Main St, Austin, TX 78701"


def test_complex_legacy_data():
    """Test complex legacy data with multiple issues."""
    # Simulates legacy address with quotes, extra spaces, and doubled quote characters
    ca = CompanyAddress.model_validate('  "123  ""Main""  St,  Austin,  TX  78701"  ')
    assert str(ca) == '123 Main St, Austin, TX 78701'


def test_null_address():
    """Test None handling."""
    ca = CompanyAddress.model_validate(None)
    assert ca is None


def test_empty_string_raises():
    """Test that empty string raises ValueError."""
    with pytest.raises(ValueError):
        CompanyAddress.model_validate("")


def test_whitespace_only_raises():
    """Test that whitespace-only string raises ValueError."""
    with pytest.raises(ValueError):
        CompanyAddress.model_validate("   ")


def test_quotes_only_raises():
    """Test that quotes-only string raises ValueError."""
    with pytest.raises(ValueError):
        CompanyAddress.model_validate('""""""')


def test_pydantic_integration():
    """Test integration with Pydantic models."""
    from pydantic import BaseModel
    from cocli.models.company_address import OptionalCompanyAddress

    class TestCompany(BaseModel):
        full_address: OptionalCompanyAddress = None
        street_address: OptionalCompanyAddress = None

    # Test with None
    c1 = TestCompany(full_address=None, street_address=None)
    assert c1.full_address is None
    assert c1.street_address is None

    # Test with quoted addresses
    c2 = TestCompany(
        full_address='"123 Main St, Austin, TX 78701"',
        street_address='"123 Main St"'
    )
    assert str(c2.full_address) == "123 Main St, Austin, TX 78701"
    assert str(c2.street_address) == "123 Main St"

    # Test serialization
    assert c2.model_dump()["full_address"] == "123 Main St, Austin, TX 78701"
    assert c2.model_dump()["street_address"] == "123 Main St"
