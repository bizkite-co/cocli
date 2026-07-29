"""GoogleMapsPlace domain value bounds and their export to datapackage.json.

Regression coverage for two bugs found together:
  1. average_rating/reviews_count had no bounds on GoogleMapsPlace (the base
     GoogleMapsProspect/GoogleMapsVenue share), even though GoogleMapsListItem
     (upstream gm-list stage) already enforced ge=0.0/le=5.0. A misaligned
     column could carry an out-of-range value all the way to the checkpoint
     with nothing to reject it.
  2. Three independent reimplementations of get_datapackage_fields existed in
     the MRO (BaseUsvModel, BaseIndexModel, GoogleMapsPlace). GoogleMapsPlace's
     super() call landed on BaseIndexModel's copy, which never exported Field
     constraints - so even a correctly-bounded field wouldn't reach
     datapackage.json for any index model.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
from cocli.models.campaigns.indexes.google_maps_venue import GoogleMapsVenue

_PLACE_ID = "ChIJ" + "x" * 22


def _base(**overrides: Any) -> dict[str, Any]:
    return {"place_id": _PLACE_ID, "slug": "test-co", "name": "Test Co", **overrides}


@pytest.mark.parametrize("model_cls", [GoogleMapsProspect, GoogleMapsVenue])
def test_average_rating_rejects_out_of_range(
    model_cls: type[GoogleMapsProspect] | type[GoogleMapsVenue],
) -> None:
    model_cls.model_validate(_base(average_rating=4.2))  # in range: fine
    with pytest.raises(ValidationError):
        model_cls.model_validate(_base(average_rating=47.0))
    with pytest.raises(ValidationError):
        model_cls.model_validate(_base(average_rating=-1.0))


@pytest.mark.parametrize("model_cls", [GoogleMapsProspect, GoogleMapsVenue])
def test_reviews_count_rejects_negative(
    model_cls: type[GoogleMapsProspect] | type[GoogleMapsVenue],
) -> None:
    model_cls.model_validate(_base(reviews_count=10))  # fine
    with pytest.raises(ValidationError):
        model_cls.model_validate(_base(reviews_count=-5))


@pytest.mark.parametrize("model_cls", [GoogleMapsProspect, GoogleMapsVenue])
@pytest.mark.parametrize("value", [None, ""])
def test_missing_rating_and_reviews_count_pass_through_as_none(
    model_cls: type[GoogleMapsProspect] | type[GoogleMapsVenue],
    value: object,
) -> None:
    """Regression: Field(ge=/le=) placed after BeforeValidator in the Annotated
    stack made a bare None/"" raise a raw TypeError instead of validating
    cleanly - most real prospects have no rating at all."""
    p = model_cls.model_validate(
        _base(average_rating=value, reviews_count=value)
    )
    assert p.average_rating is None
    assert p.reviews_count is None


@pytest.mark.parametrize("model_cls", [GoogleMapsProspect, GoogleMapsVenue])
def test_bounds_are_exported_to_datapackage_fields(
    model_cls: type[GoogleMapsProspect] | type[GoogleMapsVenue],
) -> None:
    fields = {f["name"]: f for f in model_cls.get_datapackage_fields()}
    assert fields["average_rating"]["constraints"] == {"minimum": 0.0, "maximum": 5.0}
    assert fields["reviews_count"]["constraints"] == {"minimum": 0}


def test_deprecated_flag_still_exported_after_collapsing_override_chain() -> None:
    fields = {f["name"]: f for f in GoogleMapsProspect.get_datapackage_fields()}
    assert fields["email"].get("deprecated") is True
