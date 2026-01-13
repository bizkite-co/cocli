let allProspects = [];
let categories = new Set();

function checkAuth() {
    const idToken = localStorage.getItem('cocli_id_token');
    
    // Check if token exists and is valid (not expired)
    let isExpired = true;
    if (idToken) {
        try {
            const payload = JSON.parse(atob(idToken.split('.')[1]));
            const now = Math.floor(Date.now() / 1000);
            if (payload.exp > now) {
                isExpired = false;
            } else {
                console.warn("checkAuth: Token expired.");
            }
        } catch (e) {
            console.error("checkAuth: Failed to parse token.");
        }
    }

    if (!isExpired) {
        return true;
    }

    // Token is missing or expired - redirect to login
    localStorage.removeItem('cocli_id_token');
    localStorage.removeItem('cocli_access_token');

    const config = window.COCLI_CONFIG;
    if (!config || !config.userPoolId || !config.userPoolClientId) {
        console.error("checkAuth: Cognito configuration missing from COCLI_CONFIG.");
        return false;
    }

    const redirectUri = window.location.origin + '/auth-callback/index.html';
    const loginUrl = `https://auth.turboheat.net/oauth2/authorize?client_id=${config.userPoolClientId}&response_type=token&scope=openid+email+profile&redirect_uri=${encodeURIComponent(redirectUri)}`;
    
    console.log("checkAuth: Redirecting to login:", loginUrl);
    window.location.href = loginUrl;
    return false;
}

function logout() {
    localStorage.removeItem('cocli_id_token');
    localStorage.removeItem('cocli_access_token');
    const config = window.COCLI_CONFIG;
    const logoutUrl = `https://auth.turboheat.net/logout?client_id=${config.userPoolClientId}&logout_uri=${encodeURIComponent(window.location.origin + '/signout')}`;
    window.location.href = logoutUrl;
}

async function fetchReport() {
    const urlParams = new URLSearchParams(window.location.search);
    const campaign = urlParams.get('campaign') || window.CAMPAIGN_NAME || 'turboship';
    document.getElementById('campaign-display').textContent = campaign;
    
    try {
        const version = Date.now();
        // Fetch base report and exclusions (needed for card filtering)
        const [stats, exclData] = await Promise.all([
            fetch(`/reports/${campaign}.json?v=${version}`).then(r => r.json()),
            fetch(`/reports/exclusions.json?v=${version}`).then(async r => {
                if (!r.ok) return {exclusions: []};
                const contentType = r.headers.get("content-type");
                if (!contentType || !contentType.includes("application/json")) return {exclusions: []};
                try {
                    return await r.json();
                } catch (e) {
                    return {exclusions: []};
                }
            })
        ]);

        // Merge exclusions so the card rendering logic works correctly
        const combinedStats = { ...stats, ...exclData };
        
        renderReport(combinedStats, campaign);
        fetchProspects(combinedStats.campaign_name || campaign);
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
                // Dead-simple filter: only show companies that have keywords
                allProspects = results.data.filter(p => p.keywords && p.keywords.trim() !== "");
                
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
                if (filter) {
                    filter.innerHTML = '<option value="">All Categories</option>';
                    Array.from(categories).sort().forEach(cat => {
                        const opt = document.createElement('option');
                        opt.value = cat;
                        opt.textContent = cat;
                        filter.appendChild(opt);
                    });
                }

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

function formatPhoneNumber(phoneNumberString) {
    if (!phoneNumberString) return '';
    const cleaned = ('' + phoneNumberString).replace(/\D/g, '');
    
    // Check if it is a US number
    if (cleaned.length === 10) {
        const match = cleaned.match(/^(\d{3})(\d{3})(\d{4})$/);
        return `(${match[1]}) ${match[2]}-${match[3]}`;
    } else if (cleaned.length === 11 && cleaned[0] === '1') {
        const match = cleaned.match(/^1(\d{3})(\d{3})(\d{4})$/);
        return `(${match[1]}) ${match[2]}-${match[3]}`;
    }
    
    return phoneNumberString;
}

function cleanDomain(domain) {
    if (!domain) return '';
    return domain.split('?')[0];
}

function createCompanyCard(p, index) {
    const displayDomain = cleanDomain(p.domain);
    const formattedPhone = formatPhoneNumber(p.phone);

    const servicesHtml = p.services ? `
        <div class="panel-section">
            <button class="toggle-btn" onclick="togglePanel('services-${index}')">Services (+)</button>
            <div id="services-${index}" class="panel-content" style="display:none;">
                <span class="info-data">${p.services.split(';').map(s => s.trim()).join(', ')}</span>
            </div>
        </div>` : '';

    const productsHtml = p.products ? `
        <div class="panel-section">
            <button class="toggle-btn" onclick="togglePanel('products-${index}')">Products (+)</button>
            <div id="products-${index}" class="panel-content" style="display:none;">
                <span class="info-data">${p.products.split(';').map(s => s.trim()).join(', ')}</span>
            </div>
        </div>` : '';

    const keywordsHtml = p.keywords ? `
        <div class="info-row">
            <strong>Keywords:</strong> 
            <div class="keyword-tags">
                ${p.keywords.split(';').map(k => `<span class="keyword-tag" onclick="filterByKeyword('${k.trim()}')" style="cursor:pointer;">${k.trim()}</span>`).join(' ')}
            </div>
        </div>` : '';

    return `
        <div class="company-card">
            <div class="card-header">
                <h3>${p.company}</h3>
                <a href="http://${displayDomain}" target="_blank" class="domain-link">${displayDomain}</a>
            </div>
            <div class="card-body">
                <div class="info-row">
                    <strong>Emails:</strong> 
                    <div class="email-list">${p.emails.split(';').map(e => `<div>${e.trim()}</div>`).join('')}</div>
                </div>
                ${formattedPhone ? `<div class="info-row"><strong>Phone:</strong> <span class="phone-number">${formattedPhone}</span></div>` : ''}
                ${p.categories ? `<div class="info-row"><strong>Categories:</strong> <span class="info-data"><small>${p.categories}</small></span></div>` : ''}
                ${keywordsHtml}
                
                <div class="expandable-area">
                    ${servicesHtml}
                    ${productsHtml}
                </div>
            </div>
        </div>
    `;
}

function filterByKeyword(keyword) {
    const queryInput = document.getElementById('prospect-search');
    if (queryInput) {
        queryInput.value = keyword;
        filterProspects();
        // Scroll to search box
        queryInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
}

function renderProspects(prospects) {
    const container = document.getElementById('prospects-container');
    if (!container) return;
    container.innerHTML = '';
    
    const limit = 100;
    const displayList = prospects.slice(0, limit);
    
    displayList.forEach((p, index) => {
        const div = document.createElement('div');
        div.innerHTML = createCompanyCard(p, index);
        container.appendChild(div.firstElementChild);
    });

    const info = document.getElementById('search-results-info');
    if (info) {
        info.textContent = `Showing ${displayList.length} of ${prospects.length} prospects.`;
    }
}

function filterProspects() {
    const queryInput = document.getElementById('prospect-search');
    const catFilter = document.getElementById('category-filter');
    const clearBtn = document.getElementById('clear-search');
    if (!queryInput || !catFilter) return;

    const query = queryInput.value.toLowerCase();
    const cat = catFilter.value;
    
    // Toggle clear button
    if (clearBtn) {
        clearBtn.style.display = query ? 'block' : 'none';
    }

    let filtered = allProspects.filter(p => {
        const matchesQuery = !query || 
            (p.company && p.company.toLowerCase().includes(query)) || 
            (p.domain && p.domain.toLowerCase().includes(query)) || 
            (p.emails && p.emails.toLowerCase().includes(query)) || 
            (p.categories && p.categories.toLowerCase().includes(query)) ||
            (p.services && p.services.toLowerCase().includes(query)) ||
            (p.products && p.products.toLowerCase().includes(query)) ||
            (p.keywords && p.keywords.toLowerCase().includes(query));
        
        const matchesCat = !cat || (p.categories && p.categories.includes(cat));
        
        return matchesQuery && matchesCat;
    });

    // Sort to prioritize keyword matches
    if (query) {
        filtered.sort((a, b) => {
            const aKeywords = (a.keywords || '').toLowerCase();
            const bKeywords = (b.keywords || '').toLowerCase();
            const aHasKeyword = aKeywords.includes(query);
            const bHasKeyword = bKeywords.includes(query);

            if (aHasKeyword && !bHasKeyword) return -1;
            if (!aHasKeyword && bHasKeyword) return 1;
            return 0;
        });
    }
    
    renderProspects(filtered);
}

function renderReport(stats, campaign) {
    const body = document.getElementById('report-body');
    if (!body) return;
    body.innerHTML = '';
    
    const rows = [
        { stage: 'Active Enrichment Workers (Fargate)', count: stats.active_fargate_tasks || 0, details: (stats.active_fargate_tasks > 0 ? 'Running' : 'Stopped'), badge: (stats.active_fargate_tasks > 0 ? 'status-running' : '') },
        { stage: 'Campaign Updates (SQS)', count: `${stats.command_tasks_pending || 0} Pending`, details: 'SQS', badge: (stats.command_tasks_pending > 0 ? 'status-sqs' : '') },
        { stage: 'Scrape Tasks (gm-list)', count: `${stats.scrape_tasks_pending || 0} / ${stats.scrape_tasks_inflight || 0} Active`, details: 'SQS', badge: (stats.scrape_tasks_pending > 0 ? 'status-sqs' : '') },
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
    const reportTable = document.getElementById('report-table');
    if (reportTable) reportTable.style.display = 'table';
    
    const lastUpdatedTime = document.getElementById('last-updated-time');
    if (lastUpdatedTime) lastUpdatedTime.textContent = new Date(stats.last_updated).toLocaleString();
    
    const lastUpdatedText = document.getElementById('last-updated-text');
    if (lastUpdatedText) lastUpdatedText.style.display = 'block';
    
    // Update Worker Stats
    const workerStats = stats.worker_stats || {};
    const workerBody = document.getElementById('worker-stats-body');
    const workerContainer = document.getElementById('worker-stats-container');
    if (workerBody && workerContainer) {
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
    }

    const emailCountDisplay = document.getElementById('email-count-display');
    if (emailCountDisplay) emailCountDisplay.textContent = (stats.emails_found_count || 0).toLocaleString();
    
    const downloadLink = document.getElementById('download-link');
    if (downloadLink) downloadLink.href = `/exports/${stats.campaign_name || campaign}-emails.csv`;
    
    const downloadLinkJson = document.getElementById('download-link-json');
    if (downloadLinkJson) downloadLinkJson.href = `/exports/${stats.campaign_name || campaign}-emails.json`;
}

window.addEventListener('DOMContentLoaded', () => {
    if (!checkAuth()) return;

    const searchInput = document.getElementById('prospect-search');
    const filterSelect = document.getElementById('category-filter');
    if (searchInput) searchInput.addEventListener('input', filterProspects);
    if (filterSelect) filterSelect.addEventListener('change', filterProspects);
    
    fetchReport();
});

function clearSearch() {
    const queryInput = document.getElementById('prospect-search');
    if (queryInput) {
        queryInput.value = '';
        filterProspects();
        queryInput.focus();
    }
}
