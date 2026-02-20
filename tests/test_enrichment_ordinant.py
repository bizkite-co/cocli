from cocli.models.campaigns.queues.enrichment import EnrichmentTask

def test_gold_standard_enrichment_ordinant():
    domain = "ameripriseadvisors.com"
    task = EnrichmentTask(
        domain=domain,
        company_slug="jack-venable",
        campaign_name="roadmap"
    )
    
    # Gold Standard: ID is the Domain
    assert task.task_id == domain
    
    # Shard: sha256('ameripriseadvisors.com')[:2] == 'e1'
    assert task.shard == "e1"
    
    # S3 Path: campaigns/roadmap/queues/enrichment/pending/e1/ameripriseadvisors.com/task.json
    expected_s3 = f"campaigns/roadmap/queues/enrichment/pending/e1/{domain}/task.json"
    assert task.get_s3_task_key() == expected_s3
    

if __name__ == "__main__":
    test_gold_standard_enrichment_ordinant()
