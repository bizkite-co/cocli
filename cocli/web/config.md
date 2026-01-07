---
layout: layout.njk
title: cocli Campaign Configuration
---

# Campaign Configuration: <span id="campaign-display">{% if env.CAMPAIGN %}{{ env.CAMPAIGN }}{% else %}turboship{% endif %}</span>

<p style="background: #e9ecef; padding: 10px; border-radius: 4px; display: inline-block;">
    <strong>Global Proximity:</strong> <span id="proximity-display">...</span> miles
</p>

Modify the search queries and target locations for the current campaign.

<div class="campaign-config-grid">
    <!-- Search Queries Section -->
    <div class="config-section queries-section">
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

    <!-- Target Locations Section -->
    <div class="config-section locations-section">
        <h3>Target Locations</h3>
        <div class="input-group">
            <input type="text" id="new-location" placeholder="Add new location...">
            <button onclick="addPendingChange('location', document.getElementById('new-location').value)">Add</button>
        </div>
        <div class="input-group">
            <input type="text" id="location-search" placeholder="Search target locations..." oninput="filterLocations()">
        </div>
        <ul id="locations-list" class="config-list">
            <!-- Locations will be injected here -->
        </ul>
        <p class="config-hint">Modify these in <code>target_locations.csv</code> or <code>config.toml</code></p>
    </div>
</div>

<div id="pending-changes-container" style="display:none;" class="pending-changes">
    <h3>Apply Changes</h3>
    <p>Copy and run these commands in your terminal to apply the changes:</p>
    <pre id="pending-commands-box"></pre>
    <button onclick="clearPendingChanges()">Clear All</button>
</div>

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

<script>
    let activeMap = null;
    let activeMarker = null;
    let statsData = null;

    async function fetchConfig() {
        const urlParams = new URLSearchParams(window.location.search);
        const campaign = urlParams.get('campaign') || '{% if env.CAMPAIGN %}{{ env.CAMPAIGN }}{% else %}turboship{% endif %}';
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
        const mapEl = document.getElementById('shared-map');
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
        
        // Update queries
        const queriesList = document.getElementById('queries-list');
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

        // Update locations
        const locationsList = document.getElementById('locations-list');
        locationsList.innerHTML = '';
        
        // Add shared map element if it doesn't exist
        if (!document.getElementById('shared-map')) {
            const sm = document.createElement('div');
            sm.id = 'shared-map';
            sm.style.width = '100%';
            sm.style.height = '100%';
            sm.style.display = 'none';
            document.body.appendChild(sm); // Hidden storage
        }

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
</script>
