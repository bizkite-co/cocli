---
layout: layout.njk
title: cocli Campaign Dashboard
---

# Campaign Overview: <span id="campaign-display">{% if env.CAMPAIGN %}{{ env.CAMPAIGN }}{% else %}turboship{% endif %}</span>

This dashboard provides a real-time view of the scraping and enrichment funnel.

## Data Funnel Report

<div id="report-loading">Loading report data...</div>
<div id="report-error" style="display:none; color: red; margin: 20px 0;"></div>

<table class="report-table" id="report-table" style="display:none;">
    <thead>
        <tr>
            <th>Stage</th>
            <th>Count</th>
            <th>Details</th>
        </tr>
    </thead>
    <tbody id="report-body">
        <!-- Data will be injected here -->
    </tbody>
</table>

<div id="worker-stats-container" style="display:none; margin: 20px 0;">
    <h3>Processing Sources (GM Details)</h3>
    <table class="report-table">
        <thead>
            <tr>
                <th>Worker Type</th>
                <th>Count</th>
                <th>Share</th>
            </tr>
        </thead>
        <tbody id="worker-stats-body">
        </tbody>
    </table>
</div>

<p id="last-updated-text" style="font-size: 0.8em; color: #666; display:none;">
    Last Updated: <span id="last-updated-time"></span> 
    <button onclick="location.reload()">Refresh</button>
</p>

## Prospect Search

<div class="search-box" style="background: white; padding: 20px; border-radius: 4px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin: 20px 0;">
    <div class="input-group">
        <input type="text" id="prospect-search" placeholder="Search by name, domain, email, category..." style="flex: 2;">
        <select id="category-filter">
            <option value="">All Categories</option>
        </select>
    </div>
    <div id="search-results-info" style="margin-top: 10px; font-size: 0.9em; color: #666;"></div>
</div>

<div id="prospects-loading">Loading prospect data for search...</div>
<div id="prospects-container" class="prospect-grid" style="display:none;">
    <!-- Cards will be injected here -->
</div>

## Downloads

<div class="download-box">
    <h3>Latest Email Export</h3>
    <p>Download the most recent list of enriched prospects with emails.</p>
    <p><strong>Total Emails:</strong> <span id="email-count-display">...</span></p>
    <div style="display: flex; gap: 10px;">
        <a href="#" id="download-link" class="button">Download CSV</a>
        <a href="#" id="download-link-json" class="button" style="background: #666;">Download JSON</a>
    </div>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/PapaParse/5.4.1/papaparse.min.js"></script>
<script>
    window.CAMPAIGN_NAME = '{% if env.CAMPAIGN %}{{ env.CAMPAIGN }}{% else %}turboship{% endif %}';
</script>
<script src="/dashboard.js"></script>