---
layout: layout.njk
title: cocli Campaign Configuration
---

# Campaign Configuration: <span id="campaign-display">{% if env.CAMPAIGN %}{{ env.CAMPAIGN }}{% else %}turboship{% endif %}</span>

<p style="background: #e9ecef; padding: 10px; border-radius: 4px; display: inline-block;">
    <strong>Global Proximity:</strong> <span id="proximity-display">...</span> miles
</p>

Modify the search queries and target locations for the current campaign.

{% include "components/worker_stats.njk" %}

<div class="campaign-config-grid">
    <div class="config-sidebar">
        {% include "components/pending_changes.njk" %}
        {% include "components/exclusions_config.njk" %}
        {% include "components/queries_config.njk" %}
    </div>
    <div class="config-main">
        {% include "components/locations_config.njk" %}
    </div>
</div>

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="/config_dashboard.js"></script>