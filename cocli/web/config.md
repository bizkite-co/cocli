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
        <div style="display: flex; gap: 15px;">
            <div class="scroll-container" style="flex: 1;">
                <ul id="locations-list" class="config-list">
                    <!-- Locations will be injected here -->
                </ul>
            </div>
            <div id="map-preview-container" style="width: 150px; display: none;">
                <div id="mini-map" style="width: 150px; height: 150px; border: 1px solid #ccc; background: #eee; border-radius: 4px;"></div>
                <p id="map-tile-info" style="font-size: 0.7em; color: #666; margin-top: 5px; text-align: center;"></p>
            </div>
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

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

<script>
    let map = null;
    let mapMarker = null;

    async function fetchConfig() {
        const urlParams = new URLSearchParams(window.location.search);
        const campaign = urlParams.get('campaign') || '{% if env.CAMPAIGN %}{{ env.CAMPAIGN }}{% else %}turboship{% endif %}';
        document.getElementById('campaign-display').textContent = campaign;
        
        try {
            const response = await fetch(`/reports/${campaign}.json?v=${Date.now()}`);
            if (!response.ok) throw new Error('Report data not found for this campaign.');
            
            const stats = await response.json();
            renderConfig(stats, campaign);
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

    function showMap(lat, lon, tileId, name) {
        const container = document.getElementById('map-preview-container');
        container.style.display = 'block';
        document.getElementById('map-tile-info').textContent = `Tile: ${tileId}`;

        if (!map) {
            map = L.map('mini-map', {
                zoomControl: false,
                attributionControl: false
            }).setView([lat, lon], 11);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);
            mapMarker = L.marker([lat, lon]).addTo(map);
        } else {
            map.setView([lat, lon], 11);
            mapMarker.setLatLng([lat, lon]);
        }
    }

    function renderConfig(stats, campaign) {
        document.getElementById('proximity-display').textContent = stats.proximity || '30';
        
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
            
            let statusIcon = loc.valid_geocode ? '✅' : '❓';
            let tileAction = loc.tile_id ? 
                `<button class="nav-link" style="padding: 2px 5px; font-size: 0.8em; border: 1px solid #ccc; border-radius: 3px; background: #fff; cursor: pointer;" 
                         onclick="showMap(${loc.lat}, ${loc.lon}, '${loc.tile_id}', '${loc.name}')">${loc.tile_id}</button>` : 
                '<span style="color: #999; font-size: 0.8em;">No Tile</span>';

            li.innerHTML = `
                <div style="flex: 1;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <strong>${loc.name}</strong>
                        <button class="btn-remove" onclick="removeExisting('location', '${loc.name}')">×</button>
                    </div>
                    <div style="font-size: 0.8em; color: #666; margin-top: 3px; display: flex; gap: 10px; align-items: center;">
                        <span>Prox: ${loc.proximity}mi</span>
                        <span>Geo: ${statusIcon}</span>
                        ${tileAction}
                    </div>
                </div>
            `;
            locationsList.appendChild(li);
        });
    }
</script>
