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
            renderReport(stats, campaign);
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
                    document.getElementById('prospects-container').style.display = 'grid';
                    
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

    function togglePanel(id) {
        const panel = document.getElementById(id);
        if (!panel) return;
        if (panel.style.display === 'none') {
            panel.style.display = 'block';
        } else {
            panel.style.display = 'none';
        }
    }

    function createCompanyCard(p, index) {
        const servicesHtml = p.services ? `
            <div class="panel-section">
                <button class="toggle-btn" onclick="togglePanel('services-${index}')">Services (+)</button>
                <div id="services-${index}" class="panel-content" style="display:none;">
                    ${p.services.split(';').map(s => `<span>${s.trim()}</span>`).join(', ')}
                </div>
            </div>` : '';

        const productsHtml = p.products ? `
            <div class="panel-section">
                <button class="toggle-btn" onclick="togglePanel('products-${index}')">Products (+)</button>
                <div id="products-${index}" class="panel-content" style="display:none;">
                    ${p.products.split(';').map(s => `<span>${s.trim()}</span>`).join(', ')}
                </div>
            </div>` : '';

        return `
            <div class="company-card">
                <div class="card-header">
                    <h3>${p.company}</h3>
                    <a href="http://${p.domain}" target="_blank" class="domain-link">${p.domain}</a>
                </div>
                <div class="card-body">
                    <div class="info-row">
                        <strong>Emails:</strong> 
                        <div class="email-list">${p.emails.split(';').map(e => `<div>${e.trim()}</div>`).join('')}</div>
                    </div>
                    ${p.phone ? `<div class="info-row"><strong>Phone:</strong> ${p.phone}</div>` : ''}
                    ${p.categories ? `<div class="info-row"><strong>Categories:</strong> <small>${p.categories}</small></div>` : ''}
                    
                    <div class="expandable-area">
                        ${servicesHtml}
                        ${productsHtml}
                    </div>
                </div>
            </div>
        `;
    }

    function renderProspects(prospects) {
        const container = document.getElementById('prospects-container');
        container.innerHTML = '';
        
        const limit = 100;
        const displayList = prospects.slice(0, limit);
        
        displayList.forEach((p, index) => {
            const div = document.createElement('div');
            div.innerHTML = createCompanyCard(p, index);
            container.appendChild(div.firstElementChild);
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
                p.categories.toLowerCase().includes(query) ||
                p.services.toLowerCase().includes(query) ||
                p.products.toLowerCase().includes(query);
            
            const matchesCat = !cat || (p.categories && p.categories.includes(cat));
            
            return matchesQuery && matchesCat;
        });
        
        renderProspects(filtered);
    }

    window.addEventListener('DOMContentLoaded', () => {
        fetchReport();
    });

    function renderReport(stats, campaign) {
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

        document.getElementById('email-count-display').textContent = (stats.emails_found_count || 0).toLocaleString();
        document.getElementById('download-link').href = `/exports/${stats.campaign_name || campaign}-emails.csv`;
        document.getElementById('download-link-json').href = `/exports/${stats.campaign_name || campaign}-emails.json`;
    }
</script>