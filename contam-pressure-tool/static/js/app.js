/**
 * CONTAM Stairwell Pressurization Analysis Tool — Frontend Logic
 * SGH (Simpson Gumpertz & Heger)
 */

const App = (() => {
    // State
    let currentModelId = null;
    let modelData = { levels: [], zones: [], elements: [], paths: [], ahs: [] };
    let allZones = [];
    let allElements = [];
    let allPaths = [];
    let browserTargetInput = null;
    let browserSelectedPath = '';
    let browserCurrentPath = '';
    let scenarios = [];
    let eventSource = null;
    let lastSuggestions = null;

    // ---------------------------------------------------------------------------
    // Tab Navigation
    // ---------------------------------------------------------------------------
    function initTabs() {
        document.querySelectorAll('.nav-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
                tab.classList.add('active');
                const panel = document.getElementById(tab.dataset.tab);
                if (panel) panel.classList.add('active');
            });
        });

        // Sub-tabs
        document.querySelectorAll('.sub-tab').forEach(btn => {
            btn.addEventListener('click', () => {
                const parent = btn.parentElement;
                parent.querySelectorAll('.sub-tab').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                const container = parent.parentElement;
                container.querySelectorAll('.sub-panel').forEach(p => p.classList.remove('active'));
                const panel = container.querySelector('#' + btn.dataset.subtab);
                if (panel) panel.classList.add('active');
            });
        });
    }

    // ---------------------------------------------------------------------------
    // API Helpers
    // ---------------------------------------------------------------------------
    async function api(method, endpoint, body = null) {
        const opts = { method, headers: { 'Content-Type': 'application/json' } };
        if (body) opts.body = JSON.stringify(body);
        const resp = await fetch(endpoint, opts);
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(err.detail || resp.statusText);
        }
        return resp.json();
    }

    // ---------------------------------------------------------------------------
    // Project Setup
    // ---------------------------------------------------------------------------
    async function createProject() {
        const name = document.getElementById('project-name').value.trim();
        const folder = document.getElementById('project-folder').value.trim();
        const exe = document.getElementById('contam-exe').value.trim();
        if (!name || !folder) { alert('Please enter project name and folder.'); return; }
        try {
            await api('POST', '/api/project/create', { name, folder, contam_exe: exe });
            showStatus('parse-status', `Project "${name}" created.`, 'success');
            loadRecentProjects();
        } catch (e) { alert('Error: ' + e.message); }
    }

    async function openProject() {
        const folder = document.getElementById('project-folder').value.trim();
        if (!folder) { alert('Enter a project folder path.'); return; }
        try {
            const resp = await api('POST', '/api/project/open', { path: folder });
            const proj = resp.project;
            document.getElementById('project-name').value = proj.project_name || '';
            document.getElementById('project-folder').value = proj.project_folder || '';
            document.getElementById('contam-exe').value = proj.contam_executable || '';
            showStatus('parse-status', `Project "${proj.project_name}" loaded.`, 'success');
        } catch (e) { alert('Error: ' + e.message); }
    }

    async function loadRecentProjects() {
        try {
            const recent = await api('GET', '/api/project/recent');
            const ul = document.getElementById('recent-list');
            ul.innerHTML = '';
            recent.forEach(r => {
                const li = document.createElement('li');
                li.innerHTML = `<strong>${r.name}</strong><div class="path">${r.path}</div>`;
                li.onclick = () => {
                    document.getElementById('project-folder').value = r.path;
                    document.getElementById('project-name').value = r.name;
                };
                ul.appendChild(li);
            });
        } catch (e) { /* ignore */ }
    }

    async function detectContam() {
        try {
            const cfg = await api('GET', '/api/config/load');
            if (cfg.contam_executable_default) {
                document.getElementById('contam-exe').value = cfg.contam_executable_default;
            } else {
                alert('CONTAM executable not found in common locations. Please browse manually.');
            }
        } catch (e) { alert('Error: ' + e.message); }
    }

    // ---------------------------------------------------------------------------
    // Model Import & Parsing
    // ---------------------------------------------------------------------------
    async function parseModel() {
        const filepath = document.getElementById('prj-filepath').value.trim();
        if (!filepath) { alert('Enter a .prj file path.'); return; }

        showStatus('parse-status', 'Parsing...', 'success');
        try {
            const resp = await api('POST', '/api/model/parse', { filepath });
            currentModelId = resp.model_id;

            document.getElementById('badge-levels').textContent = 'Levels: ' + resp.num_levels;
            document.getElementById('badge-zones').textContent = 'Zones: ' + resp.num_zones;
            document.getElementById('badge-elements').textContent = 'Elements: ' + resp.num_flow_elements;
            document.getElementById('badge-paths').textContent = 'Paths: ' + resp.num_airflow_paths;
            document.getElementById('badge-ahs').textContent = 'AHS: ' + resp.num_ahs;

            document.getElementById('parsed-data').style.display = 'block';
            showStatus('parse-status', `Parsed successfully: ${resp.project_name} (${resp.version})`, 'success');

            // Load all data
            await Promise.all([loadLevels(), loadZones(), loadAHS(), loadElements(), loadPaths()]);
            populateDropdowns();

            // Auto-configure: detect stairs, corridors, paths, AHS and apply automatically
            try {
                lastSuggestions = await api('GET', `/api/model/${currentModelId}/auto-configure`);
                if (lastSuggestions && lastSuggestions.confidence !== 'low') {
                    applySuggestions();
                    showAutoConfigBanner(lastSuggestions);
                    // Switch to Tab 3 (Pressurization Config) so user can review
                    switchToTab('pressurization');
                } else {
                    showSuggestionsBanner(lastSuggestions);
                }
            } catch (e) {
                // Fall back to basic suggestions
                try {
                    lastSuggestions = await api('GET', `/api/model/${currentModelId}/suggestions`);
                    showSuggestionsBanner(lastSuggestions);
                } catch (e2) { /* suggestions are optional */ }
            }
        } catch (e) {
            showStatus('parse-status', 'Parse failed: ' + e.message, 'error');
        }
    }

    async function loadLevels() {
        const data = await api('GET', `/api/model/${currentModelId}/levels`);
        modelData.levels = data;
        renderLevelsTable(data);
    }

    async function loadZones() {
        const data = await api('GET', `/api/model/${currentModelId}/zones`);
        modelData.zones = data;
        allZones = data;
        renderZonesTable(data);
        populateZoneLevelFilter(data);
    }

    function renderZonesTable(zones) {
        const tbody = document.querySelector('#tbl-zones tbody');
        tbody.innerHTML = zones.map(z =>
            `<tr><td>${z.id}</td><td>${z.name}</td><td>${z.level_num}</td><td>${z.level_name}</td><td>${z.volume.toFixed(3)}</td><td>${z.temperature.toFixed(1)}</td></tr>`
        ).join('');
    }

    function filterZones() {
        const level = document.getElementById('zone-level-filter').value;
        const search = document.getElementById('zone-search').value.toLowerCase();
        let filtered = allZones;
        if (level) filtered = filtered.filter(z => z.level_num == level);
        if (search) filtered = filtered.filter(z => z.name.toLowerCase().includes(search) || z.display_name.toLowerCase().includes(search));
        renderZonesTable(filtered);
    }

    async function loadAHS() {
        const data = await api('GET', `/api/model/${currentModelId}/ahs`);
        modelData.ahs = data;
        renderAHSTable(data);
    }

    async function loadElements() {
        const data = await api('GET', `/api/model/${currentModelId}/elements`);
        modelData.elements = data;
        allElements = data;
        renderElementsTable(data);
    }

    function renderElementsTable(elems) {
        const tbody = document.querySelector('#tbl-elements tbody');
        tbody.innerHTML = elems.map(e =>
            `<tr><td>${e.id}</td><td>${e.name}</td><td>${e.type}</td></tr>`
        ).join('');
    }

    function filterElements() {
        const search = document.getElementById('elem-search').value.toLowerCase();
        const filtered = allElements.filter(e => e.name.toLowerCase().includes(search) || e.type.toLowerCase().includes(search));
        renderElementsTable(filtered);
    }

    async function loadPaths() {
        const data = await api('GET', `/api/model/${currentModelId}/paths`);
        modelData.paths = data;
        allPaths = data;
        renderPathsTable(data);
        populatePathFilters(data);
    }

    function renderPathsTable(paths) {
        const tbody = document.querySelector('#tbl-paths tbody');
        // Limit display for performance
        const display = paths.slice(0, 500);
        tbody.innerHTML = display.map(p =>
            `<tr><td>${p.id}</td><td>${p.from_zone}</td><td>${p.to_zone}</td><td>${p.flow_elem_name}</td><td>${p.ahs}</td><td>${p.level_num}</td><td>${p.icon_type}</td><td>${p.direction}</td></tr>`
        ).join('');
        if (paths.length > 500) {
            tbody.innerHTML += `<tr><td colspan="8" style="text-align:center;color:var(--text-secondary);">... showing 500 of ${paths.length} paths. Use filters to narrow.</td></tr>`;
        }
    }

    function filterPaths() {
        const level = document.getElementById('path-level-filter').value;
        const elem = document.getElementById('path-elem-filter').value;
        let filtered = allPaths;
        if (level) filtered = filtered.filter(p => p.level_num == level);
        if (elem) filtered = filtered.filter(p => p.flow_elem_name === elem);
        renderPathsTable(filtered);
    }

    // ---------------------------------------------------------------------------
    // Pressurization Configuration
    // ---------------------------------------------------------------------------
    function populateDropdowns() {
        // Called after model parse — populate zone/AHS/element dropdowns in config tabs
        updateStairTabs();
        updateCorridorTabs();
        updateRoofTable();
        updatePathSelection();
    }

    function makeZoneSelect(id, levelNum) {
        const zones = levelNum ? allZones.filter(z => z.level_num == levelNum) : allZones;
        let html = `<select id="${id}" class="zone-select"><option value="0">-- Select Zone --</option>`;
        zones.forEach(z => {
            html += `<option value="${z.id}">${z.name} (Zone #${z.id})</option>`;
        });
        return html + '</select>';
    }

    function makeAHSSelect(id) {
        let html = `<select id="${id}" class="ahs-select"><option value="0">-- Select AHS --</option>`;
        modelData.ahs.forEach(a => {
            html += `<option value="${a.id}">${a.name} (AHS #${a.id})</option>`;
        });
        return html + '</select>';
    }

    function makeElementSelect(id, placeholder) {
        let html = `<select id="${id}"><option value="">${placeholder || '-- Select --'}</option>`;
        modelData.elements.forEach(e => {
            html += `<option value="${e.name}">${e.name}</option>`;
        });
        return html + '</select>';
    }

    function updateStairTabs() {
        const n = parseInt(document.getElementById('num-stairs').value) || 1;
        const tabsEl = document.getElementById('stair-tabs');
        const panelsEl = document.getElementById('stair-panels');
        const labelsRow = document.getElementById('stair-labels-row');

        // Preserve existing label values before rebuilding
        const existingLabels = {};
        for (let i = 0; i < n; i++) {
            const el = document.getElementById(`stair-label-${i}`);
            if (el && el.value && el.value !== `Stair_${i + 1}`) {
                existingLabels[i] = el.value;
            }
        }

        // Stair labels
        labelsRow.innerHTML = '';
        for (let i = 0; i < n; i++) {
            const labelVal = existingLabels[i] || `Stair_${i + 1}`;
            labelsRow.innerHTML += `
                <div class="form-group">
                    <label>Stair ${i + 1} Label</label>
                    <input type="text" id="stair-label-${i}" value="${labelVal}" onchange="App.updateStairTabs()">
                </div>`;
        }

        // Tabs
        tabsEl.innerHTML = '';
        panelsEl.innerHTML = '';
        for (let i = 0; i < n; i++) {
            const label = document.getElementById(`stair-label-${i}`)?.value || `Stair_${i + 1}`;
            tabsEl.innerHTML += `<button class="sub-tab ${i === 0 ? 'active' : ''}" data-subtab="stair-panel-${i}">${label}</button>`;

            let tableRows = '';
            modelData.levels.forEach(lvl => {
                tableRows += `<tr>
                    <td>${lvl.name}</td>
                    <td>${makeZoneSelect(`stair-${i}-zone-${lvl.index}`, lvl.index)}</td>
                    <td><input type="number" id="stair-${i}-flow-${lvl.index}" value="0" min="0" step="100"></td>
                    <td>${makeAHSSelect(`stair-${i}-ahs-${lvl.index}`)}</td>
                    <td id="stair-${i}-supply-${lvl.index}" class="supply-cell">-</td>
                    <td><input type="number" id="stair-${i}-icon-${lvl.index}" value="128" min="0"></td>
                    <td><input type="number" id="stair-${i}-col-${lvl.index}" value="1" min="0"></td>
                    <td><input type="number" id="stair-${i}-row-${lvl.index}" value="1" min="0"></td>
                </tr>`;
            });

            panelsEl.innerHTML += `
                <div id="stair-panel-${i}" class="sub-panel ${i === 0 ? 'active' : ''}">
                    <div class="btn-row" style="margin-bottom:0.5rem;">
                        <button class="btn btn-sm" onclick="App.autoPopulateStair(${i})">Auto-Populate by Zone Name</button>
                    </div>
                    <div class="table-container">
                        <table>
                            <thead><tr><th>Level</th><th>Zone</th><th>Flow Rate (SCFM)</th><th>AHS</th><th>Supply Zone</th><th>Icon Type</th><th>Col</th><th>Row</th></tr></thead>
                            <tbody>${tableRows}</tbody>
                        </table>
                    </div>
                </div>`;
        }

        // Re-bind sub-tab clicks
        tabsEl.querySelectorAll('.sub-tab').forEach(btn => {
            btn.addEventListener('click', () => {
                tabsEl.querySelectorAll('.sub-tab').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                panelsEl.querySelectorAll('.sub-panel').forEach(p => p.classList.remove('active'));
                const panel = document.getElementById(btn.dataset.subtab);
                if (panel) panel.classList.add('active');
            });
        });

        // Bind AHS change events to update supply zone display
        document.querySelectorAll('.ahs-select').forEach(sel => {
            sel.addEventListener('change', updateSupplyZones);
        });
    }

    function updateSupplyZones() {
        // Update supply zone display based on AHS selection
        const n = parseInt(document.getElementById('num-stairs').value) || 1;
        for (let i = 0; i < n; i++) {
            modelData.levels.forEach(lvl => {
                const ahsSel = document.getElementById(`stair-${i}-ahs-${lvl.index}`);
                const supplyCell = document.getElementById(`stair-${i}-supply-${lvl.index}`);
                if (ahsSel && supplyCell) {
                    const ahsId = parseInt(ahsSel.value);
                    const ahs = modelData.ahs.find(a => a.id === ahsId);
                    if (ahs) {
                        supplyCell.textContent = ahs.supply_zone ? `Zone #${ahs.supply_zone}` : '(auto-created)';
                    } else {
                        supplyCell.textContent = '-';
                    }
                }
            });
        }
    }

    function autoPopulateStair(stairIdx) {
        // Find the first level where a zone is selected, then auto-fill matching zone names across levels
        let selectedName = null;
        for (const lvl of modelData.levels) {
            const sel = document.getElementById(`stair-${stairIdx}-zone-${lvl.index}`);
            if (sel && parseInt(sel.value) > 0) {
                const zone = allZones.find(z => z.id === parseInt(sel.value));
                if (zone) { selectedName = zone.name; break; }
            }
        }

        if (!selectedName) {
            selectedName = prompt('Enter zone name to auto-populate (e.g., "Stair_1"):');
            if (!selectedName) return;
        }

        // Find matching zones on each level (case-insensitive)
        const nameLower = selectedName.toLowerCase();
        modelData.levels.forEach(lvl => {
            const match = allZones.find(z => z.name.toLowerCase() === nameLower && z.level_num === lvl.index)
                       || allZones.find(z => z.name === selectedName && z.level_num === lvl.index);
            if (match) {
                const sel = document.getElementById(`stair-${stairIdx}-zone-${lvl.index}`);
                if (sel) sel.value = match.id;
            }
        });
    }

    function updateCorridorTabs() {
        const n = parseInt(document.getElementById('num-corridors').value) || 1;
        const tabsEl = document.getElementById('corridor-tabs');
        const panelsEl = document.getElementById('corridor-panels');

        tabsEl.innerHTML = '';
        panelsEl.innerHTML = '';
        for (let i = 0; i < n; i++) {
            const label = `Corridor ${i + 1}`;
            tabsEl.innerHTML += `<button class="sub-tab ${i === 0 ? 'active' : ''}" data-subtab="corr-panel-${i}">${label}</button>`;

            let tableRows = '';
            modelData.levels.forEach(lvl => {
                tableRows += `<tr>
                    <td>${lvl.name}</td>
                    <td>${makeZoneSelect(`corr-${i}-zone-${lvl.index}`, lvl.index)}</td>
                    <td><input type="number" id="corr-${i}-flow-${lvl.index}" value="0" min="0" step="100"></td>
                    <td>${makeAHSSelect(`corr-${i}-ahs-${lvl.index}`)}</td>
                    <td><input type="number" id="corr-${i}-icon-${lvl.index}" value="129" min="0"></td>
                    <td><input type="number" id="corr-${i}-col-${lvl.index}" value="1" min="0"></td>
                    <td><input type="number" id="corr-${i}-row-${lvl.index}" value="1" min="0"></td>
                </tr>`;
            });

            panelsEl.innerHTML += `
                <div id="corr-panel-${i}" class="sub-panel ${i === 0 ? 'active' : ''}">
                    <div class="btn-row" style="margin-bottom:0.5rem;">
                        <button class="btn btn-sm" onclick="App.autoPopulateCorridor(${i})">Auto-Populate by Zone Name</button>
                    </div>
                    <div class="table-container">
                        <table>
                            <thead><tr><th>Level</th><th>Zone</th><th>Flow Rate (SCFM)</th><th>AHS</th><th>Icon Type</th><th>Col</th><th>Row</th></tr></thead>
                            <tbody>${tableRows}</tbody>
                        </table>
                    </div>
                </div>`;
        }

        tabsEl.querySelectorAll('.sub-tab').forEach(btn => {
            btn.addEventListener('click', () => {
                tabsEl.querySelectorAll('.sub-tab').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                panelsEl.querySelectorAll('.sub-panel').forEach(p => p.classList.remove('active'));
                const panel = document.getElementById(btn.dataset.subtab);
                if (panel) panel.classList.add('active');
            });
        });
    }

    function autoPopulateCorridor(corrIdx) {
        let selectedName = null;
        for (const lvl of modelData.levels) {
            const sel = document.getElementById(`corr-${corrIdx}-zone-${lvl.index}`);
            if (sel && parseInt(sel.value) > 0) {
                const zone = allZones.find(z => z.id === parseInt(sel.value));
                if (zone) { selectedName = zone.name; break; }
            }
        }
        if (!selectedName) {
            selectedName = prompt('Enter corridor zone name (e.g., "Corridor"):');
            if (!selectedName) return;
        }
        const nameLower = selectedName.toLowerCase();
        modelData.levels.forEach(lvl => {
            const match = allZones.find(z => z.name.toLowerCase() === nameLower && z.level_num === lvl.index)
                       || allZones.find(z => z.name === selectedName && z.level_num === lvl.index);
            if (match) {
                const sel = document.getElementById(`corr-${corrIdx}-zone-${lvl.index}`);
                if (sel) sel.value = match.id;
            }
        });
    }

    function updateFloorTabs() {
        const n = parseInt(document.getElementById('num-floors').value) || 0;
        const tabsEl = document.getElementById('floor-tabs');
        const panelsEl = document.getElementById('floor-panels');

        tabsEl.innerHTML = '';
        panelsEl.innerHTML = '';
        for (let i = 0; i < n; i++) {
            const label = `Floor Zone ${i + 1}`;
            tabsEl.innerHTML += `<button class="sub-tab ${i === 0 ? 'active' : ''}" data-subtab="floor-panel-${i}">${label}</button>`;

            let tableRows = '';
            modelData.levels.forEach(lvl => {
                tableRows += `<tr>
                    <td>${lvl.name}</td>
                    <td>${makeZoneSelect(`floor-${i}-zone-${lvl.index}`, lvl.index)}</td>
                    <td><input type="number" id="floor-${i}-flow-${lvl.index}" value="0" min="0" step="100"></td>
                    <td>${makeAHSSelect(`floor-${i}-ahs-${lvl.index}`)}</td>
                    <td><input type="number" id="floor-${i}-icon-${lvl.index}" value="129" min="0"></td>
                    <td><input type="number" id="floor-${i}-col-${lvl.index}" value="1" min="0"></td>
                    <td><input type="number" id="floor-${i}-row-${lvl.index}" value="1" min="0"></td>
                </tr>`;
            });

            panelsEl.innerHTML += `
                <div id="floor-panel-${i}" class="sub-panel ${i === 0 ? 'active' : ''}">
                    <div class="btn-row" style="margin-bottom:0.5rem;">
                        <button class="btn btn-sm" onclick="App.autoPopulateFloor(${i})">Auto-Populate by Zone Name</button>
                    </div>
                    <div class="table-container">
                        <table>
                            <thead><tr><th>Level</th><th>Zone</th><th>Flow Rate (SCFM)</th><th>AHS</th><th>Icon Type</th><th>Col</th><th>Row</th></tr></thead>
                            <tbody>${tableRows}</tbody>
                        </table>
                    </div>
                </div>`;
        }

        tabsEl.querySelectorAll('.sub-tab').forEach(btn => {
            btn.addEventListener('click', () => {
                tabsEl.querySelectorAll('.sub-tab').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                panelsEl.querySelectorAll('.sub-panel').forEach(p => p.classList.remove('active'));
                const panel = document.getElementById(btn.dataset.subtab);
                if (panel) panel.classList.add('active');
            });
        });
    }

    function autoPopulateFloor(floorIdx) {
        let selectedName = null;
        for (const lvl of modelData.levels) {
            const sel = document.getElementById(`floor-${floorIdx}-zone-${lvl.index}`);
            if (sel && parseInt(sel.value) > 0) {
                const zone = allZones.find(z => z.id === parseInt(sel.value));
                if (zone) { selectedName = zone.name; break; }
            }
        }
        if (!selectedName) {
            selectedName = prompt('Enter floor zone name (e.g., "Floor", "Office"):');
            if (!selectedName) return;
        }
        const nameLower = selectedName.toLowerCase();
        modelData.levels.forEach(lvl => {
            const match = allZones.find(z => z.name.toLowerCase() === nameLower && z.level_num === lvl.index)
                       || allZones.find(z => z.name === selectedName && z.level_num === lvl.index);
            if (match) {
                const sel = document.getElementById(`floor-${floorIdx}-zone-${lvl.index}`);
                if (sel) sel.value = match.id;
            }
        });
    }

    function updateRoofTable() {
        const n = parseInt(document.getElementById('num-stairs').value) || 1;
        const tbody = document.getElementById('roof-body');
        tbody.innerHTML = '';
        for (let i = 0; i < n; i++) {
            const label = document.getElementById(`stair-label-${i}`)?.value || `Stair_${i + 1}`;
            // Level dropdown
            let levelOpts = '<option value="">-- Level --</option>';
            modelData.levels.forEach(l => {
                levelOpts += `<option value="${l.index}">${l.name}</option>`;
            });

            tbody.innerHTML += `<tr>
                <td>${label}</td>
                <td>${makeZoneSelect(`roof-zone-${i}`, '')}</td>
                <td><select id="roof-level-${i}">${levelOpts}</select></td>
                <td><input type="number" id="roof-flow-${i}" value="0" min="0" step="100"></td>
                <td>${makeAHSSelect(`roof-ahs-${i}`)}</td>
                <td><input type="number" id="roof-icon-${i}" value="129" min="0"></td>
                <td><input type="number" id="roof-col-${i}" value="1" min="0"></td>
                <td><input type="number" id="roof-row-${i}" value="1" min="0"></td>
            </tr>`;
        }
    }

    function updatePathSelection() {
        const n = parseInt(document.getElementById('num-stairs').value) || 1;
        const container = document.getElementById('path-selection-panels');
        container.innerHTML = '';

        for (let i = 0; i < n; i++) {
            const label = document.getElementById(`stair-label-${i}`)?.value || `Stair_${i + 1}`;
            container.innerHTML += `
                <div class="config-panel" style="margin-bottom:0.75rem;">
                    <div class="panel-header"><h3>${label} — Path Elements</h3></div>
                    <div class="panel-body">
                        <div class="form-row">
                            <div class="form-group">
                                <label>S2V (Stair-to-Vestibule)</label>
                                ${makeElementSelect(`path-s2v-${i}`, '-- Select S2V --')}
                            </div>
                            <div class="form-group">
                                <label>V2C (Vestibule-to-Corridor)</label>
                                ${makeElementSelect(`path-v2c-${i}`, '-- Select V2C --')}
                            </div>
                            <div class="form-group">
                                <label>EXT (Stair-to-Exterior)</label>
                                ${makeElementSelect(`path-ext-${i}`, '-- Select EXT --')}
                            </div>
                        </div>
                        <div class="form-row" style="margin-top:0.5rem;">
                            <div class="form-group">
                                <label>S2V2 (Secondary, optional)</label>
                                ${makeElementSelect(`path-s2v2-${i}`, '-- None --')}
                            </div>
                            <div class="form-group">
                                <label>V2C2 (Secondary, optional)</label>
                                ${makeElementSelect(`path-v2c2-${i}`, '-- None --')}
                            </div>
                        </div>
                    </div>
                </div>`;
        }

        // Corridor path
        const corrSel = document.getElementById('corridor-path-name');
        corrSel.innerHTML = `<option value="">-- Select --</option>`;
        modelData.elements.forEach(e => {
            corrSel.innerHTML += `<option value="${e.name}">${e.name}</option>`;
        });
    }

    // ---------------------------------------------------------------------------
    // Tab Switching Helper
    // ---------------------------------------------------------------------------
    function switchToTab(tabId) {
        document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
        const tab = document.querySelector(`.nav-tab[data-tab="${tabId}"]`);
        const panel = document.getElementById(tabId);
        if (tab) tab.classList.add('active');
        if (panel) panel.classList.add('active');
    }

    // ---------------------------------------------------------------------------
    // Auto-Suggestions
    // ---------------------------------------------------------------------------
    function showAutoConfigBanner(config) {
        // Remove existing banners
        const existing = document.getElementById('suggestions-banner');
        if (existing) existing.remove();
        const existingAuto = document.getElementById('auto-config-banner');
        if (existingAuto) existingAuto.remove();

        const banner = document.createElement('div');
        banner.id = 'auto-config-banner';
        banner.className = 'info-box';
        banner.style.marginBottom = '1rem';
        banner.style.borderColor = 'rgba(39,174,96,0.5)';
        banner.style.background = 'rgba(39,174,96,0.08)';

        const s = config.summary;
        const details = (config.detection_details || []).map(d => `<li>${d}</li>`).join('');
        const confLabel = config.confidence === 'high' ? 'High' : config.confidence === 'medium' ? 'Medium' : 'Low';

        const vestCount = s.vestibules_detected || 0;
        const corrPath = config.corridor_path_element ? `<li>Corridor path element: ${config.corridor_path_element}</li>` : '';

        banner.innerHTML = `
            <h3 style="color:var(--success); margin-bottom:0.5rem;">Auto-Configured from PRJ File (${confLabel} Confidence)</h3>
            <p>The model has been automatically analyzed and the following has been pre-filled:</p>
            <ul style="margin:0.5rem 0; padding-left:1.5rem; font-size:0.85rem;">
                ${details}
                ${vestCount > 0 ? `<li>Vestibule zones detected: ${vestCount} (linked to stairs via S2V paths)</li>` : ''}
                ${config.supply_ahs ? `<li>Supply AHS: ${config.supply_ahs.name} (#${config.supply_ahs.id})</li>` : '<li>Supply AHS: not detected (set manually if needed)</li>'}
                ${config.return_ahs ? `<li>Return AHS: ${config.return_ahs.name} (#${config.return_ahs.id})</li>` : '<li>Return AHS: not detected (set manually if needed)</li>'}
                ${corrPath}
            </ul>
            <p style="margin-top:0.75rem;"><strong>Next steps:</strong> Review the configuration below, set flow rates (SCFM) for each level, then proceed to Tab 4 (Scenarios) and Tab 5 (Run).</p>
            <div class="btn-row" style="margin-top:0.5rem;">
                <button class="btn btn-sm" onclick="document.getElementById('auto-config-banner').remove()">Dismiss</button>
            </div>
        `;

        // Insert at the top of the pressurization tab
        const pressTab = document.getElementById('pressurization');
        if (pressTab) {
            pressTab.insertBefore(banner, pressTab.children[1] || null);
        }
    }

    function showSuggestionsBanner(suggestions) {
        // Remove existing banner if any
        const existing = document.getElementById('suggestions-banner');
        if (existing) existing.remove();

        if (!suggestions || suggestions.confidence === 'low' && suggestions.summary.stairs_detected === 0) return;

        const s = suggestions.summary;
        const banner = document.createElement('div');
        banner.id = 'suggestions-banner';
        banner.className = 'info-box';
        banner.style.marginTop = '1rem';
        banner.style.borderColor = suggestions.confidence === 'high' ? 'rgba(39,174,96,0.4)' : 'rgba(243,156,18,0.4)';
        banner.style.background = suggestions.confidence === 'high' ? 'rgba(39,174,96,0.08)' : 'rgba(243,156,18,0.08)';

        const stairList = s.stair_names.length ? s.stair_names.join(', ') : 'none found';
        const corrList = s.corridor_names.length ? s.corridor_names.join(', ') : 'none found';
        const ahsInfo = suggestions.supply_ahs ? `Supply: ${suggestions.supply_ahs.name}` : 'not detected';
        const confLabel = suggestions.confidence === 'high' ? 'High confidence' : suggestions.confidence === 'medium' ? 'Medium confidence' : 'Low confidence';

        banner.innerHTML = `
            <h3>Auto-Detected Configuration (${confLabel})</h3>
            <p><strong>Stairs (${s.stairs_detected}):</strong> ${stairList}</p>
            <p><strong>Corridors (${s.corridors_detected}):</strong> ${corrList}</p>
            <p><strong>AHS:</strong> ${ahsInfo}</p>
            ${suggestions.corridor_path_element ? `<p><strong>Corridor Path:</strong> ${suggestions.corridor_path_element}</p>` : ''}
            <div class="btn-row" style="margin-top:0.75rem;">
                <button class="btn btn-primary" onclick="App.applySuggestions()">Apply Suggestions to All Tabs</button>
                <button class="btn" onclick="document.getElementById('suggestions-banner').remove()">Dismiss</button>
            </div>
        `;

        const parsedData = document.getElementById('parsed-data');
        parsedData.parentElement.insertBefore(banner, parsedData);
    }

    function setSelectByZone(selectEl, zoneInfo) {
        // Try setting by zone_id first
        if (zoneInfo.zone_id) {
            selectEl.value = String(zoneInfo.zone_id);
            if (selectEl.value === String(zoneInfo.zone_id)) return true;
        }
        // Fallback: match by zone name in option text
        if (zoneInfo.zone_name) {
            for (const opt of selectEl.options) {
                if (opt.text.startsWith(zoneInfo.zone_name + ' ')) {
                    selectEl.value = opt.value;
                    return true;
                }
            }
            // Looser match: case-insensitive name contained in option text
            const nameLower = zoneInfo.zone_name.toLowerCase();
            for (const opt of selectEl.options) {
                const optName = opt.text.split(' (Zone')[0].toLowerCase();
                if (optName === nameLower) {
                    selectEl.value = opt.value;
                    return true;
                }
            }
        }
        return false;
    }

    function applySuggestions() {
        if (!lastSuggestions) return;
        const sg = lastSuggestions;
        console.log('[AutoConfig] Applying suggestions:', sg.summary);

        // 0. Inject auto-created AHS into modelData if model has none
        if (sg.ahs_auto_created && sg.ahs_systems && modelData.ahs.length === 0) {
            console.log('[AutoConfig] Injecting auto-created AHS entries:', sg.ahs_systems);
            modelData.ahs = sg.ahs_systems.map(a => ({
                id: a.id,
                name: a.name,
                return_zone: 0,
                supply_zone: 0,
                return_path: 0,
                supply_path: 0,
                exhaust_path: 0,
            }));
        }

        // 1. Set number of stairs and labels
        const numStairs = sg.stairs.length || 1;
        document.getElementById('num-stairs').value = numStairs;

        // Build stair labels first (updateStairTabs needs them)
        updateStairTabs(); // creates label inputs with defaults

        // Set stair labels
        for (let i = 0; i < sg.stairs.length; i++) {
            const labelEl = document.getElementById(`stair-label-${i}`);
            if (labelEl) labelEl.value = sg.stairs[i].label;
        }

        // Rebuild tabs with correct labels (labels are now preserved by updateStairTabs)
        updateStairTabs();

        // 2. Set number of corridors
        const numCorr = sg.corridors.length || 1;
        document.getElementById('num-corridors').value = numCorr;
        updateCorridorTabs();

        // 3. Populate stair zone selections; SUPPLY AHS at every level
        // Skip "open" stairs — they don't get pressurized or airflow
        let stairZonesSet = 0, stairZonesMissed = 0;
        for (let i = 0; i < sg.stairs.length; i++) {
            const stair = sg.stairs[i];
            const isOpen = stair.label.toLowerCase().includes('open');
            const stairAhsId = stair.ahs_id || (sg.supply_ahs ? sg.supply_ahs.id : 0);

            for (const zoneInfo of stair.zones) {
                const zoneSel = document.getElementById(`stair-${i}-zone-${zoneInfo.level_num}`);
                if (zoneSel) {
                    if (setSelectByZone(zoneSel, zoneInfo)) {
                        stairZonesSet++;
                        // Set default flow rate: 600 SCFM for enclosed stairs, 0 for open stairs
                        const flowEl = document.getElementById(`stair-${i}-flow-${zoneInfo.level_num}`);
                        if (flowEl) flowEl.value = isOpen ? 0 : 600;
                    } else {
                        stairZonesMissed++;
                        console.warn(`[AutoConfig] Could not set stair ${stair.label} zone on level ${zoneInfo.level_num}: id=${zoneInfo.zone_id}, name=${zoneInfo.zone_name}`);
                    }
                } else {
                    console.warn(`[AutoConfig] No select found: stair-${i}-zone-${zoneInfo.level_num}`);
                }

                // SUPPLY AHS at every level of enclosed stairs
                if (!isOpen) {
                    const ahsSel = document.getElementById(`stair-${i}-ahs-${zoneInfo.level_num}`);
                    if (ahsSel && stairAhsId) ahsSel.value = stairAhsId;
                }
            }
            if (isOpen) {
                console.log(`[AutoConfig] Skipping AHS/flow for open stair: ${stair.label}`);
            }
        }
        console.log(`[AutoConfig] Stair zones set: ${stairZonesSet}, missed: ${stairZonesMissed}`);
        updateSupplyZones();

        // 4. Smart depressurization: corridor vs floor zone per level
        //    - If a level has a corridor zone, use corridor depressurization
        //    - If a level has no corridor but has a floor zone, use floor zone depressurization
        //    - This prevents double-depressurization on the same level

        // First pass: build set of levels that have corridor zones
        const levelsWithCorridor = new Set();
        for (const corr of sg.corridors) {
            for (const z of corr.zones) {
                levelsWithCorridor.add(z.level_num);
            }
        }

        // Populate corridors — zones + AHS on all levels, flow only where corridor exists
        let corrZonesSet = 0, corrZonesMissed = 0;
        for (let i = 0; i < sg.corridors.length; i++) {
            const corr = sg.corridors[i];
            const corrAhsId = corr.ahs_id || (sg.return_ahs ? sg.return_ahs.id : 0);

            for (const zoneInfo of corr.zones) {
                const zoneSel = document.getElementById(`corr-${i}-zone-${zoneInfo.level_num}`);
                if (zoneSel) {
                    if (setSelectByZone(zoneSel, zoneInfo)) {
                        corrZonesSet++;
                        const flowEl = document.getElementById(`corr-${i}-flow-${zoneInfo.level_num}`);
                        if (flowEl) flowEl.value = 600;
                    } else {
                        corrZonesMissed++;
                    }
                }
                const ahsSel = document.getElementById(`corr-${i}-ahs-${zoneInfo.level_num}`);
                if (ahsSel && corrAhsId) ahsSel.value = corrAhsId;
            }
        }
        console.log(`[AutoConfig] Corridor zones: ${corrZonesSet} set, ${corrZonesMissed} missed (levels: ${[...levelsWithCorridor].sort((a,b)=>a-b).join(',')})`);

        // Populate floor zones — zones + AHS everywhere, but flow only on levels WITHOUT a corridor
        if (sg.floor_zones && sg.floor_zones.length > 0) {
            document.getElementById('num-floors').value = sg.floor_zones.length;
            updateFloorTabs();

            let floorActive = 0, floorSkipped = 0;
            for (let i = 0; i < sg.floor_zones.length; i++) {
                const floorZone = sg.floor_zones[i];
                const floorAhsId = floorZone.ahs_id || (sg.return_ahs ? sg.return_ahs.id : 0);

                for (const zoneInfo of floorZone.zones) {
                    const zoneSel = document.getElementById(`floor-${i}-zone-${zoneInfo.level_num}`);
                    if (zoneSel) {
                        setSelectByZone(zoneSel, zoneInfo);
                    }

                    // AHS on every level (for reference)
                    const ahsSel = document.getElementById(`floor-${i}-ahs-${zoneInfo.level_num}`);
                    if (ahsSel && floorAhsId) ahsSel.value = floorAhsId;

                    // Flow rate: only on levels that DON'T have a corridor
                    const flowEl = document.getElementById(`floor-${i}-flow-${zoneInfo.level_num}`);
                    if (flowEl) {
                        if (levelsWithCorridor.has(zoneInfo.level_num)) {
                            flowEl.value = 0; // corridor handles this level
                            floorSkipped++;
                        } else {
                            flowEl.value = 600; // no corridor — floor zone handles it
                            floorActive++;
                        }
                    }
                }
            }
            console.log(`[AutoConfig] Floor zones: ${sg.floor_zones.length} groups, ${floorActive} levels active, ${floorSkipped} levels skipped (corridor present)`);
        }

        // 5. Populate roof table and path selection
        updateRoofTable();
        updatePathSelection();

        // Set roof configs — use SUPPLY AHS (supply fan at top of stair)
        // Skip open stairs (no roof pressurization needed)
        for (let i = 0; i < sg.roof_configs.length && i < sg.stairs.length; i++) {
            const stairLabel = sg.stairs[i]?.label || '';
            const isOpen = stairLabel.toLowerCase().includes('open');
            if (isOpen) {
                console.log(`[AutoConfig] Skipping roof config for open stair: ${stairLabel}`);
                continue;
            }

            const roof = sg.roof_configs[i];
            const supplyAhsId = sg.supply_ahs ? sg.supply_ahs.id : 0;

            const zoneSel = document.getElementById(`roof-zone-${i}`);
            if (zoneSel) {
                setSelectByZone(zoneSel, { zone_id: roof.zone_id, zone_name: '' });
            }

            const levelSel = document.getElementById(`roof-level-${i}`);
            if (levelSel) levelSel.value = roof.level_num;

            const ahsSel = document.getElementById(`roof-ahs-${i}`);
            if (ahsSel && supplyAhsId) ahsSel.value = supplyAhsId;
        }

        // 6. Set path element selections
        for (let i = 0; i < sg.stairs.length; i++) {
            const paths = sg.stairs[i].paths;
            for (const [key, elemName] of Object.entries(paths)) {
                if (!elemName) continue;
                const sel = document.getElementById(`path-${key}-${i}`);
                if (sel) sel.value = elemName;
            }
        }

        // 7. Set corridor path element
        if (sg.corridor_path_element) {
            const corrPathSel = document.getElementById('corridor-path-name');
            if (corrPathSel) corrPathSel.value = sg.corridor_path_element;
        }

        // 8. Pre-populate standard scenarios (Winter/Summer x Wind/NoWind)
        if (scenarios.length === 0) {
            addScenario('WinterWind', '', 37, 20, 270);
            addScenario('WinterNoWind', '', 37, 0, 270);
            addScenario('SummerWind', '', 93, 20, 270);
            addScenario('SummerNoWind', '', 93, 0, 270);
            console.log('[AutoConfig] Pre-populated 4 standard scenarios (37F winter, 93F summer, 20mph wind)');
        }

        // 9. Summary log
        const openStairs = sg.stairs.filter(s => s.label.toLowerCase().includes('open')).map(s => s.label);
        const enclosedStairs = sg.stairs.filter(s => !s.label.toLowerCase().includes('open')).map(s => s.label);
        console.log(`[AutoConfig] Applied: ${enclosedStairs.length} enclosed stairs (${enclosedStairs.join(', ')}), ${openStairs.length} open stairs skipped (${openStairs.join(', ')}), ${numCorr} corridors, ${sg.summary.vestibules_detected} vestibules`);
    }

    function togglePanel(header) {
        const body = header.nextElementSibling;
        body.classList.toggle('collapsed');
        header.classList.toggle('collapsed');
    }

    // ---------------------------------------------------------------------------
    // Scenario Matrix
    // ---------------------------------------------------------------------------
    function addScenario(name, baseModel, tempF, windMph, windDir) {
        scenarios.push({
            name: name || '',
            base_model: baseModel || '',
            temp_f: tempF || 0,
            wind_mph: windMph || 0,
            wind_dir: windDir || 270,
        });
        renderScenarios();
    }

    function addStandardSet() {
        const winterTemp = prompt('Winter temperature (F):', '37');
        const summerTemp = prompt('Summer temperature (F):', '93');
        const windSpeed = prompt('Wind speed (mph):', '20');
        if (!winterTemp || !summerTemp || !windSpeed) return;

        addScenario('WinterWind', '', parseFloat(winterTemp), parseFloat(windSpeed), 270);
        addScenario('WinterNoWind', '', parseFloat(winterTemp), 0, 270);
        addScenario('SummerWind', '', parseFloat(summerTemp), parseFloat(windSpeed), 270);
        addScenario('SummerNoWind', '', parseFloat(summerTemp), 0, 270);
    }

    function removeSelectedScenario() {
        const checkboxes = document.querySelectorAll('#scenario-body input[type="checkbox"]:checked');
        const indices = [];
        checkboxes.forEach(cb => indices.push(parseInt(cb.dataset.idx)));
        scenarios = scenarios.filter((_, i) => !indices.includes(i));
        renderScenarios();
    }

    function renderScenarios() {
        const tbody = document.getElementById('scenario-body');
        tbody.innerHTML = scenarios.map((s, i) => `
            <tr>
                <td><input type="checkbox" data-idx="${i}"></td>
                <td><input type="text" value="${s.name}" onchange="App.updateScenario(${i},'name',this.value)"></td>
                <td><input type="text" value="${s.base_model}" onchange="App.updateScenario(${i},'base_model',this.value)" placeholder="PRJ file path"></td>
                <td><input type="number" value="${s.temp_f}" step="0.1" onchange="App.updateScenario(${i},'temp_f',parseFloat(this.value))"></td>
                <td><input type="number" value="${s.wind_mph}" step="0.1" onchange="App.updateScenario(${i},'wind_mph',parseFloat(this.value))"></td>
                <td><input type="number" value="${s.wind_dir}" step="1" min="0" max="360" onchange="App.updateScenario(${i},'wind_dir',parseFloat(this.value))"></td>
            </tr>
        `).join('');

        // Update total runs display
        updateRunSummary();
    }

    function updateScenario(idx, field, value) {
        if (scenarios[idx]) scenarios[idx][field] = value;
        updateRunSummary();
    }

    function updateRunSummary() {
        // Count fire floors (corridor levels with non-zero flow)
        const numCorr = parseInt(document.getElementById('num-corridors')?.value) || 1;
        let fireFloors = 0;
        modelData.levels.forEach(lvl => {
            for (let c = 0; c < numCorr; c++) {
                const flowEl = document.getElementById(`corr-${c}-flow-${lvl.index}`);
                if (flowEl && parseFloat(flowEl.value) > 0) { fireFloors++; break; }
            }
        });
        const total = scenarios.length * Math.max(fireFloors, 1);
        document.getElementById('total-runs').textContent = total;
    }

    // ---------------------------------------------------------------------------
    // Collect configuration from GUI
    // ---------------------------------------------------------------------------
    function collectConfig() {
        const numStairs = parseInt(document.getElementById('num-stairs').value) || 1;
        const numCorr = parseInt(document.getElementById('num-corridors').value) || 1;

        // Stairs
        const stairs = [];
        for (let i = 0; i < numStairs; i++) {
            const label = document.getElementById(`stair-label-${i}`)?.value || `Stair_${i + 1}`;
            const levels = [];
            modelData.levels.forEach(lvl => {
                const zoneId = parseInt(document.getElementById(`stair-${i}-zone-${lvl.index}`)?.value || 0);
                const flowRate = parseFloat(document.getElementById(`stair-${i}-flow-${lvl.index}`)?.value || 0);
                const ahsId = parseInt(document.getElementById(`stair-${i}-ahs-${lvl.index}`)?.value || 0);
                const ahs = modelData.ahs.find(a => a.id === ahsId);
                levels.push({
                    level_num: lvl.index,
                    zone_id: zoneId,
                    flow_rate: flowRate,
                    ahs_id: ahsId,
                    supply_zone: ahs ? ahs.supply_zone : 0,
                    icon_type: parseInt(document.getElementById(`stair-${i}-icon-${lvl.index}`)?.value || 128),
                    icon_col: parseInt(document.getElementById(`stair-${i}-col-${lvl.index}`)?.value || 1),
                    icon_row: parseInt(document.getElementById(`stair-${i}-row-${lvl.index}`)?.value || 1),
                });
            });
            stairs.push({
                label,
                levels,
                paths: {
                    s2v: document.getElementById(`path-s2v-${i}`)?.value || '',
                    v2c: document.getElementById(`path-v2c-${i}`)?.value || '',
                    ext: document.getElementById(`path-ext-${i}`)?.value || '',
                    s2v2: document.getElementById(`path-s2v2-${i}`)?.value || '',
                    v2c2: document.getElementById(`path-v2c2-${i}`)?.value || '',
                },
            });
        }

        // Corridors
        const corridors = [];
        for (let i = 0; i < numCorr; i++) {
            const levels = [];
            modelData.levels.forEach(lvl => {
                const zoneId = parseInt(document.getElementById(`corr-${i}-zone-${lvl.index}`)?.value || 0);
                const flowRate = parseFloat(document.getElementById(`corr-${i}-flow-${lvl.index}`)?.value || 0);
                const ahsId = parseInt(document.getElementById(`corr-${i}-ahs-${lvl.index}`)?.value || 0);
                const ahs = modelData.ahs.find(a => a.id === ahsId);
                levels.push({
                    level_num: lvl.index,
                    zone_id: zoneId,
                    flow_rate: flowRate,
                    ahs_id: ahsId,
                    exhaust_zone: ahs ? ahs.return_zone : 0,
                    icon_type: parseInt(document.getElementById(`corr-${i}-icon-${lvl.index}`)?.value || 129),
                    icon_col: parseInt(document.getElementById(`corr-${i}-col-${lvl.index}`)?.value || 1),
                    icon_row: parseInt(document.getElementById(`corr-${i}-row-${lvl.index}`)?.value || 1),
                });
            });
            corridors.push({
                label: `Corridor_${i + 1}`,
                levels,
                path_name: document.getElementById('corridor-path-name')?.value || '',
            });
        }

        // Floor zones
        const numFloors = parseInt(document.getElementById('num-floors').value) || 0;
        const floorZones = [];
        for (let i = 0; i < numFloors; i++) {
            const levels = [];
            modelData.levels.forEach(lvl => {
                const zoneId = parseInt(document.getElementById(`floor-${i}-zone-${lvl.index}`)?.value || 0);
                const flowRate = parseFloat(document.getElementById(`floor-${i}-flow-${lvl.index}`)?.value || 0);
                const ahsId = parseInt(document.getElementById(`floor-${i}-ahs-${lvl.index}`)?.value || 0);
                const ahs = modelData.ahs.find(a => a.id === ahsId);
                levels.push({
                    level_num: lvl.index,
                    zone_id: zoneId,
                    flow_rate: flowRate,
                    ahs_id: ahsId,
                    exhaust_zone: ahs ? ahs.return_zone : 0,
                    icon_type: parseInt(document.getElementById(`floor-${i}-icon-${lvl.index}`)?.value || 129),
                    icon_col: parseInt(document.getElementById(`floor-${i}-col-${lvl.index}`)?.value || 1),
                    icon_row: parseInt(document.getElementById(`floor-${i}-row-${lvl.index}`)?.value || 1),
                });
            });
            floorZones.push({
                label: `Floor_${i + 1}`,
                levels,
                path_name: document.getElementById('corridor-path-name')?.value || '',
            });
        }

        // Roof configs
        const roofConfigs = [];
        for (let i = 0; i < numStairs; i++) {
            const zoneId = parseInt(document.getElementById(`roof-zone-${i}`)?.value || 0);
            const levelNum = parseInt(document.getElementById(`roof-level-${i}`)?.value || 0);
            const flowRate = parseFloat(document.getElementById(`roof-flow-${i}`)?.value || 0);
            const ahsId = parseInt(document.getElementById(`roof-ahs-${i}`)?.value || 0);
            const ahs = modelData.ahs.find(a => a.id === ahsId);
            roofConfigs.push({
                stair_label: document.getElementById(`stair-label-${i}`)?.value || `Stair_${i + 1}`,
                zone_id: zoneId,
                level_num: levelNum,
                flow_rate: flowRate,
                ahs_id: ahsId,
                exhaust_zone: ahs ? ahs.return_zone : 0,
                icon_type: parseInt(document.getElementById(`roof-icon-${i}`)?.value || 129),
                icon_col: parseInt(document.getElementById(`roof-col-${i}`)?.value || 1),
                icon_row: parseInt(document.getElementById(`roof-row-${i}`)?.value || 1),
            });
        }

        // Scenarios
        const scenarioConfigs = scenarios.map(s => ({
            name: s.name,
            base_model_path: s.base_model || document.getElementById('prj-filepath')?.value || '',
            temp_f: s.temp_f,
            wind_mph: s.wind_mph,
            wind_dir: s.wind_dir,
        }));

        return {
            project_name: document.getElementById('project-name')?.value || '',
            project_folder: document.getElementById('project-folder')?.value || '',
            contam_exe: document.getElementById('contam-exe')?.value || '',
            scenarios: scenarioConfigs,
            stairs,
            corridors,
            floor_zones: floorZones,
            roof_configs: roofConfigs,
            acceptance_criteria: {
                min_dp_inwc: parseFloat(document.getElementById('min-dp')?.value || 0.05),
                max_dp_inwc: parseFloat(document.getElementById('max-dp')?.value || 0.45),
            },
        };
    }

    // ---------------------------------------------------------------------------
    // Run Analysis
    // ---------------------------------------------------------------------------
    async function dryRun() {
        const config = collectConfig();
        appendLog('Starting dry run...');
        try {
            const resp = await api('POST', '/api/analysis/dryrun', config);
            appendLog(`Dry run complete. Generated ${resp.count} PRJ files.`);
            resp.generated_files.forEach(f => appendLog('  ' + f));
        } catch (e) {
            appendLog('Dry run failed: ' + e.message);
        }
    }

    async function startAnalysis() {
        const config = collectConfig();
        document.getElementById('btn-start').disabled = true;
        document.getElementById('btn-cancel').disabled = false;
        document.getElementById('progress-container').style.display = 'block';
        appendLog('Starting analysis...');

        try {
            const resp = await api('POST', '/api/analysis/start', config);
            appendLog(`Analysis started. Total runs: ${resp.total_runs}`);

            // Connect to SSE for progress
            if (eventSource) eventSource.close();
            eventSource = new EventSource('/api/analysis/status');
            eventSource.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.message) appendLog(data.message);
                if (data.done) {
                    eventSource.close();
                    document.getElementById('btn-start').disabled = false;
                    document.getElementById('btn-cancel').disabled = true;
                    appendLog('=== Analysis Complete ===');
                    document.getElementById('progress-fill').style.width = '100%';
                    loadResultsScenarios();
                }
                if (!data.done && data.running !== false) {
                    // Update progress (approximate)
                    const match = data.message?.match(/\((\d+) of (\d+)\)/);
                    if (match) {
                        const pct = (parseInt(match[1]) / parseInt(match[2])) * 100;
                        document.getElementById('progress-fill').style.width = pct + '%';
                        document.getElementById('progress-label').textContent = data.message;
                    }
                }
            };
            eventSource.onerror = () => {
                eventSource.close();
                document.getElementById('btn-start').disabled = false;
                document.getElementById('btn-cancel').disabled = true;
            };
        } catch (e) {
            appendLog('Failed to start: ' + e.message);
            document.getElementById('btn-start').disabled = false;
            document.getElementById('btn-cancel').disabled = true;
        }
    }

    async function cancelAnalysis() {
        try {
            await api('POST', '/api/analysis/cancel');
            appendLog('Analysis cancelled.');
        } catch (e) { appendLog('Cancel failed: ' + e.message); }
        document.getElementById('btn-start').disabled = false;
        document.getElementById('btn-cancel').disabled = true;
    }

    function appendLog(msg) {
        const el = document.getElementById('log-output');
        el.textContent += msg + '\n';
        el.scrollTop = el.scrollHeight;
    }

    // ---------------------------------------------------------------------------
    // Results
    // ---------------------------------------------------------------------------
    let cachedDetailedResults = null;

    async function loadResultsScenarios() {
        try {
            const summaries = await api('GET', '/api/results/summary');
            const sel = document.getElementById('result-scenario-filter');
            sel.innerHTML = '<option value="">-- Select Scenario --</option>';
            summaries.forEach(s => {
                sel.innerHTML += `<option value="${s.scenario}">${s.scenario}</option>`;
            });
        } catch (e) { /* no results yet */ }
    }

    async function loadResults() {
        const scenario = document.getElementById('result-scenario-filter').value;
        if (!scenario) return;
        cachedDetailedResults = null;

        const viewMode = document.getElementById('result-view-mode').value;
        if (viewMode === 'summary') {
            document.getElementById('fire-floor-selector').style.display = 'none';
            try {
                const resp = await api('GET', `/api/results/${scenario}`);
                renderResultsTable(resp.columns, resp.data);
                // Try to load detailed for level summary
                try {
                    cachedDetailedResults = await api('GET', `/api/results/${scenario}/detailed`);
                    renderLevelSummary(cachedDetailedResults.level_summary);
                } catch (e) { /* no detailed available */ }
            } catch (e) { alert('Error loading results: ' + e.message); }
        } else if (viewMode === 'detailed' || viewMode === 'worst_case') {
            await loadDetailedResults(scenario);
        }
    }

    async function loadDetailedResults(scenario) {
        try {
            cachedDetailedResults = await api('GET', `/api/results/${scenario}/detailed`);
            const d = cachedDetailedResults;

            if (document.getElementById('result-view-mode').value === 'detailed') {
                // Populate fire floor dropdown
                const ffSel = document.getElementById('result-fire-floor');
                ffSel.innerHTML = '';
                d.fire_floor_names.forEach((name, idx) => {
                    ffSel.innerHTML += `<option value="${name}">${name}</option>`;
                });
                document.getElementById('fire-floor-selector').style.display = 'flex';
                loadDetailedFireFloor();
            } else {
                // Worst-case view
                document.getElementById('fire-floor-selector').style.display = 'none';
                renderWorstCaseTable(d);
            }
            renderLevelSummary(d.level_summary);
        } catch (e) { alert('Error loading detailed results: ' + e.message); }
    }

    function loadDetailedFireFloor() {
        if (!cachedDetailedResults) return;
        const ffName = document.getElementById('result-fire-floor').value;
        const table = cachedDetailedResults.tables[ffName];
        if (table) {
            renderResultsTable(table.columns, table.data, `Fire Floor: ${ffName}`);
        }
    }

    function switchResultView() {
        loadResults();
    }

    function renderWorstCaseTable(detailed) {
        const thead = document.getElementById('results-head');
        const tbody = document.getElementById('results-body');

        // Columns: Level, then for each metric: value + which fire floor
        const metricCols = detailed.tables[detailed.fire_floor_names[0]]?.columns.slice(1) || [];
        const columns = ['Level', ...metricCols];
        thead.innerHTML = '<tr>' + columns.map(c => `<th>${c}</th>`).join('') + '</tr>';

        const minDp = parseFloat(document.getElementById('min-dp').value) || 0.05;
        const maxDp = parseFloat(document.getElementById('max-dp').value) || 0.45;

        const rows = [];
        for (const lvlName of detailed.levels) {
            const wc = detailed.worst_case[lvlName];
            let rowHtml = `<td>${lvlName}</td>`;
            for (const col of metricCols) {
                const info = wc?.[col] || { value: 0, fire_floor: '' };
                const numVal = info.value;
                if (numVal === 0) {
                    rowHtml += '<td>-</td>';
                } else {
                    const absVal = Math.abs(numVal);
                    let cls = '';
                    if (absVal < minDp) cls = 'dp-fail';
                    else if (absVal > maxDp) cls = 'dp-fail';
                    else if (absVal < minDp * 1.1 || absVal > maxDp * 0.9) cls = 'dp-warn';
                    else cls = 'dp-pass';
                    rowHtml += `<td class="${cls}">${numVal.toFixed(4)}<span class="worst-ff">${info.fire_floor}</span></td>`;
                }
            }
            rows.push(`<tr>${rowHtml}</tr>`);
        }
        tbody.innerHTML = rows.join('');
    }

    function renderLevelSummary(levelSummary) {
        if (!levelSummary) {
            document.getElementById('level-summary-bar').style.display = 'none';
            return;
        }
        const container = document.getElementById('level-summary-content');
        let html = '';
        for (const [lvl, info] of Object.entries(levelSummary)) {
            const cls = info.status === 'pass' ? 'pass' : (info.status === 'fail' ? 'fail' : 'no-data');
            const title = info.status === 'no_data' ? 'No data'
                : `Pass: ${info.pass}/${info.total}, Fail: ${info.fail}`;
            html += `<span class="level-badge ${cls}" title="${title}">${lvl}</span>`;
        }
        container.innerHTML = html;
        document.getElementById('level-summary-bar').style.display = 'block';
    }

    function renderResultsTable(columns, data, subtitle) {
        const thead = document.getElementById('results-head');
        const tbody = document.getElementById('results-body');

        let headerHtml = '<tr>' + columns.map(c => `<th>${c}</th>`).join('') + '</tr>';
        if (subtitle) {
            headerHtml = `<tr><th colspan="${columns.length}" style="text-align:center;background:rgba(46,134,222,0.08);font-size:0.85rem;">${subtitle}</th></tr>` + headerHtml;
        }
        thead.innerHTML = headerHtml;

        const minDp = parseFloat(document.getElementById('min-dp').value) || 0.05;
        const maxDp = parseFloat(document.getElementById('max-dp').value) || 0.45;

        tbody.innerHTML = data.map(row =>
            '<tr>' + row.map((val, ci) => {
                if (ci === 0) return `<td>${val}</td>`;
                const numVal = parseFloat(val);
                if (isNaN(numVal) || numVal === 0) return `<td>${val ?? ''}</td>`;
                let cls = '';
                const absVal = Math.abs(numVal);
                if (absVal < minDp) cls = 'dp-fail';
                else if (absVal > maxDp) cls = 'dp-fail';
                else if (absVal < minDp * 1.1 || absVal > maxDp * 0.9) cls = 'dp-warn';
                else cls = 'dp-pass';
                return `<td class="${cls}">${numVal.toFixed(4)}</td>`;
            }).join('') + '</tr>'
        ).join('');
    }

    function applyHighlighting() {
        // Re-render current results with new thresholds
        loadResults();
    }

    async function exportCSV() {
        const scenario = document.getElementById('result-scenario-filter').value;
        window.open(`/api/results/export/csv${scenario ? '?scenario=' + scenario : ''}`, '_blank');
    }

    async function exportSummaryCSV() {
        window.open('/api/results/export/summary-csv', '_blank');
    }

    async function exportDetailedCSV() {
        if (!cachedDetailedResults) {
            alert('No detailed results loaded. Run an analysis first.');
            return;
        }
        const d = cachedDetailedResults;
        // Build CSV with all fire floors
        let csv = '';
        for (const ffName of d.fire_floor_names) {
            const table = d.tables[ffName];
            csv += `\nFire Floor: ${ffName}\n`;
            csv += table.columns.join(',') + '\n';
            for (const row of table.data) {
                csv += row.map(v => typeof v === 'number' ? v.toFixed(4) : v).join(',') + '\n';
            }
        }
        csv += '\nUnits: in. H2O\n';

        const blob = new Blob([csv], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `Detailed_Results_${d.scenario}.csv`;
        a.click();
        URL.revokeObjectURL(url);
    }

    function generateReport() {
        window.open('/api/results/export/report', '_blank');
    }

    function generateModelReport() {
        if (currentModelId) {
            window.open(`/api/model/${currentModelId}/report`, '_blank');
        } else {
            alert('No model loaded. Parse a PRJ file first.');
        }
    }

    // ---------------------------------------------------------------------------
    // File Browser
    // ---------------------------------------------------------------------------
    let browserFileFilter = '';  // e.g. '.prj' to highlight PRJ files

    function browseFolder(targetInputId) {
        browserTargetInput = targetInputId;
        browserSelectedPath = '';

        // Set file filter based on which input we're browsing for
        browserFileFilter = (targetInputId === 'prj-filepath') ? '.prj' : '';

        // Determine a good starting path
        let startPath = document.getElementById(targetInputId)?.value?.trim() || '';
        if (!startPath) {
            // Try project folder as fallback
            const projFolder = document.getElementById('project-folder')?.value?.trim() || '';
            startPath = projFolder || '';
        }
        // If we have a file path, navigate to its parent directory
        if (startPath && startPath.match(/\.\w+$/)) {
            const sep = startPath.includes('\\') ? '\\' : '/';
            startPath = startPath.substring(0, startPath.lastIndexOf(sep)) || startPath;
        }

        document.getElementById('browser-path-input').value = startPath;
        document.getElementById('file-browser-modal').style.display = 'flex';
        navigateBrowserTo(startPath);
    }

    async function navigateBrowser() {
        const path = document.getElementById('browser-path-input').value.trim();
        navigateBrowserTo(path);
    }

    async function navigateBrowserTo(path) {
        browserCurrentPath = path;
        try {
            const resp = await api('POST', '/api/browse/list', { path: path || '' });
            browserCurrentPath = resp.current_path || path;
            document.getElementById('browser-path-input').value = browserCurrentPath;

            const list = document.getElementById('browser-list');
            let items = resp.items || [];

            // Sort: directories first, then files; PRJ files highlighted at top of files
            items.sort((a, b) => {
                if (a.type !== b.type) {
                    if (a.type === 'drive') return -1;
                    if (b.type === 'drive') return 1;
                    if (a.type === 'dir') return -1;
                    if (b.type === 'dir') return 1;
                }
                // If filtering for a file type, put matching files first
                if (browserFileFilter && a.type === 'file' && b.type === 'file') {
                    const aMatch = (a.ext || '').toLowerCase() === browserFileFilter;
                    const bMatch = (b.ext || '').toLowerCase() === browserFileFilter;
                    if (aMatch && !bMatch) return -1;
                    if (!aMatch && bMatch) return 1;
                }
                return a.name.localeCompare(b.name);
            });

            list.innerHTML = items.map(item => {
                const isDir = item.type === 'dir' || item.type === 'drive';
                const icon = isDir ? '&#128193;' : '&#128196;';
                const isMatch = browserFileFilter && !isDir && (item.ext || '').toLowerCase() === browserFileFilter;
                const dimClass = browserFileFilter && !isDir && !isMatch ? ' dimmed' : '';
                const highlightClass = isMatch ? ' highlighted' : '';
                const sizeStr = item.size ? ` (${(item.size / 1024).toFixed(0)} KB)` : '';
                return `<div class="browser-item${dimClass}${highlightClass}" data-path="${item.path}" data-type="${item.type}" onclick="App.browserItemClick(this)" ondblclick="App.browserItemDblClick(this)">
                    <span class="icon">${icon}</span>
                    <span class="name">${item.name}</span>
                    <span class="meta">${!isDir ? (item.ext || '') + sizeStr : ''}</span>
                </div>`;
            }).join('');

            if (items.length === 0) {
                list.innerHTML = '<div style="padding:1rem;color:var(--text-muted);">Empty folder</div>';
            }
        } catch (e) {
            document.getElementById('browser-list').innerHTML = `<div style="padding:1rem;color:var(--danger);">${e.message}</div>`;
        }
    }

    function browserItemClick(el) {
        const type = el.dataset.type;
        const path = el.dataset.path;

        if (type === 'dir' || type === 'drive') {
            navigateBrowserTo(path);
        } else {
            // Select file — highlight it
            document.querySelectorAll('.browser-item').forEach(i => i.classList.remove('selected'));
            el.classList.add('selected');
            browserSelectedPath = path;
        }
    }

    function browserItemDblClick(el) {
        const type = el.dataset.type;
        const path = el.dataset.path;

        if (type === 'dir' || type === 'drive') {
            navigateBrowserTo(path);
        } else {
            // Double-click on file: select it and close the browser
            browserSelectedPath = path;
            selectBrowserPath();
        }
    }

    function browserUp() {
        if (browserCurrentPath) {
            const parts = browserCurrentPath.replace(/\\/g, '/').split('/');
            parts.pop();
            const parent = parts.join('/') || '';
            navigateBrowserTo(parent);
        }
    }

    function selectBrowserPath() {
        const path = browserSelectedPath || browserCurrentPath;
        if (browserTargetInput && path) {
            document.getElementById(browserTargetInput).value = path;
        }
        closeBrowser();
    }

    function closeBrowser() {
        document.getElementById('file-browser-modal').style.display = 'none';
        browserSelectedPath = '';
        browserFileFilter = '';
    }

    // ---------------------------------------------------------------------------
    // Utility
    // ---------------------------------------------------------------------------
    function showStatus(elemId, msg, type) {
        const el = document.getElementById(elemId);
        if (!el) return;
        el.textContent = msg;
        el.className = 'status-msg ' + type;
    }

    // ---------------------------------------------------------------------------
    // Drag & Drop Upload
    // ---------------------------------------------------------------------------
    function initDropZone() {
        const dropZone = document.getElementById('drop-zone');
        const fileInput = document.getElementById('prj-file-input');
        if (!dropZone || !fileInput) return;

        // Click to browse
        dropZone.addEventListener('click', () => fileInput.click());

        // File input change
        fileInput.addEventListener('change', () => {
            if (fileInput.files.length > 0) {
                handleFileUpload(fileInput.files[0]);
            }
        });

        // Drag events
        dropZone.addEventListener('dragenter', (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.add('drag-over');
        });

        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.add('drag-over');
        });

        dropZone.addEventListener('dragleave', (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.remove('drag-over');
        });

        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.classList.remove('drag-over');

            const files = e.dataTransfer.files;
            if (files.length > 0) {
                const file = files[0];
                if (file.name.toLowerCase().endsWith('.prj')) {
                    handleFileUpload(file);
                } else {
                    alert('Please drop a .prj file.');
                }
            }
        });

        // Also support page-level drop (in case they miss the zone)
        document.body.addEventListener('dragover', (e) => {
            e.preventDefault();
            if (document.getElementById('drop-zone-landing')?.style.display !== 'none') {
                dropZone.classList.add('drag-over');
            }
        });
        document.body.addEventListener('dragleave', (e) => {
            if (!e.relatedTarget || e.relatedTarget === document.documentElement) {
                dropZone.classList.remove('drag-over');
            }
        });
        document.body.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('drag-over');
            const files = e.dataTransfer.files;
            if (files.length > 0 && files[0].name.toLowerCase().endsWith('.prj')) {
                if (document.getElementById('drop-zone-landing')?.style.display !== 'none') {
                    handleFileUpload(files[0]);
                }
            }
        });
    }

    async function handleFileUpload(file) {
        const dropZone = document.getElementById('drop-zone');
        const uploadProgress = document.getElementById('upload-progress');
        const statusText = document.getElementById('upload-status-text');

        // Show progress, hide drop zone
        dropZone.style.display = 'none';
        uploadProgress.style.display = 'flex';
        statusText.textContent = `Uploading ${file.name}...`;

        try {
            const formData = new FormData();
            formData.append('file', file);

            statusText.textContent = `Parsing ${file.name}...`;

            const resp = await fetch('/api/model/upload', {
                method: 'POST',
                body: formData,
            });

            if (!resp.ok) {
                const err = await resp.json().catch(() => ({ detail: resp.statusText }));
                throw new Error(err.detail || resp.statusText);
            }

            const data = await resp.json();
            statusText.textContent = 'Auto-configuring...';

            // Apply everything from the upload response
            applyUploadResult(data);

            // Also extract estimation data so it auto-fills when user visits the Estimation page
            forwardToEstimation(file);

            statusText.textContent = 'Done!';

            // Brief pause, then switch to config tab
            await new Promise(r => setTimeout(r, 500));
            document.getElementById('drop-zone-landing').style.display = 'none';
            uploadProgress.style.display = 'none';

        } catch (e) {
            // Show drop zone again on error
            dropZone.style.display = '';
            uploadProgress.style.display = 'none';
            alert('Upload failed: ' + e.message);
        }
    }

    async function forwardToEstimation(file) {
        // Extract estimation values in the background and store in localStorage
        // so the Estimation page auto-fills when visited.
        try {
            const formData = new FormData();
            formData.append('file', file);
            const resp = await fetch('/api/estimation/extract-from-prj', {
                method: 'POST',
                body: formData,
            });
            if (resp.ok) {
                const estData = await resp.json();
                localStorage.setItem('est_prj_pending', JSON.stringify(estData));
                console.log('[APP] Estimation data forwarded to localStorage for auto-fill');
            }
        } catch (e) {
            console.warn('[APP] Could not forward estimation data:', e);
        }
    }

    function applyUploadResult(data) {
        // Set project fields
        const nameEl = document.getElementById('project-name');
        const folderEl = document.getElementById('project-folder');
        const exeEl = document.getElementById('contam-exe');
        const prjEl = document.getElementById('prj-filepath');

        if (nameEl) nameEl.value = data.project_name;
        if (folderEl) folderEl.value = data.project_folder;
        if (exeEl) exeEl.value = data.contam_exe || '';
        if (prjEl) prjEl.value = data.filepath;

        // Set model id and populate all model data
        currentModelId = data.model_id;
        modelData.levels = data.levels;
        modelData.zones = data.zones;
        modelData.elements = data.elements;
        modelData.paths = data.paths;
        modelData.ahs = data.ahs;
        allZones = data.zones;
        allElements = data.elements;
        allPaths = data.paths;

        // Update badges
        document.getElementById('badge-levels').textContent = 'Levels: ' + data.num_levels;
        document.getElementById('badge-zones').textContent = 'Zones: ' + data.num_zones;
        document.getElementById('badge-elements').textContent = 'Elements: ' + data.num_flow_elements;
        document.getElementById('badge-paths').textContent = 'Paths: ' + data.num_airflow_paths;
        document.getElementById('badge-ahs').textContent = 'AHS: ' + data.num_ahs;
        document.getElementById('parsed-data').style.display = 'block';

        // Render data tables
        renderLevelsTable(data.levels);
        renderZonesTable(data.zones);
        renderAHSTable(data.ahs);
        renderElementsTable(data.elements);
        renderPathsTable(data.paths);
        populateZoneLevelFilter(data.zones);
        populatePathFilters(data.paths);

        // Populate config dropdowns
        populateDropdowns();

        // Apply auto-config suggestions
        lastSuggestions = data.auto_config;
        if (lastSuggestions && lastSuggestions.confidence !== 'low') {
            applySuggestions();
            showAutoConfigBanner(lastSuggestions);
            switchToTab('pressurization');
        }

        showStatus('parse-status', `Parsed successfully: ${data.project_name} (${data.version})`, 'success');
    }

    function renderLevelsTable(levels) {
        const tbody = document.querySelector('#tbl-levels tbody');
        tbody.innerHTML = levels.map(l =>
            `<tr><td>${l.index}</td><td>${l.name}</td><td>${l.ref_height.toFixed(3)}</td><td>${l.delta_height.toFixed(3)}</td><td>${l.num_icons}</td></tr>`
        ).join('');
    }

    function renderAHSTable(ahsList) {
        const tbody = document.querySelector('#tbl-ahs tbody');
        tbody.innerHTML = ahsList.map(a =>
            `<tr><td>${a.id}</td><td>${a.name}</td><td>${a.return_zone}</td><td>${a.supply_zone}</td><td>${a.return_path}</td><td>${a.supply_path}</td><td>${a.exhaust_path}</td></tr>`
        ).join('');
    }

    function populateZoneLevelFilter(zones) {
        const filter = document.getElementById('zone-level-filter');
        filter.innerHTML = '<option value="">All Levels</option>';
        const levels = [...new Set(zones.map(z => z.level_num))].sort((a, b) => a - b);
        levels.forEach(l => {
            const lvlName = zones.find(z => z.level_num === l)?.level_name || l;
            filter.innerHTML += `<option value="${l}">${lvlName} (${l})</option>`;
        });
    }

    function populatePathFilters(paths) {
        const levelFilter = document.getElementById('path-level-filter');
        levelFilter.innerHTML = '<option value="">All</option>';
        [...new Set(paths.map(p => p.level_num))].sort((a, b) => a - b).forEach(l => {
            levelFilter.innerHTML += `<option value="${l}">${l}</option>`;
        });

        const elemFilter = document.getElementById('path-elem-filter');
        elemFilter.innerHTML = '<option value="">All</option>';
        [...new Set(paths.map(p => p.flow_elem_name))].sort().forEach(n => {
            elemFilter.innerHTML += `<option value="${n}">${n}</option>`;
        });
    }

    // ---------------------------------------------------------------------------
    // Init
    // ---------------------------------------------------------------------------
    function initScenarioSelectAll() {
        const selectAll = document.getElementById('scenario-select-all');
        if (selectAll) {
            selectAll.addEventListener('change', () => {
                const checked = selectAll.checked;
                document.querySelectorAll('#scenario-body input[type="checkbox"]').forEach(cb => {
                    cb.checked = checked;
                });
            });
        }
    }

    function init() {
        initTabs();
        initScenarioSelectAll();
        initDropZone();
        loadRecentProjects();
        loadResultsScenarios();
    }

    document.addEventListener('DOMContentLoaded', init);

    // Public API
    return {
        createProject,
        openProject,
        detectContam,
        parseModel,
        filterZones,
        filterElements,
        filterPaths,
        updateStairTabs,
        updateCorridorTabs,
        updateFloorTabs,
        autoPopulateStair,
        autoPopulateCorridor,
        autoPopulateFloor,
        applySuggestions,
        togglePanel,
        addScenario: () => addScenario(`Scenario_${scenarios.length + 1}`, '', 70, 0, 270),
        addStandardSet,
        removeSelectedScenario,
        updateScenario,
        dryRun,
        startAnalysis,
        cancelAnalysis,
        loadResults,
        switchResultView,
        loadDetailedFireFloor,
        applyHighlighting,
        exportCSV,
        exportSummaryCSV,
        exportDetailedCSV,
        generateReport,
        generateModelReport,
        browseFolder,
        navigateBrowser,
        browserItemClick,
        browserItemDblClick,
        browserUp,
        selectBrowserPath,
        closeBrowser,
    };
})();
