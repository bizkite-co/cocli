let activeMap = null;
let activeMarker = null;
let statsData = null;

async function fetchConfig() {
    const urlParams = new URLSearchParams(window.location.search);
    const campaign = urlParams.get('campaign') || window.CAMPAIGN_NAME || 'turboship';
    document.getElementById('campaign-display').textContent = campaign;
    
    try {
        const response = await fetch(`/reports/${campaign}.json?v=${Date.now()}`);
        if (!response.ok) throw new Error('Report data not found for this campaign.');
        
        statsData = await response.json();
        renderConfig(statsData, campaign);
    } catch (error) {
        console.error(error);
    }
}

window.addEventListener('DOMContentLoaded', () => {
    if (typeof checkAuth === 'function') {
        if (!checkAuth()) return;
    }
    console.log("Config Page Loaded");
    fetchConfig();
});

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
    if (type === 'exclude') document.getElementById('new-exclude').value = '';
}

function removeExisting(type, value, elementId) {
    const campaign = document.getElementById('campaign-display').textContent;
    const confirmArea = document.getElementById(`confirm-${elementId}`);
    
    if (confirmArea) {
        confirmArea.innerHTML = `
            <span style="color: #dc3545; font-weight: bold; font-size: 0.9em;">Are you sure?</span>
            <button class="btn-confirm" onclick="confirmRemove('${type}', '${value}')">Yes</button>
            <button class="btn-cancel" onclick="cancelRemove('${elementId}')">No</button>
        `;
    }
}

function confirmRemove(type, value) {
    const campaign = document.getElementById('campaign-display').textContent;
    const cmd = `cocli campaign remove-${type} "${value}" --campaign ${campaign}`;
    if (!pendingChanges.includes(cmd)) {
        pendingChanges.push(cmd);
        updatePendingUI();
    }
}

function cancelRemove(elementId) {
    const confirmArea = document.getElementById(`confirm-${elementId}`);
    if (confirmArea) confirmArea.innerHTML = '';
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

async function submitChanges() {
    const btn = document.querySelector('.btn-submit');
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Submitting...';

    const config = window.COCLI_CONFIG;
    const idToken = localStorage.getItem('cocli_id_token');
    
    if (!idToken) {
        alert("Session expired. Please log in again.");
        window.location.href = '/index.html';
        return;
    }

    try {
        // 1. Configure AWS SDK with Identity Pool
        AWS.config.region = config.region;
        const loginKey = `cognito-idp.${config.region}.amazonaws.com/${config.userPoolId}`;
        
        AWS.config.credentials = new AWS.CognitoIdentityCredentials({
            IdentityPoolId: config.identityPoolId,
            Logins: {
                [loginKey]: idToken
            }
        });

        // 2. Refresh credentials
        await new Promise((resolve, reject) => {
            AWS.config.credentials.get((err) => {
                if (err) reject(err);
                else resolve();
            });
        });

        const sqs = new AWS.SQS();
        
        // 3. Send each command as a separate message
        for (const cmd of pendingChanges) {
            const message = {
                command: cmd,
                timestamp: new Date().toISOString()
            };

            await sqs.sendMessage({
                QueueUrl: config.commandQueueUrl,
                MessageBody: JSON.stringify(message)
            }).promise();
        }

        alert(`Successfully submitted ${pendingChanges.length} changes! They will be processed by the worker shortly.`);
        pendingChanges = [];
        updatePendingUI();
    } catch (error) {
        console.error("Failed to submit changes:", error);
        alert("Error submitting changes: " + error.message);
    } finally {
        btn.disabled = false;
        btn.textContent = originalText;
    }
}

function clearPendingChanges() {
    pendingChanges = [];
    updatePendingUI();
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
        (stats.queries || []).forEach((q, idx) => {
            const li = document.createElement('li');
            li.className = 'list-item-editable';
            const elId = `query-${idx}`;
            li.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
                    <span>${q}</span>
                    <button class="btn-remove" onclick="removeExisting('query', '${q}', '${elId}')">×</button>
                </div>
                <div id="confirm-${elId}" class="delete-confirm-area"></div>
            `;
            queriesList.appendChild(li);
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
        (stats.exclusions || []).forEach((exc, idx) => {
            const li = document.createElement('li');
            li.className = 'list-item-editable';
            const elId = `exclude-${idx}`;
            const target = exc.company_slug || exc.domain;
            li.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
                    <span><strong>${target}</strong> ${exc.reason ? `<br><small style="color:#666">${exc.reason}</small>` : ''}</span>
                    <button class="btn-remove" onclick="removeExisting('exclude', '${target}', '${elId}')">×</button>
                </div>
                <div id="confirm-${elId}" class="delete-confirm-area"></div>
            `;
            exclusionsList.appendChild(li);
        });
    }
}
