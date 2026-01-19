let activeMap = null;
let activeMarker = null;
let statsData = null;

function logout() {
    localStorage.removeItem('cocli_id_token');
    localStorage.removeItem('cocli_access_token');
    localStorage.removeItem('cocli_pending_changes');
    const config = window.COCLI_CONFIG;
    if (config && config.userPoolId) {
        const domain = "auth.turboheat.net";
        const clientId = config.userPoolClientId;
        const logoutUri = window.location.origin + '/signout/index.html';
        window.location.href = `https://${domain}/logout?client_id=${clientId}&logout_uri=${encodeURIComponent(logoutUri)}`;
    } else {
        window.location.href = '/signout/index.html';
    }
}

async function fetchConfig() {
    const urlParams = new URLSearchParams(window.location.search);
    const campaign = urlParams.get('campaign') || window.CAMPAIGN_NAME || 'turboship';
    document.getElementById('campaign-display').textContent = campaign;
    
    try {
        // Fetch all parts in parallel
        const version = Date.now();
        const paths = [
            `/reports/${campaign}.json?v=${version}`,
            `/reports/exclusions.json?v=${version}`,
            `/reports/queries.json?v=${version}`,
            `/reports/locations.json?v=${version}`
        ];

        const [baseRes, exclRes, queryRes, locRes] = await Promise.all(
            paths.map(p => fetch(p).then(async r => {
                if (!r.ok) return {};
                const contentType = r.headers.get("content-type");
                if (!contentType || !contentType.includes("application/json")) {
                    console.warn(`Path ${p} did not return JSON. Content-Type: ${contentType}`);
                    return {};
                }
                try {
                    return await r.json();
                } catch (e) {
                    console.error(`Error parsing JSON from ${p}:`, e);
                    return {};
                }
            }))
        );

        // Merge granular data into the main stats object
        statsData = {
            ...baseRes,
            ...exclRes,
            ...queryRes,
            ...locRes
        };

        if (!statsData.campaign_name && !baseRes.campaign_name) {
             console.warn('Base report data not found, some stats might be missing.');
        }
        
        renderConfig(statsData, campaign);
    } catch (error) {
        console.error("Failed to fetch configuration:", error);
    }
}

window.addEventListener('DOMContentLoaded', () => {
    if (typeof checkAuth === 'function') {
        if (!checkAuth()) return;
    }
    console.log("Config Page Loaded");
    fetchConfig();
    updatePendingUI();
});

let pendingChanges = JSON.parse(localStorage.getItem('cocli_pending_changes') || '[]');

function savePendingToStorage() {
    localStorage.setItem('cocli_pending_changes', JSON.stringify(pendingChanges));
}

function addPendingChange(type, value) {
    if (!value) return;
    const cmd = `add-${type} "${value}"`;
    if (!pendingChanges.includes(cmd)) {
        pendingChanges.push(cmd);
        savePendingToStorage();
        updatePendingUI();
        
        // Add visual feedback to the lists
        renderDraftItem(type, value);
    }
    if (type === 'query') document.getElementById('new-query').value = '';
    if (type === 'location') document.getElementById('new-location').value = '';
    if (type === 'exclude') document.getElementById('new-exclude').value = '';
}

function renderDraftItem(type, value) {
    if (type === 'exclude') {
        const list = document.getElementById('exclusions-list');
        if (!list) return;
        const li = document.createElement('li');
        li.className = 'list-item-editable draft';
        li.innerHTML = `<span><strong>${value}</strong> <br><small style="color:var(--status-sqs)">Pending addition...</small></span>`;
        list.prepend(li);
    } else if (type === 'query') {
        const list = document.getElementById('queries-list');
        if (!list) return;
        const li = document.createElement('li');
        li.className = 'list-item-editable draft';
        li.innerHTML = `<span>${value} <br><small style="color:var(--status-sqs)">Pending addition...</small></span>`;
        list.prepend(li);
    }
}

function removeExisting(type, value, elementId) {
    const confirmArea = document.getElementById(`confirm-${elementId}`);
    
    if (confirmArea) {
        confirmArea.innerHTML = `
            <div class="confirm-box">
                <span>Remove this?</span>
                <div class="confirm-buttons">
                    <button class="btn-confirm" onclick="confirmRemove('${type}', '${value}', '${elementId}')">Yes</button>
                    <button class="btn-cancel" onclick="cancelRemove('${elementId}')">No</button>
                </div>
            </div>
        `;
    }
}

function confirmRemove(type, value, elementId) {
    const cmd = `remove-${type} "${value}"`;
    if (!pendingChanges.includes(cmd)) {
        pendingChanges.push(cmd);
        savePendingToStorage();
        updatePendingUI();
        
        // Mark existing item as draft-remove
        const el = document.getElementById(`confirm-${elementId}`).parentElement;
        if (el) {
            el.classList.add('draft-remove');
            const label = el.querySelector('span');
            if (label) label.style.textDecoration = 'line-through';
        }
    }
    cancelRemove(elementId);
}

function cancelRemove(elementId) {
    const confirmArea = document.getElementById(`confirm-${elementId}`);
    if (confirmArea) confirmArea.innerHTML = '';
}

function updatePendingUI() {
    const container = document.getElementById('pending-changes-container');
    const box = document.getElementById('pending-commands-box');
    const countBadge = document.getElementById('pending-count');
    
    if (pendingChanges.length > 0) {
        if (container) container.style.display = 'block';
        if (box) box.textContent = pendingChanges.join('\n');
        if (countBadge) countBadge.textContent = pendingChanges.length;
    } else {
        if (container) container.style.display = 'none';
    }
}

async function submitChanges() {
    // Proactively check auth before doing anything
    if (typeof checkAuth === 'function') {
        if (!checkAuth()) return;
    }

    const btn = document.querySelector('.btn-submit');
    const statusMsg = document.getElementById('submission-status');
    const originalText = btn.textContent;
    
    btn.disabled = true;
    btn.textContent = 'Connecting...';
    
    if (statusMsg) {
        statusMsg.style.display = 'block';
        statusMsg.className = 'status-info';
        statusMsg.textContent = 'Initializing AWS connection...';
    }

    const config = window.COCLI_CONFIG;
    const idToken = localStorage.getItem('cocli_id_token');
    
    if (!idToken) {
        alert("Session expired. Please log in again.");
        window.location.href = '/index.html';
        return;
    }

    try {
        AWS.config.region = config.region;
        const loginKey = `cognito-idp.${config.region}.amazonaws.com/${config.userPoolId}`;
        
        AWS.config.credentials = new AWS.CognitoIdentityCredentials({
            IdentityPoolId: config.identityPoolId,
            Logins: { [loginKey]: idToken }
        });

        await new Promise((resolve, reject) => {
            AWS.config.credentials.get((err) => {
                if (err) reject(err);
                else resolve();
            });
        });

        const sqs = new AWS.SQS();
        const total = pendingChanges.length;
        
        for (let i = 0; i < total; i++) {
            const cmd = pendingChanges[i];
            if (statusMsg) statusMsg.textContent = `Submitting command ${i+1} of ${total}...`;
            
            await sqs.sendMessage({
                QueueUrl: config.commandQueueUrl,
                MessageBody: JSON.stringify({
                    command: cmd,
                    timestamp: new Date().toISOString()
                })
            }).promise();
        }

        if (statusMsg) {
            statusMsg.className = 'status-success';
            statusMsg.textContent = `Successfully submitted ${total} changes! Workers will process them shortly.`;
        }
        
        // Keep the "draft" items but maybe change their label
        document.querySelectorAll('.draft, .draft-remove').forEach(el => {
            const small = el.querySelector('small');
            if (small) small.textContent = 'Submitted to queue...';
        });

        pendingChanges = [];
        savePendingToStorage();
        updatePendingUI();
        
        // Hide success message after 10 seconds
        setTimeout(() => {
            if (statusMsg) statusMsg.style.display = 'none';
        }, 10000);

    } catch (error) {
        console.error("Failed to submit changes:", error);
        if (statusMsg) {
            statusMsg.className = 'status-error';
            statusMsg.textContent = 'Error: ' + error.message;
        }
        btn.textContent = originalText;
        btn.disabled = false;
    } finally {
        btn.textContent = originalText;
        btn.disabled = false;
    }
}

function clearPendingChanges() {
    pendingChanges = [];
    savePendingToStorage();
    updatePendingUI();
    // Refresh to clear visual drafts
    fetchConfig();
}

function toggleMap(element, lat, lon, tileId) {
    // Remove active class from others
    document.querySelectorAll('.location-item').forEach(el => el.classList.remove('active'));
    
    const mapContainer = element.querySelector('.location-map-bg');
    
    // If clicking same item, just deactivate
    if (element.dataset.mapActive === 'true') {
        element.dataset.mapActive = 'false';
        return;
    }

    // Reset all others
    document.querySelectorAll('.location-item').forEach(el => el.dataset.mapActive = 'false');
    
    element.classList.add('active');
    element.dataset.mapActive = 'true';

    // Move map to this element
    let mapEl = document.getElementById('shared-map');
    if (!mapEl) {
        mapEl = document.createElement('div');
        mapEl.id = 'shared-map';
        mapEl.style.width = '100%';
        mapEl.style.height = '100%';
        document.body.appendChild(mapEl);
    }
    
    mapContainer.appendChild(mapEl);
    mapEl.style.display = 'block';

    if (!activeMap) {
        activeMap = L.map('shared-map', {
            zoomControl: false,
            attributionControl: false
        }).setView([lat, lon], 11);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(activeMap);
        activeMarker = L.marker([lat, lon]).addTo(activeMap);
    } else {
        activeMap.setView([lat, lon], 11);
        activeMarker.setLatLng([lat, lon]);
        activeMap.invalidateSize();
    }
}

function filterLocations() {
    const query = document.getElementById('location-search').value.toLowerCase();
    renderConfig(statsData, document.getElementById('campaign-display').textContent, query);
}

function renderConfig(stats, campaign, filterQuery = '') {
    document.getElementById('proximity-display').textContent = stats.proximity || '30';
    
    // Update Report Table
    const reportBody = document.getElementById('report-body');
    const reportTable = document.getElementById('report-table');
    if (reportBody) {
        reportBody.innerHTML = '';
        const rows = [
            { stage: 'Scrape Tasks (gm-list)', count: `${stats.scrape_tasks_pending || 0} / ${stats.scrape_tasks_inflight || 0} Active`, details: 'SQS', badge: (stats.scrape_tasks_pending > 0 ? 'status-sqs' : '') },
            { stage: 'GM List Items (gm-details)', count: `${stats.gm_list_item_pending || 0} / ${stats.gm_list_item_inflight || 0} Active`, details: 'SQS', badge: (stats.gm_list_item_pending > 0 ? 'status-sqs' : '') },
            { stage: 'Website Enrichment (Pending)', count: (stats.enrichment_pending || 0).toLocaleString(), details: 'Queue', badge: (stats.enrichment_pending > 0 ? 'status-sqs' : '') },
            { stage: 'Website Enrichment (Completed)', count: (stats.remote_enrichment_completed || stats.completed_count || 0).toLocaleString(), details: 'S3', badge: '' },
            { stage: 'Total Target Tiles', count: (stats.total_target_tiles || 0).toLocaleString(), details: 'Campaign', badge: '' },
            { stage: 'Total Scraped Tiles', count: (stats.total_scraped_tiles || 0).toLocaleString(), details: stats.total_target_tiles ? `${((stats.total_scraped_tiles / stats.total_target_tiles) * 100).toFixed(1)}%` : '0%', badge: '' },
            { stage: 'Prospects Found', count: (stats.prospects_count || 0).toLocaleString(), details: 'Local Index', badge: '' }
        ];

        rows.forEach(row => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${row.stage}</td>
                <td>${row.count}</td>
                <td><span class="status-badge ${row.badge}">${row.details}</span></td>
            `;
            reportBody.appendChild(tr);
        });
        if (reportTable) reportTable.style.display = 'table';
        const loading = document.getElementById('report-loading');
        if (loading) loading.style.display = 'none';
    }

    // Update Phrase Progress
    const phraseBody = document.getElementById('phrase-progress-body');
    const phraseContainer = document.getElementById('phrase-progress-container');
    if (phraseBody && stats.scraped_per_phrase) {
        phraseBody.innerHTML = '';
        Object.entries(stats.scraped_per_phrase).forEach(([phrase, count]) => {
            const pct = stats.total_target_tiles ? ((count / stats.total_target_tiles) * 100).toFixed(1) + '%' : '0%';
            const tr = document.createElement('tr');
            tr.innerHTML = `<td>${phrase}</td><td>${count.toLocaleString()}</td><td>${pct}</td>`;
            phraseBody.appendChild(tr);
        });
        phraseContainer.style.display = 'block';
    }

    // Update Worker Heartbeats
    const hbBody = document.getElementById('worker-heartbeats-body');
    const hbContainer = document.getElementById('worker-heartbeats-container');
    if (hbBody && stats.worker_heartbeats) {
        hbBody.innerHTML = '';
        stats.worker_heartbeats.sort((a,b) => new Date(b.timestamp) - new Date(a.timestamp)).forEach(hb => {
            const tr = document.createElement('tr');
            const lastSeen = new Date(hb.timestamp).toLocaleTimeString();
            const cpu = hb.system ? `${hb.system.cpu_percent}%` : 'N/A';
            const mem = hb.system ? `${hb.system.memory_percent}%` : 'N/A';
            const tasks = hb.workers ? `${hb.workers.scrape}/${hb.workers.details}/${hb.workers.enrichment}` : 'N/A';
            
            // Check if stale (> 30 mins)
            const isStale = (Date.now() - new Date(hb.timestamp)) > 30 * 60 * 1000;
            const statusClass = isStale ? 'status-error' : 'status-running';
            const statusText = isStale ? 'Stale' : 'Active';

            tr.innerHTML = `
                <td><strong>${hb.hostname}</strong></td>
                <td><span class="status-badge ${statusClass}">${statusText}</span></td>
                <td>${tasks}</td>
                <td>${cpu} / ${mem}</td>
                <td>${lastSeen}</td>
            `;
            hbBody.appendChild(tr);
        });
        hbContainer.style.display = 'block';
    }

    // Update Slugs Datalist
    const datalist = document.getElementById('slugs-datalist');
    if (datalist && stats.all_slugs) {
        datalist.innerHTML = stats.all_slugs.map(s => `<option value="${s}">`).join('');
    }

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

    // Update queries
    const queriesList = document.getElementById('queries-list');
    if (queriesList) {
        queriesList.innerHTML = '';
        
        // 1. Render actual existing queries
        (stats.queries || []).forEach((q, idx) => {
            const li = document.createElement('li');
            li.className = 'list-item-editable';
            const elId = `query-${idx}`;
            
            const removeCmd = `cocli campaign remove-query "${q}" --campaign ${campaign}`;
            const isPendingRemove = pendingChanges.includes(removeCmd);
            
            if (isPendingRemove) {
                li.classList.add('draft-remove');
            }

            li.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
                    <span style="${isPendingRemove ? 'text-decoration: line-through;' : ''}">
                        ${q}
                        ${isPendingRemove ? '<br><small style="color:var(--status-error)">Pending removal...</small>' : ''}
                    </span>
                    ${!isPendingRemove ? `<button class="btn-remove" onclick="removeExisting('query', '${q}', '${elId}')">×</button>` : ''}
                </div>
                <div id="confirm-${elId}" class="delete-confirm-area"></div>
            `;
            queriesList.appendChild(li);
        });

        // 2. Render new pending queries (drafts)
        pendingChanges.forEach(cmd => {
            if (cmd.includes('add-query')) {
                const match = cmd.match(/add-query "([^"]+)"/);
                if (match) {
                    const value = match[1];
                    renderDraftItem('query', value);
                }
            }
        });
    }

    // Update locations
    const locationsList = document.getElementById('locations-list');
    if (locationsList) {
        locationsList.innerHTML = '';
        
        const filtered = (stats.locations || []).filter(loc => 
            !filterQuery || loc.name.toLowerCase().includes(filterQuery)
        );

        filtered.forEach((loc, idx) => {
            const li = document.createElement('li');
            li.className = 'location-item';
            const elId = `loc-${idx}`;
            
            let statusIcon = loc.valid_geocode ? '✅' : '❓';
            let tileDisplay = loc.tile_id ? 
                `<span class="tile-id-badge">${loc.tile_id}</span>` : 
                '<span style="color: #999;">No Tile</span>';

            li.innerHTML = `
                <div class="location-map-bg"></div>
                <div class="location-content" onclick="toggleMap(this.parentElement, ${loc.lat}, ${loc.lon}, '${loc.tile_id}')">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                        <div>
                            <strong style="font-size: 1.1em;">${loc.name}</strong><br>
                            <span style="font-size: 0.85em; color: #555;">Geo: ${statusIcon} | Prox: ${loc.proximity}mi</span>
                        </div>
                        <div style="text-align: right;">
                            ${tileDisplay}
                        </div>
                    </div>
                    
                    <div class="stats-grid">
                        <div class="stat-box">
                            <small>Tiles</small><br><strong>${loc.tiles_count || 0}</strong>
                        </div>
                        <div class="stat-box">
                            <small>Scraped</small><br><strong>${loc.scraped_tiles_count || 0}</strong>
                        </div>
                        <div class="stat-box">
                            <small>Prospects</small><br><strong>${loc.prospects_count || 0}</strong>
                        </div>
                    </div>

                    <div id="confirm-${elId}" class="delete-confirm-area"></div>
                </div>
                <button class="btn-remove" style="position: absolute; top: 10px; right: 10px; z-index: 10;" 
                        onclick="event.stopPropagation(); removeExisting('location', '${loc.name}', '${elId}')">×</button>
            `;
            locationsList.appendChild(li);
        });
    }
    
    // Update exclusions
    const exclusionsList = document.getElementById('exclusions-list');
    if (exclusionsList) {
        exclusionsList.innerHTML = '';
        
        // 1. Render actual existing exclusions
        (stats.exclusions || []).forEach((exc, idx) => {
            const li = document.createElement('li');
            li.className = 'list-item-editable';
            const elId = `exclude-${idx}`;
            const target = exc.company_slug || exc.domain;
            
            // Check if this item is marked for removal in pendingChanges
            const removeCmd = `cocli campaign remove-exclude "${target}" --campaign ${campaign}`;
            const isPendingRemove = pendingChanges.includes(removeCmd);
            
            if (isPendingRemove) {
                li.classList.add('draft-remove');
            }

            li.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
                    <span style="${isPendingRemove ? 'text-decoration: line-through;' : ''}">
                        <strong>${target}</strong> ${exc.reason ? `<br><small style="color:#666">${exc.reason}</small>` : ''}
                        ${isPendingRemove ? '<br><small style="color:var(--status-error)">Pending removal...</small>' : ''}
                    </span>
                    ${!isPendingRemove ? `<button class="btn-remove" onclick="removeExisting('exclude', '${target}', '${elId}')">×</button>` : ''}
                </div>
                <div id="confirm-${elId}" class="delete-confirm-area"></div>
            `;
            exclusionsList.appendChild(li);
        });

        // 2. Render new pending exclusions (drafts)
        pendingChanges.forEach(cmd => {
            if (cmd.includes('add-exclude')) {
                const match = cmd.match(/add-exclude "([^"]+)"/);
                if (match) {
                    const value = match[1];
                    renderDraftItem('exclude', value);
                }
            }
        });
    }
}
