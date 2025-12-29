---
layout: layout.njk
title: cocli Campaign Dashboard
---

# Campaign Overview: <span id="campaign-display">turboship</span>

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

<p id="last-updated-text" style="font-size: 0.8em; color: #666; display:none;">
    Last Updated: <span id="last-updated-time"></span> 
    <button onclick="location.reload()">Refresh</button>
</p>

## Downloads

<div class="download-box">
    <h3>Latest Email Export</h3>
    <p>Download the most recent list of enriched prospects with emails.</p>
    <p><strong>Total Emails:</strong> <span id="email-count-display">...</span></p>
    <a href="#" id="download-link" class="button">Download CSV</a>
</div>

<script>
    async function fetchReport() {
        const urlParams = new URLSearchParams(window.location.search);
        const campaign = urlParams.get('campaign') || 'turboship';
        document.getElementById('campaign-display').textContent = campaign;
        
        try {
            const response = await fetch(`/reports/${campaign}.json?v=${Date.now()}`);
            if (!response.ok) throw new Error('Report data not found for this campaign.');
            
            const stats = await response.json();
            renderReport(stats);
        } catch (error) {
            document.getElementById('report-loading').style.display = 'none';
            const errDiv = document.getElementById('report-error');
            errDiv.textContent = error.message;
            errDiv.style.display = 'block';
        }
    }

    function renderReport(stats) {
        const body = document.getElementById('report-body');
        body.innerHTML = '';
        
        const rows = [
            { stage: 'Active Enrichment Workers', count: stats.active_fargate_tasks || 0, details: stats.active_fargate_tasks > 0 ? 'Running (Fargate)' : 'Stopped', badge: stats.active_fargate_tasks > 0 ? 'status-running' : '' },
            { stage: 'Scrape Tasks (gm-list)', count: `${stats.scrape_tasks_pending || 0} / ${stats.scrape_tasks_inflight || 0} Active`, details: 'SQS', badge: 'status-sqs' },
            { stage: 'GM List Items (gm-details)', count: `${stats.gm_list_item_pending || 0} / ${stats.gm_list_item_inflight || 0} Active`, details: 'SQS', badge: 'status-sqs' },
            { stage: 'Prospects (gm-detail)', count: (stats.prospects_count || 0).toLocaleString(), details: '100%', badge: '' },
            { stage: 'Enriched (Local)', count: (stats.enriched_count || 0).toLocaleString(), details: `${((stats.enriched_count / stats.prospects_count) * 100).toFixed(1)}%`, badge: '' },
            { stage: 'Emails Found', count: (stats.emails_found_count || 0).toLocaleString(), details: `${((stats.emails_found_count / stats.enriched_count) * 100).toFixed(1)}% (Yield)`, badge: '' }
        ];

        rows.forEach(row => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${row.stage}</td>
                <td>${row.count}</td>
                <td><span class="status-badge ${row.badge}">${row.details}</span></td>
            `;
            body.appendChild(tr);
        });

        document.getElementById('report-loading').style.display = 'none';
        document.getElementById('report-table').style.display = 'table';
        document.getElementById('last-updated-time').textContent = new Date(stats.last_updated).toLocaleString();
        document.getElementById('last-updated-text').style.display = 'block';
        
        // Update downloads
        document.getElementById('email-count-display').textContent = (stats.emails_found_count || 0).toLocaleString();
        const downloadBtn = document.getElementById('download-link');
        const campaign = stats.campaign_name || 'turboship';
        downloadBtn.href = `/exports/${campaign}-emails.csv`;
    }

    window.addEventListener('DOMContentLoaded', fetchReport);
</script>