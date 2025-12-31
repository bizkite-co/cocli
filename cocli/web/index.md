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

<div class="campaign-config-grid">
    <div class="config-section">
        <h3>Search Queries</h3>
        <div class="input-group">
            <input type="text" id="new-query" placeholder="Add new query...">
            <button onclick="addPendingChange('query', document.getElementById('new-query').value)">Add</button>
        </div>
        <ul id="queries-list" class="config-list">
            <!-- Queries will be injected here -->
        </ul>
        <p class="config-hint">Modify these in <code>config.toml</code> under <code>[prospecting].queries</code></p>
    </div>
    <div class="config-section">
        <h3>Target Locations</h3>
        <div class="input-group">
            <input type="text" id="new-location" placeholder="Add new location...">
            <button onclick="addPendingChange('location', document.getElementById('new-location').value)">Add</button>
        </div>
        <div class="scroll-container">
            <ul id="locations-list" class="config-list">
                <!-- Locations will be injected here -->
            </ul>
        </div>
        <p class="config-hint">Modify these in <code>target_locations.csv</code> or <code>config.toml</code></p>
    </div>
</div>

<div id="pending-changes-container" style="display:none;" class="pending-changes">
    <h3>Apply Changes</h3>
    <p>Copy and run these commands in your terminal to apply the changes:</p>
    <pre id="pending-commands-box"></pre>
    <button onclick="clearPendingChanges()">Clear All</button>
</div>

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

    window.addEventListener('DOMContentLoaded', fetchReport);

    let pendingChanges = [];

    function addPendingChange(type, value) {
        if (!value) return;
        const campaign = document.getElementById('campaign-display').textContent;
        const cmd = `cocli campaign add-${type} "${value}" --campaign ${campaign}`;
        if (!pendingChanges.includes(cmd)) {
            pendingChanges.push(cmd);
            updatePendingUI();
        }
        if (type === 'query') document.getElementById('new-query').value = '';
        if (type === 'location') document.getElementById('new-location').value = '';
    }

    function removeExisting(type, value) {
        const campaign = document.getElementById('campaign-display').textContent;
        const cmd = `cocli campaign remove-${type} "${value}" --campaign ${campaign}`;
        if (!pendingChanges.includes(cmd)) {
            pendingChanges.push(cmd);
            updatePendingUI();
        }
    }

    function updatePendingUI() {
        const container = document.getElementById('pending-changes-container');
        const box = document.getElementById('pending-commands-box');
        if (pendingChanges.length > 0) {
            container.style.display = 'block';
            box.textContent = pendingChanges.join('\n');
        } else {
            container.style.display = 'none';
        }
    }

    function clearPendingChanges() {
        pendingChanges = [];
        updatePendingUI();
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
        
        // Update queries
        const queriesList = document.getElementById('queries-list');
        queriesList.innerHTML = '';
        (stats.queries || []).forEach(q => {
            const li = document.createElement('li');
            li.className = 'list-item-editable';
            li.innerHTML = `<span>${q}</span> <button class="btn-remove" onclick="removeExisting('query', '${q}')">×</button>`;
            queriesList.appendChild(li);
        });

        // Update locations
        const locationsList = document.getElementById('locations-list');
        locationsList.innerHTML = '';
        (stats.locations || []).forEach(loc => {
            const li = document.createElement('li');
            li.className = 'list-item-editable';
            li.innerHTML = `<span>${loc}</span> <button class="btn-remove" onclick="removeExisting('location', '${loc}')">×</button>`;
            locationsList.appendChild(li);
        });

        // Update downloads

</script>