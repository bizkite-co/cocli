---
layout: layout.njk
title: cocli Campaign Dashboard
---

# Campaign Overview: <span id="campaign-display">{% if env.CAMPAIGN %}{{ env.CAMPAIGN }}{% else %}turboship{% endif %}</span>

This dashboard provides a real-time view of the scraping and enrichment funnel.

## Data Funnel Report

{% include "components/report_table.njk" %}

## Prospect Search

{% include "components/search_box.njk" %}

## Downloads

{% include "components/downloads.njk" %}

<script src="https://cdnjs.cloudflare.com/ajax/libs/PapaParse/5.4.1/papaparse.min.js"></script>
<script>
    window.CAMPAIGN_NAME = '{% if env.CAMPAIGN %}{{ env.CAMPAIGN }}{% else %}turboship{% endif %}';
</script>
<script src="/dashboard.js"></script>
