import toml
from cocli.core.paths import paths
from cocli.application.worker_service import WorkerService

def test_worker_service_resolve_worker_definitions(tmp_path):
    # Set up isolated paths
    paths.root = tmp_path
    campaign_name = "test-campaign"
    campaign_dir = tmp_path / "campaigns" / campaign_name
    campaign_dir.mkdir(parents=True)

    # Create config.toml with scaling configs
    config_data = {
        "prospecting": {
            "scaling": {
                "fargate": {
                    "gm-list": 2,
                    "enrichment": 1
                }
            }
        }
    }
    with open(campaign_dir / "config.toml", "w") as f:
        toml.dump(config_data, f)

    service = WorkerService(campaign_name=campaign_name)

    # 1. Resolve for Fargate
    defs = service.resolve_worker_definitions(hostname="fargate", running_in_fargate=True)
    assert len(defs) == 2
    
    # Assert gm-list definition
    gm_list_def = next(d for d in defs if d.content_type == "gm-list")
    assert gm_list_def.workers == 2
    assert gm_list_def.role == "full"

    # Assert enrichment definition
    enrichment_def = next(d for d in defs if d.content_type == "enrichment")
    assert enrichment_def.workers == 1

    # 2. Fallback to default when not in Fargate and host not configured
    defs_default = service.resolve_worker_definitions(hostname="some-random-pi", running_in_fargate=False)
    assert len(defs_default) == 1
    assert defs_default[0].content_type == "gm-list"
    assert defs_default[0].workers == 1
