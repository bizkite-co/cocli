import pytest
from cocli.core.config import load_campaign_config
import tomli_w

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
