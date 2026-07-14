import toml
from cocli.core.paths import paths
from cocli.application.web_service import WebService

def test_web_service_resolve_deployment_config(tmp_path):
    # Set up isolated paths
    paths.root = tmp_path
    campaign_name = "test-campaign"
    campaign_dir = tmp_path / "campaigns" / campaign_name
    campaign_dir.mkdir(parents=True)

    # Create config.toml
    config_data = {
        "aws": {
            "profile": "test-profile",
            "hosted-zone-domain": "test-domain.com"
        }
    }
    with open(campaign_dir / "config.toml", "w") as f:
        toml.dump(config_data, f)

    service = WebService(campaign_name=campaign_name)
    cfg = service.resolve_deployment_config()

    assert cfg["profile"] == "test-profile"
    assert cfg["domain"] == "cocli.test-domain.com"
    assert cfg["bucket_name"] == "cocli-web-assets-test-domain-com"
