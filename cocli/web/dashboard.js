/**
 * Shared across dashboard pages, which each include a different subset of
 * _includes/components/*.njk - not every element this file looks up exists
 * on every page. Guard DOM lookups (`if (el) {...}`) instead of an early
 * `return` keyed on one element, or you'll silently skip unrelated logic
 * later in the same function on pages that don't have that element. See
 * web/README.md for the page/component map and the auth setup this file
 * depends on (checkAuth/logout are defined globally in layout.njk).
 */
let allProspects = [];
let categories = new Set();

async function fetchReport() {
    const urlParams = new URLSearchParams(window.location.search);
    const campaign = urlParams.get('campaign') || window.CAMPAIGN_NAME;
    if (!campaign) {
        console.error("No campaign name found.");
        return;
    }
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
        const exportCampaign = combinedStats.campaign_name || campaign;

        // Resolved once and shared: the download panel and the prospect
        // cards must agree on whether the refined list exists, or the
        // displayed count and the displayed cards would silently disagree.
        const leadFilterInfo = await resolveLeadFilterInfo(exportCampaign);

        renderReport(combinedStats, campaign, exportCampaign, leadFilterInfo);
        fetchProspects(exportCampaign, leadFilterInfo);
    } catch (error) {
        document.getElementById('report-loading').style.display = 'none';
        const errDiv = document.getElementById('report-error');
        errDiv.textContent = error.message;
        errDiv.style.display = 'block';
    }
}

async function fetchProspects(campaign, leadFilterInfo) {
    try {
        // Same data source the download panel is showing - a campaign
        // without a filter yet falls back to the raw export so the card
        // list still works, exactly like setupDownloadPanel's fallback.
        const csvUrl = leadFilterInfo && leadFilterInfo.available
            ? `/exports/${campaign}-leadfilter-in.csv?v=${Date.now()}`
            : `/exports/${campaign}-emails.csv?v=${Date.now()}`;
        Papa.parse(csvUrl, {
            download: true,
            header: true,
            skipEmptyLines: true,
            complete: function(results) {
                const config = window.COCLI_CONFIG || {};
                const isStrict = config.strictKeywordFilter === true;

                // If strictKeywordFilter is enabled, only show those with keywords
                if (isStrict) {
                    allProspects = results.data.filter(p => p.keywords && p.keywords.trim() !== "");
                } else {
                    allProspects = results.data;
                }

                document.getElementById('prospects-loading').style.display = 'none';
                document.getElementById('prospects-container').style.display = 'grid';

                // Authoritative count: renderReport's own count is only ever
                // a provisional guess from stats.json (which reflects the
                // raw export, not whichever CSV actually got used here).
                const countDisplay = document.getElementById('prospect-count-display');
                if (countDisplay) countDisplay.textContent = allProspects.length.toLocaleString();

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

    const tagsHtml = p.tags ? `
        <div class="info-row">
            <strong>Tags:</strong> 
            <div class="keyword-tags">
                ${p.tags.split(';').map(k => `<span class="keyword-tag" onclick="filterByKeyword('${k.trim()}')" style="cursor:pointer;">${k.trim()}</span>`).join(' ')}
            </div>
        </div>` : '';

    const locationHtml = (p.city || p.state) ? `
        <div class="info-row">
            <strong>Location:</strong> 
            <span class="info-data">${[p.city, p.state].filter(Boolean).join(', ')}</span>
        </div>` : '';

    const ratingHtml = p.rating ? `
        <div class="info-row">
            <strong>Rating:</strong> 
            <span class="rating-value">${p.rating} ⭐ (${p.reviews})</span>
            ${p.gmb_url ? `
                <a href="${p.gmb_url}" target="_blank" class="gmb-icon-link" title="View on Google Maps">
                    <i class="fa-solid fa-map-location-dot"></i>
                </a>` : ''}
        </div>` : (p.gmb_url ? `
        <div class="info-row">
            <strong>Maps:</strong>
            <a href="${p.gmb_url}" target="_blank" class="gmb-icon-link" title="View on Google Maps">
                <i class="fa-solid fa-map-location-dot"></i>
            </a>
        </div>` : '');

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
                ${locationHtml}
                ${ratingHtml}
                ${p.categories ? `<div class="info-row"><strong>Categories:</strong> <span class="info-data"><small>${p.categories}</small></span></div>` : ''}
                ${tagsHtml}
                
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
            (p.tags && p.tags.toLowerCase().includes(query)) ||
            (p.city && p.city.toLowerCase().includes(query)) ||
            (p.state && p.state.toLowerCase().includes(query));
        
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

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Renders a small, fixed subset of Markdown - only what
 * lead-filter-summary.md actually uses (h1/h2 headers, **bold**, bullet
 * lists, paragraphs). Not a general-purpose Markdown parser; if the
 * summary doc's structure grows beyond this, extend it deliberately
 * rather than assuming full CommonMark support. Text is HTML-escaped
 * before any markup is applied, so this stays safe even if the source
 * file is ever editable by someone other than the CLI that generates it.
 */
function renderLeadFilterSummary(markdown) {
    const lines = markdown.split(/\r?\n/);
    let html = '';
    let inList = false;
    // Soft-wrapped continuation lines (no blank line between them) belong
    // to the current paragraph/list item and must be joined BEFORE inline
    // formatting is applied - a per-line regex misses a **bold** span or a
    // bullet's own text when either wraps across physical lines (verified
    // 2026-09-14 against the real doc: it broke both ways on the first try).
    let blockLines = [];
    let blockType = null; // 'p' | 'li'

    function inlineBold(text) {
        return escapeHtml(text).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    }
    function flushBlock() {
        if (!blockLines.length) return;
        const text = inlineBold(blockLines.join(' '));
        html += blockType === 'li' ? `<li>${text}</li>` : `<p>${text}</p>`;
        blockLines = [];
        blockType = null;
    }
    function closeList() {
        if (inList) { html += '</ul>'; inList = false; }
    }

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim();
        if (!line) {
            flushBlock();
            // A blank line only ends the list if the next non-blank line
            // isn't another bullet - a blank line between two "- " items
            // is a loose list (still one list), not two separate ones.
            // Verified against the real doc, which separates its two
            // bullets exactly this way.
            const nextLine = (lines[i + 1] || '').trim();
            if (!nextLine.startsWith('- ')) closeList();
            continue;
        }
        if (line.startsWith('## ')) {
            flushBlock(); closeList();
            html += `<h2>${inlineBold(line.slice(3))}</h2>`;
        } else if (line.startsWith('# ')) {
            flushBlock(); closeList();
            html += `<h1>${inlineBold(line.slice(2))}</h1>`;
        } else if (line.startsWith('- ')) {
            flushBlock();
            if (!inList) { html += '<ul>'; inList = true; }
            blockType = 'li';
            blockLines.push(line.slice(2));
        } else {
            // A plain-text line either continues the block already open
            // (list item or paragraph) or, right after a header/blank,
            // starts a fresh paragraph. Never touches inList itself -
            // that's only ever opened/closed at a bullet, header, or
            // blank line, never inferred from a continuation line.
            if (blockType === null) blockType = 'p';
            blockLines.push(line);
        }
    }
    flushBlock();
    closeList();
    return html;
}

/**
 * Single source of truth for "has this campaign run the lead filter yet."
 * Both the download panel (renderReport) and the prospect-card list
 * (fetchProspects) need this same answer, resolved once, so the count
 * shown and the cards displayed always agree with each other - not one
 * reading the filtered list while the other silently still reads the raw
 * export.
 *
 * res.ok alone isn't enough to detect "not uploaded yet": this site's
 * CloudFront distribution serves the dashboard's own index.html (200,
 * text/html) as an error-document fallback for missing keys instead of a
 * real 404 - confirmed live 2026-09-14, the fallback page's own <script>
 * tags rendered as visible text in the summary box before this check
 * existed. A real upload is always text/markdown.
 */
async function resolveLeadFilterInfo(exportCampaign) {
    try {
        const res = await fetch(`/exports/${exportCampaign}-leadfilter-summary.md?v=${Date.now()}`);
        const contentType = res.headers.get('content-type') || '';
        if (!res.ok || !contentType.includes('text/markdown')) {
            return { available: false };
        }
        return { available: true, summaryText: await res.text() };
    } catch (e) {
        console.error('Lead filter summary check failed:', e);
        return { available: false };
    }
}

function setupDownloadPanel(exportCampaign, leadFilterInfo) {
    const titleEl = document.getElementById('download-box-title');
    const descEl = document.getElementById('download-box-description');
    const primaryLink = document.getElementById('download-link-primary');
    const secondaryLink = document.getElementById('download-link-secondary');
    const toggleRow = document.getElementById('lead-filter-toggle-row');
    const toggle = document.getElementById('lead-filter-toggle');
    const summaryEl = document.getElementById('lead-filter-summary');

    if (leadFilterInfo.available) {
        if (titleEl) titleEl.textContent = 'Refined Lead List';
        if (descEl) descEl.textContent = 'Prospects matched to this campaign, with off-topic and poor-fit results already filtered out.';
        if (primaryLink) {
            primaryLink.href = `/exports/${exportCampaign}-leadfilter-in.csv?v=${Date.now()}`;
            primaryLink.setAttribute('download', `${exportCampaign}-leadfilter-in.csv`);
            primaryLink.textContent = 'Download Refined List (CSV)';
        }
        if (secondaryLink) {
            secondaryLink.href = `/exports/${exportCampaign}-leadfilter-out.csv?v=${Date.now()}`;
            secondaryLink.setAttribute('download', `${exportCampaign}-leadfilter-out.csv`);
            secondaryLink.textContent = 'Download Excluded List (CSV)';
            secondaryLink.classList.add('button-small');
        }
        if (summaryEl) summaryEl.innerHTML = renderLeadFilterSummary(leadFilterInfo.summaryText);
        if (toggleRow) toggleRow.hidden = false;
        if (toggle && summaryEl && !toggle.dataset.wired) {
            toggle.dataset.wired = 'true';
            toggle.addEventListener('click', (e) => {
                e.preventDefault();
                summaryEl.hidden = !summaryEl.hidden;
                toggle.textContent = summaryEl.hidden ? 'Show filtering criteria' : 'Hide filtering criteria';
            });
        }
    } else {
        // No filter run for this campaign yet - fall back to the raw,
        // unfiltered export so the panel still works.
        if (titleEl) titleEl.textContent = 'Latest Email Export';
        if (descEl) descEl.textContent = 'Download the most recent list of enriched prospects with emails.';
        if (primaryLink) {
            primaryLink.href = `/exports/${exportCampaign}-emails.csv?v=${Date.now()}`;
            primaryLink.setAttribute('download', `${exportCampaign}-emails.csv`);
            primaryLink.textContent = 'Download CSV';
        }
        if (secondaryLink) {
            secondaryLink.href = `/exports/${exportCampaign}-emails.json?v=${Date.now()}`;
            secondaryLink.setAttribute('download', `${exportCampaign}-emails.json`);
            secondaryLink.textContent = 'Download JSON';
            secondaryLink.classList.remove('button-small');
        }
        if (toggleRow) toggleRow.hidden = true;
        if (summaryEl) summaryEl.hidden = true;
    }
}

function renderReport(stats, campaign, exportCampaign, leadFilterInfo) {
    // The report table (and worker stats) only exist on pages that include
    // report_table.njk / worker_stats.njk (currently just config.md) - the
    // download links and email count below are unrelated and must still
    // populate on pages (like index.md) that don't have that table.
    const body = document.getElementById('report-body');
    if (body) {
        body.innerHTML = '';

        const rows = [
            { stage: 'Active Enrichment Workers (Fargate)', count: stats.active_fargate_tasks || 0, details: (stats.active_fargate_tasks > 0 ? 'Running' : 'Stopped'), badge: (stats.active_fargate_tasks > 0 ? 'status-running' : '') },
            { stage: 'Campaign Updates (SQS)', count: `${stats.command_tasks_pending || 0} Pending`, details: 'SQS', badge: (stats.command_tasks_pending > 0 ? 'status-sqs' : '') },
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

        const reportLoading = document.getElementById('report-loading');
        if (reportLoading) reportLoading.style.display = 'none';
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
    }

    // Provisional count from the report stats - fetchProspects() overwrites
    // this with the real row count of whichever CSV it actually ends up
    // parsing (refined or raw) once that fetch completes, since stats.json
    // only ever reflects the raw export's count.
    const countDisplay = document.getElementById('prospect-count-display');
    if (countDisplay) countDisplay.textContent = (stats.emails_found_count || 0).toLocaleString();

    setupDownloadPanel(exportCampaign, leadFilterInfo);
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
