import pytest
import os
import tomli_w
from cocli.core.config import (
    load_campaign_config, get_campaign, set_campaign, is_campaign_overridden
)

@pytest.fixture
def hierarchical_env(mock_cocli_env):
    """
    Sets up a nested config environment:
    campaigns/test/config.toml (base)
    campaigns/test/sub/config.toml (override)
    """
    campaigns_root = mock_cocli_env / "campaigns"
    
    # 1. Base test config
    test_root = campaigns_root / "test"
    test_root.mkdir(parents=True, exist_ok=True)
    with (test_root / "config.toml").open("wb") as f:
        tomli_w.dump({
            "aws": {"bucket": "base-bucket", "region": "us-east-1"},
            "scraper": {"delay": 10}
        }, f)

    # 2. Sub-namespace override
    sub_root = test_root / "sub"
    sub_root.mkdir(parents=True, exist_ok=True)
    with (sub_root / "config.toml").open("wb") as f:
        tomli_w.dump({
            "aws": {"bucket": "sub-bucket"},
            "new_key": "hello"
        }, f)

    # 3. Specific campaign
    camp_root = sub_root / "my-camp"
    camp_root.mkdir(parents=True, exist_ok=True)
    with (camp_root / "config.toml").open("wb") as f:
        tomli_w.dump({
            "scraper": {"delay": 20}
        }, f)

    return mock_cocli_env

def test_campaign_resolution_hierarchy(mock_cocli_env, monkeypatch):
    """
    Verifies the Hierarchy of Truth for campaign resolution:
    1. Environment Override (COCLI_CAMPAIGN)
    2. Global Config (cocli_config.toml)
    """
    # 1. Start with no campaign
    monkeypatch.delenv("COCLI_CAMPAIGN", raising=False)
    assert get_campaign() is None
    assert is_campaign_overridden() is False

    # 2. Set Global Config
    set_campaign("global_camp")
    # set_campaign automatically sets the env var for the current process
    # for consistency. Let's clear it to test the fallback.
    monkeypatch.delenv("COCLI_CAMPAIGN", raising=False)
    
    assert get_campaign() == "global_camp"
    assert is_campaign_overridden() is False

    # 3. Set Environment Override
    monkeypatch.setenv("COCLI_CAMPAIGN", "env_override")
    assert get_campaign() == "env_override"
    assert is_campaign_overridden() is True

def test_set_campaign_updates_environment(mock_cocli_env, monkeypatch):
    """
    Ensures that calling set_campaign (e.g. from TUI) updates 
    the environment variable to maintain process-wide consistency.
    """
    monkeypatch.delenv("COCLI_CAMPAIGN", raising=False)
    set_campaign("new_context")
    assert os.environ["COCLI_CAMPAIGN"] == "new_context"
    assert get_campaign() == "new_context"
    assert is_campaign_overridden() is True

def test_load_campaign_config_inheritance(hierarchical_env):
    # Load the deep campaign
    config = load_campaign_config("test/sub/my-camp")
    
    # 1. Inherited from root 'test'
    assert config["aws"]["region"] == "us-east-1"
    
    # 2. Overridden by 'sub'
    assert config["aws"]["bucket"] == "sub-bucket"
    
    # 3. Inherited from 'sub'
    assert config["new_key"] == "hello"
    
    # 4. Overridden by specific 'my-camp'
    assert config["scraper"]["delay"] == 20

def test_load_campaign_config_shallow(hierarchical_env):
    # Load just the top 'test' campaign
    config = load_campaign_config("test")
    
    assert config["aws"]["bucket"] == "base-bucket"
    assert "new_key" not in config
