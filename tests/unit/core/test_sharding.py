from cocli.core.sharding import get_shard_id

def test_get_shard_id_variability():
    # Test Place IDs that used to collide on first char 'C'
    pids = [
        "ChIJ-9Oz1dAV9YgRBTavXvn2DPY", # Index 5: 9
        "ChIJ-Q0XN9-g9YgRUSom1pMaJjY", # Index 5: Q
        "ChIJLZ6UEn1AuIkRzADaH9dPaRo", # Index 5: 6
        "ChIJdbusyWkXTIYRLaHy8lwhqgw", # Index 5: u
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
