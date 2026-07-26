from cocli.core.sharding import (
    get_place_id_shard,
    get_place_id_shard_from_last_character_of_place_id,
    get_shard_id,
)
from stations.segments import shard_by_char_index


def test_get_shard_id_variability():
    # Test Place IDs that used to collide on first char 'C'
    pids = [
        "ChIJ-9Oz1dAV9YgRBTavXvn2DPY",  # Index 5: 9
        "ChIJ-Q0XN9-g9YgRUSom1pMaJjY",  # Index 5: Q
        "ChIJLZ6UEn1AuIkRzADaH9dPaRo",  # Index 5: Z
        "ChIJdbusyWkXTIYRLaHy8lwhqgw",  # Index 5: b
    ]

    shards = [get_shard_id(pid) for pid in pids]

    assert shards == ["9", "Q", "Z", "b"]
    assert len(set(shards)) == 4


def test_get_shard_id_short_input():
    assert get_shard_id("ChIJ") == "_"
    assert get_shard_id("") == "_"
    assert get_shard_id(None) == "_"


def test_get_shard_id_consistency():
    pid = "ChIJ-9Oz1dAV9YgRBTavXvn2DPY"
    assert get_shard_id(pid) == get_shard_id(pid)


def test_place_id_dash_and_underscore_are_distinct_shards():
    """
    Place IDs are base64-like: '-' and '_' at index 5 must not collapse.

    Production S3 keeps both pending/-/ and pending/_/ as separate folders.
    Slugifying non-alnum to '_' collides those identities.
    """
    dash_id = "ChIJ--Cy9B3Jw4kR9h1ar_qcBTg"  # index 5 = '-'
    under_id = "ChIJg_FAeU6P3YgRdYX05J1RuZw"  # index 5 = '_'

    assert dash_id[5] == "-"
    assert under_id[5] == "_"

    assert get_place_id_shard(dash_id) == "-"
    assert get_place_id_shard(under_id) == "_"
    assert get_shard_id(dash_id) == "-"
    assert get_shard_id(under_id) == "_"

    # Must not collide
    assert get_place_id_shard(dash_id) != get_place_id_shard(under_id)


def test_shard_by_char_index_matches_place_id_shard():
    s = shard_by_char_index(5)
    for key in (
        "ChIJ--Cy9B3Jw4kR9h1ar_qcBTg",
        "ChIJg_FAeU6P3YgRdYX05J1RuZw",
        "ChIJ-5-rest",
        "ChIJ5X0j7DHDwogRvQgaGw0y4FM",
        "short",
    ):
        assert s.shard_for(key) == get_place_id_shard(key), key


def test_last_char_variant_also_preserves_alphabet():
    # trailing '-' or '_' must stay distinct if used
    assert get_place_id_shard_from_last_character_of_place_id("abc-") == "-"
    assert get_place_id_shard_from_last_character_of_place_id("abc_") == "_"
