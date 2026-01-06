---
layout: layout.njk
title: cocli Campaign Configuration
---

# Campaign Configuration: <span id="campaign-display">{% if env.CAMPAIGN %}{{ env.CAMPAIGN }}{% else %}turboship{% endif %}</span>

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

<script>
    async function fetchConfig() {
        const urlParams = new URLSearchParams(window.location.search);
        const campaign = urlParams.get('campaign') || '{% if env.CAMPAIGN %}{{ env.CAMPAIGN }}{% else %}turboship{% endif %}';
        document.getElementById('campaign-display').textContent = campaign;
        
        try {
            const response = await fetch(`/reports/${campaign}.json?v=${Date.now()}`);
            if (!response.ok) throw new Error('Report data not found for this campaign.');
            
            const stats = await response.json();
            renderConfig(stats);
        } catch (error) {
            console.error(error);
        }
    }

    window.addEventListener('DOMContentLoaded', fetchConfig);

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

    function renderConfig(stats) {
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
    }
</script>
