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
<table class="report-table" id="prospects-table" style="display:none;">
    <thead>
        <tr>
            <th>Company</th>
            <th>Emails</th>
            <th>Categories</th>
            <th>Actions</th>
        </tr>
    </thead>
    <tbody id="prospects-body">
    </tbody>
</table>

## Downloads

<div class="download-box">
    <h3>Latest Email Export</h3>
    <p>Download the most recent list of enriched prospects with emails.</p>
    <p><strong>Total Emails:</strong> <span id="email-count-display">...</span></p>
    <a href="#" id="download-link" class="button">Download CSV</a>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/PapaParse/5.4.1/papaparse.min.js"></script>
<script>
    let allProspects = [];
    let categories = new Set();

    async function fetchReport() {
        const urlParams = new URLSearchParams(window.location.search);
        const campaign = urlParams.get('campaign') || '{% if env.CAMPAIGN %}{{ env.CAMPAIGN }}{% else %}turboship{% endif %}';
        document.getElementById('campaign-display').textContent = campaign;
        
        try {
            const response = await fetch(`/reports/${campaign}.json?v=${Date.now()}`);
            if (!response.ok) throw new Error('Report data not found for this campaign.');
            
            const stats = await response.json();
            renderReport(stats);
            fetchProspects(stats.campaign_name || campaign);
        } catch (error) {
            document.getElementById('report-loading').style.display = 'none';
            const errDiv = document.getElementById('report-error');
            errDiv.textContent = error.message;
            errDiv.style.display = 'block';
        }
    }

    async function fetchProspects(campaign) {
        try {
            const csvUrl = `/exports/${campaign}-emails.csv?v=${Date.now()}`;
            Papa.parse(csvUrl, {
                download: true,
                header: true,
                skipEmptyLines: true,
                complete: function(results) {
                    allProspects = results.data;
                    document.getElementById('prospects-loading').style.display = 'none';
                    document.getElementById('prospects-table').style.display = 'table';
                    
                    // Build category list
                    allProspects.forEach(p => {
                        if (p.categories) {
                            p.categories.split(';').forEach(c => {
                                const cat = c.trim();
                                if (cat) categories.add(cat);
                            });
                        }
                    });
                    
                    const filter = document.getElementById('category-filter');
                    Array.from(categories).sort().forEach(cat => {
                        const opt = document.createElement('option');
                        opt.value = cat;
                        opt.textContent = cat;
                        filter.appendChild(opt);
                    });

                    renderProspects(allProspects);
                },
                error: function(err) {
                    document.getElementById('prospects-loading').textContent = 'Error loading prospects CSV.';
                    console.error('PapaParse error:', err);
                }
            });
        } catch (error) {
            console.error('Fetch error:', error);
        }
    }

    function renderProspects(prospects) {
        const body = document.getElementById('prospects-body');
        body.innerHTML = '';
        
        const limit = 50;
        const displayList = prospects.slice(0, limit);
        
        displayList.forEach(p => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>
                    <strong>${p.company}</strong><br>
                    <small>${p.domain}</small>
                </td>
                <td>${p.emails.replace(/;/g, '<br>')}</td>
                <td><small>${p.categories || ''}</small></td>
                <td>
                    <a href="http://${p.domain}" target="_blank" class="nav-link" style="color: #007bff; font-size: 0.8em;">Visit</a>
                </td>
            `;
            body.appendChild(tr);
        });

        const info = document.getElementById('search-results-info');
        info.textContent = `Showing ${displayList.length} of ${prospects.length} prospects.`;
    }

    document.getElementById('prospect-search').addEventListener('input', filterProspects);
    document.getElementById('category-filter').addEventListener('change', filterProspects);

    function filterProspects() {
        const query = document.getElementById('prospect-search').value.toLowerCase();
        const cat = document.getElementById('category-filter').value;
        
        const filtered = allProspects.filter(p => {
            const matchesQuery = !query || 
                p.company.toLowerCase().includes(query) || 
                p.domain.toLowerCase().includes(query) || 
                p.emails.toLowerCase().includes(query) || 
                p.categories.toLowerCase().includes(query);
            
            const matchesCat = !cat || (p.categories && p.categories.includes(cat));
            
            return matchesQuery && matchesCat;
        });
        
        renderProspects(filtered);
    }

    window.addEventListener('DOMContentLoaded', () => {
        console.log("Dashboard Page Loaded");
        fetchReport();
    });

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
        
        // Update Worker Stats
        const workerStats = stats.worker_stats || {};
        const workerBody = document.getElementById('worker-stats-body');
        const workerContainer = document.getElementById('worker-stats-container');
        workerBody.innerHTML = '';
        const totalProcessed = Object.values(workerStats).reduce((a, b) => a + b, 0);
        
        if (totalProcessed > 0) {
            Object.entries(workerStats).sort((a,b) => b[1] - a[1]).forEach(([worker, count]) => {
                const share = ((count / totalProcessed) * 100).toFixed(1) + '%';
                const tr = document.createElement('tr');
                tr.innerHTML = `<td>${worker}</td><td>${count.toLocaleString()}</td><td>${share}</td>`;
                workerBody.appendChild(tr);
            });
            workerContainer.style.display = 'block';
        }

                // Update downloads

                document.getElementById('email-count-display').textContent = (stats.emails_found_count || 0).toLocaleString();

                document.getElementById('download-link').href = `/exports/${stats.campaign_name || campaign}-emails.csv`;

            }

        </script>

        