from cocli.models.campaigns.indexes.google_maps_list_item import GoogleMapsListItem


def test_schema_integrity():
    """Verify that GoogleMapsListItem schema contains expected fields and constraints."""
    fields = GoogleMapsListItem.get_datapackage_fields()
    field_names = [f["name"] for f in fields]

    # 1. Verify Field Count
    assert len(field_names) == 10, (
        f"Expected 10 fields, found {len(field_names)}: {field_names}"
    )

    # 2. Verify Category Field (Index 3)
    assert field_names[3] == "category", (
        f"Expected category at index 3, found {field_names[3]}"
    )

    # 3. Verify Constraints for place_id
    place_id_field = next(f for f in fields if f["name"] == "place_id")
    assert "constraints" in place_id_field
    assert place_id_field["constraints"]["minLength"] == 26
    assert place_id_field["constraints"]["maxLength"] == 29

    # 4. Verify Hash Generation
    schema_hash = GoogleMapsListItem.get_schema_hash()
    assert isinstance(schema_hash, str)
    assert len(schema_hash) > 0
