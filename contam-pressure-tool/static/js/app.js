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
        const tbody = document.querySelector('#tbl-levels tbody');
        tbody.innerHTML = data.map(l =>
            `<tr><td>${l.index}</td><td>${l.name}</td><td>${l.ref_height.toFixed(3)}</td><td>${l.delta_height.toFixed(3)}</td><td>${l.num_icons}</td></tr>`
        ).join('');
    }

    async function loadZones() {
        const data = await api('GET', `/api/model/${currentModelId}/zones`);
        modelData.zones = data;
        allZones = data;
        renderZonesTable(data);

        // Populate level filter
        const filter = document.getElementById('zone-level-filter');
        filter.innerHTML = '<option value="">All Levels</option>';
        const levels = [...new Set(data.map(z => z.level_num))].sort((a, b) => a - b);
        levels.forEach(l => {
            const lvlName = data.find(z => z.level_num === l)?.level_name || l;
            filter.innerHTML += `<option value="${l}">${lvlName} (${l})</option>`;
        });
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
        const tbody = document.querySelector('#tbl-ahs tbody');
        tbody.innerHTML = data.map(a =>
            `<tr><td>${a.id}</td><td>${a.name}</td><td>${a.return_zone}</td><td>${a.supply_zone}</td><td>${a.return_path}</td><td>${a.supply_path}</td><td>${a.exhaust_path}</td></tr>`
        ).join('');
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

        // Populate path filters
        const levelFilter = document.getElementById('path-level-filter');
        levelFilter.innerHTML = '<option value="">All</option>';
        [...new Set(data.map(p => p.level_num))].sort((a, b) => a - b).forEach(l => {
            levelFilter.innerHTML += `<option value="${l}">${l}</option>`;
        });

        const elemFilter = document.getElementById('path-elem-filter');
        elemFilter.innerHTML = '<option value="">All</option>';
        [...new Set(data.map(p => p.flow_elem_name))].sort().forEach(n => {
            elemFilter.innerHTML += `<option value="${n}">${n}</option>`;
        });
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

        // Stair labels
        labelsRow.innerHTML = '';
        for (let i = 0; i < n; i++) {
            labelsRow.innerHTML += `
                <div class="form-group">
                    <label>Stair ${i + 1} Label</label>
                    <input type="text" id="stair-label-${i}" value="Stair_${i + 1}" onchange="App.updateStairTabs()">
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
                    supplyCell.textContent = ahs ? `Zone #${ahs.supply_zone}` : '-';
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

        // Find matching zones on each level
        modelData.levels.forEach(lvl => {
            const match = allZones.find(z => z.name === selectedName && z.level_num === lvl.index);
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
        modelData.levels.forEach(lvl => {
            const match = allZones.find(z => z.name === selectedName && z.level_num === lvl.index);
            if (match) {
                const sel = document.getElementById(`corr-${corrIdx}-zone-${lvl.index}`);
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

        banner.innerHTML = `
            <h3 style="color:var(--success); margin-bottom:0.5rem;">Auto-Configured from PRJ File (${confLabel} Confidence)</h3>
            <p>The model has been automatically analyzed and the following has been pre-filled:</p>
            <ul style="margin:0.5rem 0; padding-left:1.5rem; font-size:0.85rem;">
                ${details}
                ${config.supply_ahs ? `<li>Supply AHS: ${config.supply_ahs.name} (#${config.supply_ahs.id})</li>` : ''}
                ${config.return_ahs ? `<li>Return AHS: ${config.return_ahs.name} (#${config.return_ahs.id})</li>` : ''}
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

    function applySuggestions() {
        if (!lastSuggestions) return;
        const sg = lastSuggestions;

        // 1. Set number of stairs and labels
        const numStairs = sg.stairs.length || 1;
        document.getElementById('num-stairs').value = numStairs;

        // Build stair labels first (updateStairTabs needs them)
        updateStairTabs(); // creates label inputs

        // Set stair labels
        for (let i = 0; i < sg.stairs.length; i++) {
            const labelEl = document.getElementById(`stair-label-${i}`);
            if (labelEl) labelEl.value = sg.stairs[i].label;
        }

        // Rebuild tabs with correct labels
        updateStairTabs();

        // 2. Set number of corridors
        const numCorr = sg.corridors.length || 1;
        document.getElementById('num-corridors').value = numCorr;
        updateCorridorTabs();

        // 3. Populate stair zone selections and AHS
        for (let i = 0; i < sg.stairs.length; i++) {
            const stair = sg.stairs[i];
            // Use per-stair AHS if detected, otherwise fall back to global supply AHS
            const stairAhsId = stair.ahs_id || (sg.supply_ahs ? sg.supply_ahs.id : 0);

            for (const zoneInfo of stair.zones) {
                // Set zone dropdown — use zone_name matching as fallback
                // since zone names may vary across levels (e.g. Stair_4 vs Stair4)
                const zoneSel = document.getElementById(`stair-${i}-zone-${zoneInfo.level_num}`);
                if (zoneSel) {
                    zoneSel.value = zoneInfo.zone_id;
                    // Verify it was set (zone_id might not be in this level's dropdown)
                    if (zoneSel.value != zoneInfo.zone_id && zoneInfo.zone_name) {
                        // Try to find by name match in the dropdown options
                        for (const opt of zoneSel.options) {
                            if (opt.text.startsWith(zoneInfo.zone_name + ' ')) {
                                zoneSel.value = opt.value;
                                break;
                            }
                        }
                    }
                }

                // Set AHS
                const ahsSel = document.getElementById(`stair-${i}-ahs-${zoneInfo.level_num}`);
                if (ahsSel) ahsSel.value = stairAhsId;
            }
        }
        updateSupplyZones();

        // 4. Populate corridor zone selections and AHS
        for (let i = 0; i < sg.corridors.length; i++) {
            const corr = sg.corridors[i];
            // Use per-corridor AHS if detected, otherwise fall back to global return AHS
            const corrAhsId = corr.ahs_id || (sg.return_ahs ? sg.return_ahs.id : 0);

            for (const zoneInfo of corr.zones) {
                const zoneSel = document.getElementById(`corr-${i}-zone-${zoneInfo.level_num}`);
                if (zoneSel) {
                    zoneSel.value = zoneInfo.zone_id;
                    if (zoneSel.value != zoneInfo.zone_id && zoneInfo.zone_name) {
                        for (const opt of zoneSel.options) {
                            if (opt.text.startsWith(zoneInfo.zone_name + ' ')) {
                                zoneSel.value = opt.value;
                                break;
                            }
                        }
                    }
                }

                const ahsSel = document.getElementById(`corr-${i}-ahs-${zoneInfo.level_num}`);
                if (ahsSel) ahsSel.value = corrAhsId;
            }
        }

        // 5. Populate roof table and path selection
        updateRoofTable();
        updatePathSelection();

        // Set roof configs
        for (let i = 0; i < sg.roof_configs.length && i < sg.stairs.length; i++) {
            const roof = sg.roof_configs[i];
            const returnAhsId = sg.return_ahs ? sg.return_ahs.id : 0;

            const zoneSel = document.getElementById(`roof-zone-${i}`);
            if (zoneSel) zoneSel.value = roof.zone_id;

            const levelSel = document.getElementById(`roof-level-${i}`);
            if (levelSel) levelSel.value = roof.level_num;

            const ahsSel = document.getElementById(`roof-ahs-${i}`);
            if (ahsSel) ahsSel.value = returnAhsId;
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

        // 8. Show confirmation and switch to pressurization tab
        const banner = document.getElementById('suggestions-banner');
        if (banner) {
            banner.innerHTML = `
                <h3 style="color:var(--success);">Suggestions Applied</h3>
                <p>Stairs, corridors, AHS, roof configs, and path elements have been pre-filled.
                   Review and adjust values in Tab 3 (Pressurization Config), then set flow rates (SCFM) for each level.</p>
                <p><strong>Remaining steps:</strong> Set flow rates for each stair/corridor level, configure scenarios in Tab 4, then run.</p>
            `;
            banner.style.borderColor = 'rgba(39,174,96,0.4)';
            banner.style.background = 'rgba(39,174,96,0.08)';
        }
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

        // Get first base model if available
        const baseKeys = Object.keys(modelData.levels.length ? { 'default': '' } : {});

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

        try {
            const resp = await api('GET', `/api/results/${scenario}`);
            renderResultsTable(resp.columns, resp.data);
        } catch (e) { alert('Error loading results: ' + e.message); }
    }

    function renderResultsTable(columns, data) {
        const thead = document.getElementById('results-head');
        const tbody = document.getElementById('results-body');

        thead.innerHTML = '<tr>' + columns.map(c => `<th>${c}</th>`).join('') + '</tr>';

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

    // ---------------------------------------------------------------------------
    // File Browser
    // ---------------------------------------------------------------------------
    function browseFolder(targetInputId) {
        browserTargetInput = targetInputId;
        const currentVal = document.getElementById(targetInputId)?.value || '';
        document.getElementById('browser-path-input').value = currentVal;
        document.getElementById('file-browser-modal').style.display = 'flex';
        navigateBrowserTo(currentVal || '/');
    }

    async function navigateBrowser() {
        const path = document.getElementById('browser-path-input').value.trim();
        if (path) navigateBrowserTo(path);
    }

    async function navigateBrowserTo(path) {
        browserCurrentPath = path;
        try {
            const resp = await api('POST', '/api/browse/list', { path });
            browserCurrentPath = resp.current_path || path;
            document.getElementById('browser-path-input').value = browserCurrentPath;

            const list = document.getElementById('browser-list');
            list.innerHTML = resp.items.map(item => {
                const icon = item.type === 'dir' || item.type === 'drive' ? '&#128193;' : '&#128196;';
                return `<div class="browser-item" data-path="${item.path}" data-type="${item.type}" onclick="App.browserItemClick(this)">
                    <span class="icon">${icon}</span>
                    <span class="name">${item.name}</span>
                    <span class="meta">${item.type === 'file' ? (item.ext || '') : ''}</span>
                </div>`;
            }).join('');
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
            // Select file
            document.querySelectorAll('.browser-item').forEach(i => i.classList.remove('selected'));
            el.classList.add('selected');
            browserSelectedPath = path;
        }
    }

    function browserUp() {
        if (browserCurrentPath) {
            const parts = browserCurrentPath.replace(/\\/g, '/').split('/');
            parts.pop();
            const parent = parts.join('/') || '/';
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
    // Init
    // ---------------------------------------------------------------------------
    function init() {
        initTabs();
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
        autoPopulateStair,
        autoPopulateCorridor,
        applySuggestions,
        togglePanel,
        addScenario: () => addScenario(),
        addStandardSet,
        removeSelectedScenario,
        updateScenario,
        dryRun,
        startAnalysis,
        cancelAnalysis,
        loadResults,
        applyHighlighting,
        exportCSV,
        exportSummaryCSV,
        browseFolder,
        navigateBrowser,
        browserItemClick,
        browserUp,
        selectBrowserPath,
        closeBrowser,
    };
})();
