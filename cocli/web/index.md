---
layout: layout.njk
title: cocli Campaign Dashboard
---

# Campaign Overview: <span id="campaign-display">{{ campaign.name }}</span>

This dashboard provides a real-time view of the scraping and enrichment funnel.

## Downloads

{% include "components/downloads.njk" %}

## Prospect Search

{% include "components/search_box.njk" %}

<script src="/papaparse.min.js"></script>
<script>
    window.CAMPAIGN_NAME = '{{ campaign.name }}';
</script>
<script src="/dashboard.js"></script>
