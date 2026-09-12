from pathlib import Path

from cocli.planning.generate_grid import export_target_areas_geojson, export_to_kml


def test_export_target_areas_geojson_is_compact(tmp_path: Path) -> None:
    tiles = [
        {
            "id": "30.2_-97.7",
            "south_west_lat": 30.2,
            "south_west_lon": -97.7,
            "north_east_lat": 30.3,
            "north_east_lon": -97.6,
        }
    ]
    out = tmp_path / "target-areas.geojson"
    export_target_areas_geojson(tiles, str(out))
    data = out.read_text()
    assert '"kind":"target"' in data
    assert "30.2_-97.7" in data
    assert data.count("Feature") >= 1


def test_export_to_kml_writes_shared_style_and_geojson_sidecar(tmp_path: Path) -> None:
    tiles = [
        {
            "id": "30.2_-97.7",
            "south_west_lat": 30.2,
            "south_west_lon": -97.7,
            "north_east_lat": 30.3,
            "north_east_lon": -97.6,
            "step_deg": 0.1,
            "est_width_miles": 6,
            "est_height_miles": 6.9,
            "center_lat": 30.25,
            "center_lon": -97.65,
        }
    ]
    kml_path = tmp_path / "target-areas.kml"
    export_to_kml(tiles, str(kml_path), "test", color="08ffffff")
    kml = kml_path.read_text()
    assert kml.count("<Style") == 1
    assert "<styleUrl>#s</styleUrl>" in kml
    assert (tmp_path / "target-areas.geojson").exists()
