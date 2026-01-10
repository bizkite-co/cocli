import pytest
from cocli.models.phone import PhoneNumber

def test_parse_nanp_basic():
    p = PhoneNumber.model_validate("5125551212")
    assert p.country_code == "1"
    assert p.national_destination_code == "512"
    assert p.subscriber_number == "5551212"
    assert str(p) == "15125551212"

def test_parse_nanp_formatted():
    p = PhoneNumber.model_validate("(512) 555-1212")
    assert p.country_code == "1"
    assert p.national_destination_code == "512"
    assert p.subscriber_number == "5551212"

def test_parse_nanp_with_plus():
    p = PhoneNumber.model_validate("+1 512-555-1212")
    assert p.country_code == "1"
    assert p.national_destination_code == "512"
    assert p.subscriber_number == "5551212"

def test_parse_mismatched_parentheses():
    # Example from user: 414) 321-7507
    p = PhoneNumber.model_validate("414) 321-7507")
    assert p.country_code == "1"
    assert p.national_destination_code == "414"
    assert p.subscriber_number == "3217507"

def test_parse_dots():
    p = PhoneNumber.model_validate("626.581.6159")
    assert p.country_code == "1"
    assert p.national_destination_code == "626"
    assert p.subscriber_number == "5816159"

def test_parse_international_uk():
    # Example from data: 07887 795086
    # If we assume it's UK and it has the leading 0, we might need a way to handle it.
    # For now, let's test explicit +44
    p = PhoneNumber.model_validate("+44 7887 795086")
    assert p.country_code == "44"
    # This might fail with current naive implementation, let's see.

def test_formatting():
    p = PhoneNumber(
        country_code="1",
        national_destination_code="512",
        subscriber_number="5551212"
    )
    assert p.format("international") == "+1 (512) 555-1212"
    assert p.format("national") == "(512) 555-1212"
    assert p.format("dots") == "1.512.555.1212"
    assert p.format("digits") == "15125551212"
    assert p.format("e164") == "+15125551212"
    assert p.format("{ndc}-{sn_prefix}-{sn_line}") == "512-555-1212"

def test_parse_with_extension():
    p = PhoneNumber.model_validate("(512) 555-1212 x101")
    assert p.country_code == "1"
    assert p.national_destination_code == "512"
    assert p.subscriber_number == "5551212"
    assert p.extension == "101"
    assert p.format("international") == "+1 (512) 555-1212 ext 101"

def test_invalid_phone():
    with pytest.raises(Exception): # Should raise ValueError or similar
        PhoneNumber.model_validate("abc")

def test_null_phone():
    # Test if it can be used with Optional
    from typing import Optional
    from pydantic import BaseModel
    
    class TestModel(BaseModel):
        phone: Optional[PhoneNumber] = None
        
    m = TestModel(phone=None)
    assert m.phone is None
    
    m2 = TestModel(phone="(512) 555-1212")
    assert m2.phone.country_code == "1"
