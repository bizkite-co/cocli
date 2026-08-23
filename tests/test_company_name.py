import pytest
from cocli.models.company_name import CompanyName


def test_basic_name():
    """Test basic company name without quotes."""
    cn = CompanyName.model_validate("Acme Corp")
    assert str(cn) == "Acme Corp"


def test_remove_outer_double_quotes():
    """Test removal of outer double quotes."""
    cn = CompanyName.model_validate('"Acme Corp"')
    assert str(cn) == "Acme Corp"


def test_preserves_single_quotes():
    """Single-quotes are real content in business names ("John's Flooring",
    "Lowe's") far more often than they're a CSV artifact - confirmed live
    against production data (193 of 197 checkpoint names with a quote
    character were legitimate apostrophes, only 4 were real corruption,
    and all 4 used double-quotes). Only double-quotes get stripped."""
    cn = CompanyName.model_validate("'Acme Corp'")
    assert str(cn) == "'Acme Corp'"
    cn2 = CompanyName.model_validate("John's Flooring Inc.")
    assert str(cn2) == "John's Flooring Inc."


def test_remove_doubled_quotes():
    """Test removal of doubled quote characters."""
    # Doubled quotes from legacy data: Acme ""Real"" Corp becomes Acme Real Corp
    cn = CompanyName.model_validate('Acme ""Real"" Corp')
    assert str(cn) == 'Acme Real Corp'


def test_remove_mixed_quotes():
    """Only double-quotes are stripped; an embedded single-quote survives."""
    cn = CompanyName.model_validate('"Acme \'Real\' Corp"')
    assert str(cn) == "Acme 'Real' Corp"


def test_normalize_whitespace():
    """Test normalization of multiple spaces."""
    cn = CompanyName.model_validate("Acme    Corp    Inc")
    assert str(cn) == "Acme Corp Inc"


def test_trim_whitespace():
    """Test trimming of leading and trailing whitespace."""
    cn = CompanyName.model_validate("  Acme Corp  ")
    assert str(cn) == "Acme Corp"


def test_complex_legacy_data():
    """Test complex legacy data with multiple issues."""
    # Simulates legacy name with quotes, extra spaces, and doubled quote characters
    cn = CompanyName.model_validate('  "Acme  ""Real""  Corp"  ')
    assert str(cn) == 'Acme Real Corp'


def test_null_name():
    """Test None handling."""
    cn = CompanyName.model_validate(None)
    assert cn is None


def test_empty_string_raises():
    """Test that empty string raises ValueError."""
    with pytest.raises(ValueError):
        CompanyName.model_validate("")


def test_whitespace_only_raises():
    """Test that whitespace-only string raises ValueError."""
    with pytest.raises(ValueError):
        CompanyName.model_validate("   ")


def test_quotes_only_raises():
    """Test that quotes-only string raises ValueError."""
    with pytest.raises(ValueError):
        CompanyName.model_validate('""""""')


def test_pydantic_integration():
    """Test integration with Pydantic models."""
    from pydantic import BaseModel
    from cocli.models.company_name import OptionalCompanyName

    class TestCompany(BaseModel):
        name: OptionalCompanyName = None

    # Test with None
    c1 = TestCompany(name=None)
    assert c1.name is None

    # Test with quoted name
    c2 = TestCompany(name='"Acme Corp"')
    assert str(c2.name) == "Acme Corp"

    # Test serialization
    assert c2.model_dump()["name"] == "Acme Corp"
