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
    let corridorDepressEnabled = true;
    let floorDepressEnabled = false;
    let runAllFloors = true;
    let selectedFloorIndices = null; // null = all
    let stairCriteriaGroups = []; // [{id, stairs: [labels], min_dp, max_dp}]

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
        if (search) filtered = filtered.filter(z => z.name.toLowerCase().includes(search) || (z.display_name || '').toLowerCase().includes(search));
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

        // Preserve existing label values before rebuilding
        const existingLabels = {};
        const existingPressurized = {};
        for (let i = 0; i < n; i++) {
            const el = document.getElementById(`stair-label-${i}`);
            if (el && el.value && el.value !== `Stair_${i + 1}`) {
                existingLabels[i] = el.value;
            }
            const cb = document.getElementById(`stair-pressurized-${i}`);
            if (cb) {
                existingPressurized[i] = cb.checked;
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
            const isPressurized = existingPressurized[i] !== undefined ? existingPressurized[i] : true;
            tabsEl.innerHTML += `<button class="sub-tab ${i === 0 ? 'active' : ''}" data-subtab="stair-panel-${i}">${label}</button>`;

            let tableRows = '';
            modelData.levels.forEach(lvl => {
                tableRows += `<tr>
                    <td>${lvl.name}</td>
                    <td>${makeZoneSelect(`stair-${i}-zone-${lvl.index}`, lvl.index)}</td>
                    <td><input type="number" id="stair-${i}-flow-${lvl.index}" value="0" min="0" step="100"></td>
                    <td style="display:none">${makeAHSSelect(`stair-${i}-ahs-${lvl.index}`)}</td>
                    <td style="display:none" id="stair-${i}-supply-${lvl.index}" class="supply-cell">-</td>
                    <td><input type="number" id="stair-${i}-icon-${lvl.index}" value="128" min="0"></td>
                    <td><input type="number" id="stair-${i}-col-${lvl.index}" value="1" min="0"></td>
                    <td><input type="number" id="stair-${i}-row-${lvl.index}" value="1" min="0"></td>
                </tr>`;
            });

            panelsEl.innerHTML += `
                <div id="stair-panel-${i}" class="sub-panel ${i === 0 ? 'active' : ''}">
                    <!-- Pressurized checkbox -->
                    <div class="stair-pressurized-toggle">
                        <input type="checkbox" id="stair-pressurized-${i}" ${isPressurized ? 'checked' : ''} onchange="App.toggleStairPressurized(${i})">
                        <label for="stair-pressurized-${i}">Pressurized Stair</label>
                        <span style="font-size:0.75rem;color:var(--text-secondary);margin-left:auto;">Uncheck to disable pressurization for this stair</span>
                    </div>
                    <div id="stair-content-${i}" class="${isPressurized ? '' : 'stair-disabled-overlay'}">
                        <!-- Bulk SCFM Tools -->
                        <div class="bulk-scfm-tools">
                            <h4>Bulk Flow Rate (SCFM) Tools</h4>
                            <div class="bulk-scfm-row">
                                <div class="form-group">
                                    <label>Apply Value to All</label>
                                    <input type="number" id="stair-${i}-bulk-value" value="0" min="0" step="100" style="width:100px;">
                                </div>
                                <button class="btn btn-sm" onclick="App.applyBulkSCFM(${i}, 'stair')">Apply to All</button>
                                <button class="btn btn-sm" onclick="App.importExcelSCFM(${i}, 'stair')">&#128196; Import from Excel</button>
                            </div>
                            <div class="alternating-section">
                                <div class="bulk-scfm-row">
                                    <div class="form-group">
                                        <label>Alternating Value</label>
                                        <input type="number" id="stair-${i}-alt-value" value="0" min="0" step="100" style="width:100px;">
                                    </div>
                                    <div class="form-group">
                                        <label>Apply Every N Floors</label>
                                        <input type="number" id="stair-${i}-alt-skip" value="2" min="2" max="20" step="1" style="width:70px;">
                                    </div>
                                    <div class="form-group">
                                        <label>Start at Floor #</label>
                                        <input type="number" id="stair-${i}-alt-start" value="1" min="1" step="1" style="width:70px;">
                                    </div>
                                    <button class="btn btn-sm" onclick="App.applyAlternatingSCFM(${i}, 'stair')">Apply Alternating</button>
                                </div>
                            </div>
                        </div>
                        <div class="btn-row" style="margin-bottom:0.5rem;">
                            <button class="btn btn-sm" onclick="App.autoPopulateStair(${i})">Auto-Populate by Zone Name</button>
                        </div>
                        <div class="table-container">
                            <table>
                                <thead><tr><th>Level</th><th>Zone</th><th>Flow Rate (SCFM)</th><th style="display:none">AHS</th><th style="display:none">Supply Zone</th><th>Icon Type</th><th>Col</th><th>Row</th></tr></thead>
                                <tbody>${tableRows}</tbody>
                            </table>
                        </div>
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

    function toggleStairPressurized(stairIdx) {
        const cb = document.getElementById(`stair-pressurized-${stairIdx}`);
        const content = document.getElementById(`stair-content-${stairIdx}`);
        if (!cb || !content) return;

        if (cb.checked) {
            content.classList.remove('stair-disabled-overlay');
        } else {
            content.classList.add('stair-disabled-overlay');
            modelData.levels.forEach(lvl => {
                const flowEl = document.getElementById(`stair-${stairIdx}-flow-${lvl.index}`);
                if (flowEl) flowEl.value = 0;
            });
        }
        // Refresh dependent sections
        updateRoofTable();
        updatePathSelection();
        renderStairCriteriaGroups();
    }

    function applyBulkSCFM(groupIdx, prefix) {
        const valueEl = document.getElementById(`${prefix}-${groupIdx}-bulk-value`);
        if (!valueEl) return;
        const value = parseFloat(valueEl.value) || 0;
        modelData.levels.forEach(lvl => {
            const flowEl = document.getElementById(`${prefix}-${groupIdx}-flow-${lvl.index}`);
            if (flowEl) flowEl.value = value;
        });
    }

    function applyAlternatingSCFM(groupIdx, prefix) {
        const valueEl = document.getElementById(`${prefix}-${groupIdx}-alt-value`);
        const skipEl = document.getElementById(`${prefix}-${groupIdx}-alt-skip`);
        const startEl = document.getElementById(`${prefix}-${groupIdx}-alt-start`);
        if (!valueEl || !skipEl) return;
        
        const value = parseFloat(valueEl.value) || 0;
        const skip = parseInt(skipEl.value) || 2;
        const startFloor = parseInt(startEl?.value) || 1;

        modelData.levels.forEach((lvl, idx) => {
            const flowEl = document.getElementById(`${prefix}-${groupIdx}-flow-${lvl.index}`);
            if (!flowEl) return;
            // Apply value at every Nth floor starting from startFloor (1-indexed)
            const floorNum = idx + 1;
            if (floorNum >= startFloor && (floorNum - startFloor) % skip === 0) {
                flowEl.value = value;
            }
        });
    }

    // Pending action after file browser selection (for Excel import)
    let _pendingBrowserCallback = null;

    async function importExcelSCFM(groupIdx, prefix) {
        // Open the file browser modal, and when user selects a file, import it
        const projFolder = document.getElementById('project-folder')?.value?.trim() || '';
        const sep = projFolder.includes('\\') ? '\\' : '/';
        const templatesPath = projFolder ? projFolder + sep + 'scfm_templates' : '';

        // Set a callback for when the user clicks Select in the browser
        _pendingBrowserCallback = function(selectedPath) {
            if (selectedPath) {
                _doExcelImport(groupIdx, prefix, selectedPath);
            }
        };

        // Open browser — don't target an input, the callback handles it
        browserTargetInput = null;
        browserSelectedPath = '';
        browserFileFilter = '.xlsx';
        const startPath = templatesPath || projFolder;
        document.getElementById('browser-path-input').value = startPath;
        document.getElementById('file-browser-modal').style.display = 'flex';
        navigateBrowserTo(startPath);
    }

    async function _doExcelImport(groupIdx, prefix, filePath) {
        if (!filePath) return;

        try {
            const resp = await api('POST', '/api/tab3/import-excel', { filepath: filePath });
            if (!resp.data || resp.data.length === 0) {
                alert('No data found in the file.');
                return;
            }

            // If file has multiple SCFM columns, ask which to use
            const numCols = resp.columns.length - 1; // minus the level column
            let colIdx = 0;
            if (numCols > 1) {
                const colNames = resp.columns.slice(1);
                const choice = prompt(
                    `File has ${numCols} data columns:\n` +
                    colNames.map((c, i) => `${i + 1}: ${c}`).join('\n') +
                    `\n\nEnter column number (1-${numCols}):`, '1'
                );
                colIdx = (parseInt(choice) || 1) - 1;
                if (colIdx < 0 || colIdx >= numCols) colIdx = 0;
            }

            // Apply values to flow rate inputs
            const levels = modelData.levels;
            let count = 0;
            resp.data.forEach((row, rowIdx) => {
                if (rowIdx < levels.length) {
                    const flowEl = document.getElementById(`${prefix}-${groupIdx}-flow-${levels[rowIdx].index}`);
                    if (flowEl) {
                        const val = row[colIdx + 1];
                        if (val !== null && val !== undefined && val !== '') {
                            flowEl.value = val;
                            count++;
                        }
                    }
                }
            });

            alert(`Imported ${count} flow rate values from:\n${filePath}`);
        } catch (e) {
            alert('Import failed: ' + e.message);
        }
    }

    async function generateExcelTemplates() {
        const folder = document.getElementById('project-folder')?.value?.trim();
        if (!folder) {
            alert('Set a project folder in Tab 1 first.');
            return;
        }
        if (modelData.levels.length === 0) {
            alert('Parse a PRJ model in Tab 2 first so level names are available.');
            return;
        }

        const numStairs = parseInt(document.getElementById('num-stairs').value) || 1;
        const numCorr = parseInt(document.getElementById('num-corridors').value) || 1;
        const numFloors = parseInt(document.getElementById('num-floors').value) || 0;

        // Gather stair labels
        const stairs = [];
        for (let i = 0; i < numStairs; i++) {
            stairs.push({ label: document.getElementById(`stair-label-${i}`)?.value || `Stair_${i + 1}` });
        }

        // Corridor labels
        const corridors = [];
        for (let i = 0; i < numCorr; i++) {
            corridors.push({ label: `Corridor_${i + 1}` });
        }

        // Floor zone labels
        const floor_zones = [];
        for (let i = 0; i < numFloors; i++) {
            floor_zones.push({ label: `Floor_Zone_${i + 1}` });
        }

        // Levels from model
        const levels = modelData.levels.map(l => ({ index: l.index, name: l.name }));

        try {
            const resp = await api('POST', '/api/tab3/generate-templates', {
                project_folder: folder,
                model_id: currentModelId || '',
                levels,
                stairs,
                corridors,
                floor_zones,
                num_stairs: numStairs,
                num_corridors: numCorr,
                num_floors: numFloors,
            });

            let msg = `Generated ${resp.count} SCFM template(s) in:\n${resp.templates_folder}\n\nFiles created:\n`;
            resp.generated.forEach(g => {
                msg += `  • ${g.filename}\n`;
            });
            msg += '\nFill in the SCFM values in Excel, then use "Import from Excel" on each section to load them.';
            alert(msg);
        } catch (e) {
            alert('Template generation failed: ' + e.message);
        }
    }

    async function saveTab3Config() {
        const folder = document.getElementById('project-folder')?.value?.trim();
        if (!folder) {
            alert('Set a project folder in Tab 1 first.');
            return;
        }

        const config = collectConfig();
        try {
            await api('POST', '/api/tab3/save', {
                project_folder: folder,
                config: config,
            });
            alert('Configuration saved successfully.');
        } catch (e) {
            alert('Save failed: ' + e.message);
        }
    }

    async function loadTab3Config() {
        const folder = document.getElementById('project-folder')?.value?.trim();
        if (!folder) {
            alert('Set a project folder in Tab 1 first.');
            return;
        }

        try {
            const resp = await api('POST', '/api/tab3/load', {
                project_folder: folder,
            });
            if (!resp.config) {
                alert('No saved configuration found.');
                return;
            }

            const cfg = resp.config;

            // Check model is parsed — needed for zone selects to have options
            if (modelData.levels.length === 0) {
                alert('Please parse a PRJ model in Tab 2 first, then load config.');
                return;
            }

            // Restore Tab 1 fields
            if (cfg.project_name) {
                const el = document.getElementById('project-name');
                if (el) el.value = cfg.project_name;
            }
            if (cfg.contam_exe) {
                const el = document.getElementById('contam-exe');
                if (el) el.value = cfg.contam_exe;
            }

            // Restore corridor/floor depress toggles
            if (cfg.corridor_depress_enabled !== undefined) {
                corridorDepressEnabled = cfg.corridor_depress_enabled;
                const cb = document.getElementById('corridor-depress-enabled');
                if (cb) { cb.checked = corridorDepressEnabled; toggleCorridorDepress(); }
            }
            if (cfg.floor_depress_enabled !== undefined) {
                floorDepressEnabled = cfg.floor_depress_enabled;
                const cb = document.getElementById('floor-depress-enabled');
                if (cb) { cb.checked = floorDepressEnabled; toggleFloorDepress(); }
            }

            // Restore simulation level selection (run all floors / specific floors)
            if (cfg.selected_floors !== null && cfg.selected_floors !== undefined) {
                runAllFloors = false;
                selectedFloorIndices = cfg.selected_floors;
                const cb = document.getElementById('run-all-floors');
                if (cb) { cb.checked = false; toggleRunAllFloors(); }
                // Check specific floor checkboxes
                if (Array.isArray(cfg.selected_floors)) {
                    setTimeout(() => {
                        cfg.selected_floors.forEach(idx => {
                            const fc = document.getElementById(`floor-check-${idx}`);
                            if (fc) fc.checked = true;
                        });
                        parseFloorRange();
                    }, 100);
                }
            } else {
                runAllFloors = true;
                selectedFloorIndices = null;
                const cb = document.getElementById('run-all-floors');
                if (cb) cb.checked = true;
            }

            // Restore stairs — set labels first, then rebuild tabs, then populate values
            if (cfg.stairs && cfg.stairs.length > 0) {
                document.getElementById('num-stairs').value = cfg.stairs.length;

                // First pass: create label inputs
                updateStairTabs();
                for (let i = 0; i < cfg.stairs.length; i++) {
                    const stair = cfg.stairs[i];
                    const labelEl = document.getElementById(`stair-label-${i}`);
                    if (labelEl && stair.label) labelEl.value = stair.label;
                    // Restore pressurized flag
                    const pressEl = document.getElementById(`stair-pressurized-${i}`);
                    if (pressEl && stair.pressurized !== undefined) {
                        pressEl.checked = stair.pressurized;
                        toggleStairPressurized(i);
                    }
                }
                // Second pass: rebuild with correct labels
                updateStairTabs();

                // Third pass: populate data values
                for (let i = 0; i < cfg.stairs.length; i++) {
                    const stair = cfg.stairs[i];
                    // Re-set pressurized flag (updateStairTabs may have reset it)
                    const pressEl = document.getElementById(`stair-pressurized-${i}`);
                    if (pressEl && stair.pressurized !== undefined) {
                        pressEl.checked = stair.pressurized;
                    }

                    if (stair.levels) {
                        for (const lvl of stair.levels) {
                            const zoneSel = document.getElementById(`stair-${i}-zone-${lvl.level_num}`);
                            if (zoneSel) zoneSel.value = lvl.zone_id || 0;
                            const flowEl = document.getElementById(`stair-${i}-flow-${lvl.level_num}`);
                            if (flowEl) flowEl.value = lvl.flow_rate || 0;
                            const ahsSel = document.getElementById(`stair-${i}-ahs-${lvl.level_num}`);
                            if (ahsSel) ahsSel.value = lvl.ahs_id || 0;
                            const iconEl = document.getElementById(`stair-${i}-icon-${lvl.level_num}`);
                            if (iconEl) iconEl.value = lvl.icon_type || 128;
                            const colEl = document.getElementById(`stair-${i}-col-${lvl.level_num}`);
                            if (colEl) colEl.value = lvl.icon_col || 1;
                            const rowEl = document.getElementById(`stair-${i}-row-${lvl.level_num}`);
                            if (rowEl) rowEl.value = lvl.icon_row || 1;
                        }
                    }
                }
            }

            // Restore corridors
            if (cfg.corridors && cfg.corridors.length > 0) {
                document.getElementById('num-corridors').value = cfg.corridors.length;
                updateCorridorTabs();

                for (let i = 0; i < cfg.corridors.length; i++) {
                    const corr = cfg.corridors[i];
                    if (corr.levels) {
                        for (const lvl of corr.levels) {
                            const zoneSel = document.getElementById(`corr-${i}-zone-${lvl.level_num}`);
                            if (zoneSel) zoneSel.value = lvl.zone_id || 0;
                            const flowEl = document.getElementById(`corr-${i}-flow-${lvl.level_num}`);
                            if (flowEl) flowEl.value = lvl.flow_rate || 0;
                            const ahsSel = document.getElementById(`corr-${i}-ahs-${lvl.level_num}`);
                            if (ahsSel) ahsSel.value = lvl.ahs_id || 0;
                            const colEl = document.getElementById(`corr-${i}-col-${lvl.level_num}`);
                            if (colEl) colEl.value = lvl.icon_col || 1;
                            const rowEl = document.getElementById(`corr-${i}-row-${lvl.level_num}`);
                            if (rowEl) rowEl.value = lvl.icon_row || 1;
                        }
                    }
                }
            }

            // Restore floor zones
            if (cfg.floor_zones && cfg.floor_zones.length > 0) {
                document.getElementById('num-floors').value = cfg.floor_zones.length;
                updateFloorTabs();

                for (let i = 0; i < cfg.floor_zones.length; i++) {
                    const fz = cfg.floor_zones[i];
                    if (fz.levels) {
                        for (const lvl of fz.levels) {
                            const zoneSel = document.getElementById(`floor-${i}-zone-${lvl.level_num}`);
                            if (zoneSel) zoneSel.value = lvl.zone_id || 0;
                            const flowEl = document.getElementById(`floor-${i}-flow-${lvl.level_num}`);
                            if (flowEl) flowEl.value = lvl.flow_rate || 0;
                            const ahsSel = document.getElementById(`floor-${i}-ahs-${lvl.level_num}`);
                            if (ahsSel) ahsSel.value = lvl.ahs_id || 0;
                            const colEl = document.getElementById(`floor-${i}-col-${lvl.level_num}`);
                            if (colEl) colEl.value = lvl.icon_col || 1;
                            const rowEl = document.getElementById(`floor-${i}-row-${lvl.level_num}`);
                            if (rowEl) rowEl.value = lvl.icon_row || 1;
                        }
                    }
                }
            }

            // Restore roof configs
            if (cfg.roof_configs) {
                // Rebuild roof table first
                updateRoofTable();
                for (let i = 0; i < cfg.roof_configs.length; i++) {
                    const roof = cfg.roof_configs[i];
                    const zoneSel = document.getElementById(`roof-zone-${i}`);
                    if (zoneSel) zoneSel.value = roof.zone_id || 0;
                    const levelSel = document.getElementById(`roof-level-${i}`);
                    if (levelSel) levelSel.value = roof.level_num || '';
                    const flowEl = document.getElementById(`roof-flow-${i}`);
                    if (flowEl) flowEl.value = roof.flow_rate || 0;
                    const ahsSel = document.getElementById(`roof-ahs-${i}`);
                    if (ahsSel) ahsSel.value = roof.ahs_id || 0;
                    const iconEl = document.getElementById(`roof-icon-${i}`);
                    if (iconEl && roof.icon_type) iconEl.value = roof.icon_type;
                    const colEl = document.getElementById(`roof-col-${i}`);
                    if (colEl && roof.icon_col) colEl.value = roof.icon_col;
                    const rowEl = document.getElementById(`roof-row-${i}`);
                    if (rowEl && roof.icon_row) rowEl.value = roof.icon_row;
                }
            }

            // Restore path selections — must happen AFTER updatePathSelection is called
            updatePathSelection();
            if (cfg.stairs) {
                for (let i = 0; i < cfg.stairs.length; i++) {
                    const stair = cfg.stairs[i];
                    if (stair.paths) {
                        for (const [key, val] of Object.entries(stair.paths)) {
                            const sel = document.getElementById(`path-${key}-${i}`);
                            if (sel && val) sel.value = val;
                        }
                    }
                }
            }

            // Restore corridor path name
            if (cfg.corridors?.[0]?.path_name) {
                const sel = document.getElementById('corridor-path-name');
                if (sel) sel.value = cfg.corridors[0].path_name;
            }
            // Restore floor path name
            if (cfg.floor_path_name) {
                const sel = document.getElementById('floor-path-name');
                if (sel) sel.value = cfg.floor_path_name;
            }

            // Restore scenarios
            if (cfg.scenarios && cfg.scenarios.length > 0) {
                scenarios = cfg.scenarios.map(s => ({
                    name: s.name,
                    base_model: s.base_model_path || '',
                    temp_f: s.temp_f,
                    wind_mph: s.wind_mph,
                    wind_dir: s.wind_dir,
                }));
                renderScenarios();
            }

            // Restore acceptance criteria (Tab 6)
            if (cfg.acceptance_criteria) {
                const ac = cfg.acceptance_criteria;
                const minFloor = document.getElementById('min-dp-floor');
                const maxFloor = document.getElementById('max-dp-floor');
                const minCorr = document.getElementById('min-dp-corr');
                const maxCorr = document.getElementById('max-dp-corr');
                if (minFloor && ac.min_dp_floor != null) minFloor.value = ac.min_dp_floor;
                if (maxFloor && ac.max_dp_floor != null) maxFloor.value = ac.max_dp_floor;
                if (minCorr && ac.min_dp_corr != null) minCorr.value = ac.min_dp_corr;
                if (maxCorr && ac.max_dp_corr != null) maxCorr.value = ac.max_dp_corr;
                // Restore stair criteria groups
                if (ac.stair_groups && ac.stair_groups.length > 0) {
                    stairCriteriaGroups = ac.stair_groups;
                    renderStairCriteriaGroups();
                }
            }

            updateSupplyZones();
            alert('Configuration loaded successfully.');
        } catch (e) {
            alert('Load failed: ' + e.message);
        }
    }

    async function updatePrjFile() {
        const prjPath = document.getElementById('prj-filepath')?.value?.trim();
        if (!prjPath) {
            alert('No PRJ file loaded. Parse a PRJ file in Tab 2 first.');
            return;
        }

        const config = collectConfig();
        const outputPath = prompt('Enter output PRJ file path:', prjPath.replace('.prj', '_updated.prj'));
        if (!outputPath) return;

        try {
            const resp = await api('POST', '/api/tab3/update-prj', {
                ...config,
                base_prj_path: prjPath,
                output_path: outputPath,
            });
            alert(`PRJ file updated successfully:\n${resp.output_path}`);
        } catch (e) {
            alert('Update failed: ' + e.message);
        }
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

    async function autoPopulateStair(stairIdx) {
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
            const stairLabel = document.getElementById(`stair-label-${stairIdx}`)?.value || '';
            selectedName = prompt('Enter zone name to auto-populate:', stairLabel || 'Stair_1');
            if (!selectedName) return;
        }

        // Find matching zones on each level (case-insensitive)
        const nameLower = selectedName.toLowerCase();
        let firstMatchZoneId = null;
        modelData.levels.forEach(lvl => {
            const match = allZones.find(z => z.name.toLowerCase() === nameLower && z.level_num === lvl.index)
                       || allZones.find(z => z.name === selectedName && z.level_num === lvl.index);
            if (match) {
                const sel = document.getElementById(`stair-${stairIdx}-zone-${lvl.index}`);
                if (sel) sel.value = match.id;
                if (!firstMatchZoneId) firstMatchZoneId = match.id;
                // Auto-set AHS to #1 (Supply) for stairs — uses 1 even if no AHS in base model
                const ahsSel = document.getElementById(`stair-${stairIdx}-ahs-${lvl.index}`);
                if (ahsSel) ahsSel.value = modelData.ahs.length > 0 ? modelData.ahs[0].id : 1;
            }
        });

        // Try to fetch icon positions from PRJ
        await _autoPlaceIcons(stairIdx, 'stair');
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
                    <td style="display:none">${makeAHSSelect(`corr-${i}-ahs-${lvl.index}`)}</td>
                    <td><input type="number" id="corr-${i}-icon-${lvl.index}" value="129" min="0"></td>
                    <td><input type="number" id="corr-${i}-col-${lvl.index}" value="1" min="0"></td>
                    <td><input type="number" id="corr-${i}-row-${lvl.index}" value="1" min="0"></td>
                </tr>`;
            });

            panelsEl.innerHTML += `
                <div id="corr-panel-${i}" class="sub-panel ${i === 0 ? 'active' : ''}">
                    <!-- Bulk SCFM Tools -->
                    <div class="bulk-scfm-tools">
                        <h4>Bulk Flow Rate (SCFM) Tools</h4>
                        <div class="bulk-scfm-row">
                            <div class="form-group">
                                <label>Apply Value to All</label>
                                <input type="number" id="corr-${i}-bulk-value" value="0" min="0" step="100" style="width:100px;">
                            </div>
                            <button class="btn btn-sm" onclick="App.applyBulkSCFM(${i}, 'corr')">Apply to All</button>
                            <button class="btn btn-sm" onclick="App.importExcelSCFM(${i}, 'corr')">&#128196; Import from Excel</button>
                        </div>
                        <div class="alternating-section">
                            <div class="bulk-scfm-row">
                                <div class="form-group">
                                    <label>Alternating Value</label>
                                    <input type="number" id="corr-${i}-alt-value" value="0" min="0" step="100" style="width:100px;">
                                </div>
                                <div class="form-group">
                                    <label>Apply Every N Floors</label>
                                    <input type="number" id="corr-${i}-alt-skip" value="2" min="2" max="20" step="1" style="width:70px;">
                                </div>
                                <div class="form-group">
                                    <label>Start at Floor #</label>
                                    <input type="number" id="corr-${i}-alt-start" value="1" min="1" step="1" style="width:70px;">
                                </div>
                                <button class="btn btn-sm" onclick="App.applyAlternatingSCFM(${i}, 'corr')">Apply Alternating</button>
                            </div>
                        </div>
                    </div>
                    <div class="btn-row" style="margin-bottom:0.5rem;">
                        <button class="btn btn-sm" onclick="App.autoPopulateCorridor(${i})">Auto-Populate by Zone Name</button>
                    </div>
                    <div class="table-container">
                        <table>
                            <thead><tr><th>Level</th><th>Zone</th><th>Flow Rate (SCFM)</th><th style="display:none">AHS</th><th>Icon Type</th><th>Col</th><th>Row</th></tr></thead>
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

    async function autoPopulateCorridor(corrIdx) {
        let selectedName = null;
        for (const lvl of modelData.levels) {
            const sel = document.getElementById(`corr-${corrIdx}-zone-${lvl.index}`);
            if (sel && parseInt(sel.value) > 0) {
                const zone = allZones.find(z => z.id === parseInt(sel.value));
                if (zone) { selectedName = zone.name; break; }
            }
        }
        if (!selectedName) {
            selectedName = prompt('Enter corridor zone name:', 'Corridor');
            if (!selectedName) return;
        }
        const nameLower = selectedName.toLowerCase();
        modelData.levels.forEach(lvl => {
            const match = allZones.find(z => z.name.toLowerCase() === nameLower && z.level_num === lvl.index)
                       || allZones.find(z => z.name === selectedName && z.level_num === lvl.index);
            if (match) {
                const sel = document.getElementById(`corr-${corrIdx}-zone-${lvl.index}`);
                if (sel) sel.value = match.id;
                // Auto-set AHS to #2 (Return) for corridors — uses 2 even if no AHS in base model
                const ahsSel = document.getElementById(`corr-${corrIdx}-ahs-${lvl.index}`);
                if (ahsSel) ahsSel.value = modelData.ahs.length > 1 ? modelData.ahs[1].id : 2;
            }
        });
        await _autoPlaceIcons(corrIdx, 'corr');
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
                    <td style="display:none">${makeAHSSelect(`floor-${i}-ahs-${lvl.index}`)}</td>
                    <td><input type="number" id="floor-${i}-icon-${lvl.index}" value="129" min="0"></td>
                    <td><input type="number" id="floor-${i}-col-${lvl.index}" value="1" min="0"></td>
                    <td><input type="number" id="floor-${i}-row-${lvl.index}" value="1" min="0"></td>
                </tr>`;
            });

            panelsEl.innerHTML += `
                <div id="floor-panel-${i}" class="sub-panel ${i === 0 ? 'active' : ''}">
                    <!-- Bulk SCFM Tools -->
                    <div class="bulk-scfm-tools">
                        <h4>Bulk Flow Rate (SCFM) Tools</h4>
                        <div class="bulk-scfm-row">
                            <div class="form-group">
                                <label>Apply Value to All</label>
                                <input type="number" id="floor-${i}-bulk-value" value="0" min="0" step="100" style="width:100px;">
                            </div>
                            <button class="btn btn-sm" onclick="App.applyBulkSCFM(${i}, 'floor')">Apply to All</button>
                            <button class="btn btn-sm" onclick="App.importExcelSCFM(${i}, 'floor')">&#128196; Import from Excel</button>
                        </div>
                        <div class="alternating-section">
                            <div class="bulk-scfm-row">
                                <div class="form-group">
                                    <label>Alternating Value</label>
                                    <input type="number" id="floor-${i}-alt-value" value="0" min="0" step="100" style="width:100px;">
                                </div>
                                <div class="form-group">
                                    <label>Apply Every N Floors</label>
                                    <input type="number" id="floor-${i}-alt-skip" value="2" min="2" max="20" step="1" style="width:70px;">
                                </div>
                                <div class="form-group">
                                    <label>Start at Floor #</label>
                                    <input type="number" id="floor-${i}-alt-start" value="1" min="1" step="1" style="width:70px;">
                                </div>
                                <button class="btn btn-sm" onclick="App.applyAlternatingSCFM(${i}, 'floor')">Apply Alternating</button>
                            </div>
                        </div>
                    </div>
                    <div class="btn-row" style="margin-bottom:0.5rem;">
                        <button class="btn btn-sm" onclick="App.autoPopulateFloor(${i})">Auto-Populate by Zone Name</button>
                    </div>
                    <div class="table-container">
                        <table>
                            <thead><tr><th>Level</th><th>Zone</th><th>Flow Rate (SCFM)</th><th style="display:none">AHS</th><th>Icon Type</th><th>Col</th><th>Row</th></tr></thead>
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

    async function autoPopulateFloor(floorIdx) {
        let selectedName = null;
        for (const lvl of modelData.levels) {
            const sel = document.getElementById(`floor-${floorIdx}-zone-${lvl.index}`);
            if (sel && parseInt(sel.value) > 0) {
                const zone = allZones.find(z => z.id === parseInt(sel.value));
                if (zone) { selectedName = zone.name; break; }
            }
        }
        if (!selectedName) {
            selectedName = prompt('Enter floor zone name (e.g., "EXH.Floor", "Floor"):', 'EXH.Floor');
            if (!selectedName) return;
        }
        const nameLower = selectedName.toLowerCase();
        modelData.levels.forEach(lvl => {
            const match = allZones.find(z => z.name.toLowerCase() === nameLower && z.level_num === lvl.index)
                       || allZones.find(z => z.name === selectedName && z.level_num === lvl.index);
            if (match) {
                const sel = document.getElementById(`floor-${floorIdx}-zone-${lvl.index}`);
                if (sel) sel.value = match.id;
                // Auto-set AHS to #2 (Return) for floor depress — uses 2 even if no AHS in base model
                const ahsSel = document.getElementById(`floor-${floorIdx}-ahs-${lvl.index}`);
                if (ahsSel) ahsSel.value = modelData.ahs.length > 1 ? modelData.ahs[1].id : 2;
            }
        });
        await _autoPlaceIcons(floorIdx, 'floor');
    }

    // Helper: fetch icon positions from PRJ and set col/row for a group
    async function _autoPlaceIcons(groupIdx, prefix) {
        const prjPath = document.getElementById('prj-filepath')?.value?.trim();
        if (!prjPath) return;
        try {
            const resp = await api('POST', '/api/tab3/zone-icons', { prj_path: prjPath });
            const placements = resp.zone_placements || {};
            modelData.levels.forEach(lvl => {
                const zoneId = document.getElementById(`${prefix}-${groupIdx}-zone-${lvl.index}`)?.value;
                if (!zoneId || zoneId === '0') return;
                const info = placements[zoneId];
                if (info) {
                    const colEl = document.getElementById(`${prefix}-${groupIdx}-col-${lvl.index}`);
                    const rowEl = document.getElementById(`${prefix}-${groupIdx}-row-${lvl.index}`);
                    if (colEl) colEl.value = info.supply_col;
                    if (rowEl) rowEl.value = info.supply_row;
                }
            });
        } catch (e) {
            console.warn('Could not fetch icon positions:', e);
        }
    }

    // Auto-populate airflow path selections based on stair label naming conventions
    function autoPopulatePaths() {
        const n = parseInt(document.getElementById('num-stairs').value) || 1;
        const elemNames = modelData.elements.map(e => e.name);
        for (let i = 0; i < n; i++) {
            const isPressurized = document.getElementById(`stair-pressurized-${i}`)?.checked !== false;
            if (!isPressurized) continue;
            const label = document.getElementById(`stair-label-${i}`)?.value || `Stair_${i + 1}`;
            // Try standard naming: Door-{Label}-S2V, Door-{Label}-V2C, Door-{Label}-EXT
            // Also try with underscores removed, S2C variant, etc.
            const variants = [label, label.replace(/_/g, ''), label.replace(/ /g, '')];
            for (const pk of ['s2v', 'v2c', 'ext']) {
                const sel = document.getElementById(`path-${pk}-${i}`);
                if (!sel || (sel.value && sel.value !== '')) continue; // Skip if already set
                const suffixes = pk === 's2v' ? ['S2V', 'S2V1', 'S2C'] :
                                 pk === 'v2c' ? ['V2C', 'V2C1'] :
                                 pk === 'ext' ? ['EXT', 'S2EXT'] : [];
                let found = false;
                for (const v of variants) {
                    for (const sfx of suffixes) {
                        const candidate = `Door-${v}-${sfx}`;
                        if (elemNames.includes(candidate)) {
                            sel.value = candidate;
                            found = true;
                            break;
                        }
                    }
                    if (found) break;
                }
            }
        }
    }

    function updateRoofTable() {
        const n = parseInt(document.getElementById('num-stairs').value) || 1;
        const tbody = document.getElementById('roof-body');
        tbody.innerHTML = '';
        for (let i = 0; i < n; i++) {
            const label = document.getElementById(`stair-label-${i}`)?.value || `Stair_${i + 1}`;
            const isPressurized = document.getElementById(`stair-pressurized-${i}`)?.checked !== false;
            let levelOpts = '<option value="">-- Level --</option>';
            modelData.levels.forEach(l => {
                levelOpts += `<option value="${l.index}">${l.name}</option>`;
            });

            // Try to auto-select zone matching stair label on highest level
            let autoZoneId = 0;
            let autoLevelNum = '';
            if (isPressurized && modelData.levels.length > 0) {
                const labelLower = label.toLowerCase();
                const highestLevel = modelData.levels[modelData.levels.length - 1];
                autoLevelNum = highestLevel.index;
                const match = allZones.find(z => z.name.toLowerCase() === labelLower && z.level_num === highestLevel.index);
                if (match) autoZoneId = match.id;
            }

            tbody.innerHTML += `<tr class="${isPressurized ? '' : 'roof-disabled'}">
                <td>${label}</td>
                <td>${isPressurized ? '&#9989;' : '&#10060;'}</td>
                <td>${makeZoneSelect(`roof-zone-${i}`, '')}</td>
                <td><select id="roof-level-${i}">${levelOpts}</select></td>
                <td><input type="number" id="roof-flow-${i}" value="0" min="0" step="100"></td>
                <td style="display:none">${makeAHSSelect(`roof-ahs-${i}`)}</td>
                <td><input type="number" id="roof-icon-${i}" value="129" min="0"></td>
                <td><input type="number" id="roof-col-${i}" value="1" min="0"></td>
                <td><input type="number" id="roof-row-${i}" value="1" min="0"></td>
                <td><button class="btn btn-sm" onclick="App.autoPopulateRoofSingle(${i})" ${isPressurized ? '' : 'disabled'}>Auto-Populate</button></td>
            </tr>`;

            // Apply auto-selections for roof
            if (autoZoneId) {
                setTimeout(() => {
                    const zs = document.getElementById(`roof-zone-${i}`);
                    if (zs) zs.value = autoZoneId;
                    const ls = document.getElementById(`roof-level-${i}`);
                    if (ls) ls.value = autoLevelNum;
                    // Auto-set AHS to #2 (Return) for roof exhaust
                    const as2 = document.getElementById(`roof-ahs-${i}`);
                    if (as2) as2.value = modelData.ahs.length > 1 ? modelData.ahs[1].id : 2;
                }, 0);
            }
        }
    }

    function applyBulkRoofExhaust() {
        const val = parseFloat(document.getElementById('roof-bulk-exhaust')?.value) || 0;
        const n = parseInt(document.getElementById('num-stairs').value) || 1;
        for (let i = 0; i < n; i++) {
            const isPressurized = document.getElementById(`stair-pressurized-${i}`)?.checked !== false;
            if (isPressurized) {
                const el = document.getElementById(`roof-flow-${i}`);
                if (el) el.value = val;
            }
        }
    }

    async function autoPopulateRoofSingle(roofIdx) {
        const label = document.getElementById(`stair-label-${roofIdx}`)?.value || `Stair_${roofIdx + 1}`;
        const nameLower = label.toLowerCase();

        // Find highest level with this zone name
        let bestMatch = null;
        let bestLevel = -1;
        for (let j = modelData.levels.length - 1; j >= 0; j--) {
            const lvl = modelData.levels[j];
            const match = allZones.find(z => z.name.toLowerCase() === nameLower && z.level_num === lvl.index);
            if (match) {
                bestMatch = match;
                bestLevel = lvl.index;
                break;
            }
        }

        if (!bestMatch) {
            const entered = prompt(`Enter zone name for roof of "${label}":`, label);
            if (!entered) return;
            const enteredLower = entered.toLowerCase();
            for (let j = modelData.levels.length - 1; j >= 0; j--) {
                const lvl = modelData.levels[j];
                const match = allZones.find(z => z.name.toLowerCase() === enteredLower && z.level_num === lvl.index);
                if (match) {
                    bestMatch = match;
                    bestLevel = lvl.index;
                    break;
                }
            }
        }

        if (bestMatch) {
            const zoneSel = document.getElementById(`roof-zone-${roofIdx}`);
            if (zoneSel) zoneSel.value = bestMatch.id;
            const levelSel = document.getElementById(`roof-level-${roofIdx}`);
            if (levelSel) levelSel.value = bestLevel;
            // AHS#2 Return
            const ahsSel = document.getElementById(`roof-ahs-${roofIdx}`);
            if (ahsSel) ahsSel.value = modelData.ahs.length > 1 ? modelData.ahs[1].id : 2;

            // Auto-place icon
            const prjPath = document.getElementById('prj-filepath')?.value?.trim();
            if (prjPath) {
                try {
                    const resp = await api('POST', '/api/tab3/zone-icons', { prj_path: prjPath });
                    const info = resp.zone_placements?.[String(bestMatch.id)];
                    if (info) {
                        const colEl = document.getElementById(`roof-col-${roofIdx}`);
                        const rowEl = document.getElementById(`roof-row-${roofIdx}`);
                        if (colEl) colEl.value = info.supply_col;
                        if (rowEl) rowEl.value = info.supply_row;
                    }
                } catch (e) {
                    console.warn('Could not fetch icon positions for roof:', e);
                }
            }
            appendLog(`Roof ${label}: zone=${bestMatch.name} (Z${bestMatch.id}) on level ${bestLevel}`);
        } else {
            alert(`No matching zone found for "${label}". Try entering the zone name manually.`);
        }
    }

    async function checkAllFiles() {
        if (!window._dryRunFiles || window._dryRunFiles.length === 0) {
            appendLog('No files to check.');
            return;
        }
        const config = collectConfig();
        appendLog('');
        appendLog(`Checking all ${window._dryRunFiles.length} PRJ files...`);
        let passed = 0, failed = 0;
        for (const f of window._dryRunFiles) {
            try {
                const resp = await api('POST', '/api/analysis/building-check', {
                    prj_path: f,
                    contam_exe: config.contam_exe,
                });
                const fname = f.split(/[/\\]/).pop();
                if (resp.passed) {
                    appendLog(`  ✅ ${fname}`);
                    passed++;
                } else {
                    appendLog(`  ❌ ${fname}: ${resp.message}`);
                    failed++;
                }
            } catch (e) {
                const fname = f.split(/[/\\]/).pop();
                appendLog(`  ⚠ ${fname}: ${e.message}`);
                failed++;
            }
        }
        appendLog(`Results: ${passed} passed, ${failed} failed out of ${window._dryRunFiles.length}`);
        document.getElementById('btn-check-all').style.display = 'none';
    }

    async function autoPopulateRoof() {
        const n = parseInt(document.getElementById('num-stairs').value) || 1;
        const prjPath = document.getElementById('prj-filepath')?.value?.trim();
        let placements = null;

        // Fetch icon positions if PRJ path is available
        if (prjPath) {
            try {
                const resp = await api('POST', '/api/tab3/zone-icons', { prj_path: prjPath });
                placements = resp.zone_placements || {};
            } catch (e) {
                console.warn('Could not fetch icon positions for roof:', e);
            }
        }

        for (let i = 0; i < n; i++) {
            const isPressurized = document.getElementById(`stair-pressurized-${i}`)?.checked !== false;
            if (!isPressurized) continue;

            const label = document.getElementById(`stair-label-${i}`)?.value || `Stair_${i + 1}`;
            const labelLower = label.toLowerCase();

            // Find the highest level that has this zone name
            let bestZone = null;
            let bestLevel = 0;
            for (let j = modelData.levels.length - 1; j >= 0; j--) {
                const lvl = modelData.levels[j];
                const match = allZones.find(z =>
                    z.name.toLowerCase() === labelLower && z.level_num === lvl.index);
                if (match) {
                    bestZone = match;
                    bestLevel = lvl.index;
                    break;
                }
            }

            if (bestZone) {
                const zoneSel = document.getElementById(`roof-zone-${i}`);
                if (zoneSel) zoneSel.value = bestZone.id;
                const levelSel = document.getElementById(`roof-level-${i}`);
                if (levelSel) levelSel.value = bestLevel;
                // Auto-set AHS#2 Return
                const ahsSel = document.getElementById(`roof-ahs-${i}`);
                if (ahsSel) ahsSel.value = modelData.ahs.length > 1 ? modelData.ahs[1].id : 2;

                // Auto-place icon near zone
                if (placements) {
                    const info = placements[String(bestZone.id)];
                    if (info) {
                        const colEl = document.getElementById(`roof-col-${i}`);
                        const rowEl = document.getElementById(`roof-row-${i}`);
                        if (colEl) colEl.value = info.supply_col;
                        if (rowEl) rowEl.value = info.supply_row;
                    }
                }
            }
        }
        alert('Roof auto-populate complete. Review zone and level selections.');
    }

    function updatePathSelection() {
        const n = parseInt(document.getElementById('num-stairs').value) || 1;
        const container = document.getElementById('path-selection-panels');
        container.innerHTML = '';

        for (let i = 0; i < n; i++) {
            const isPressurized = document.getElementById(`stair-pressurized-${i}`)?.checked !== false;
            if (!isPressurized) continue; // Only show pressurized stairs
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
                                <label>V2C (Vestibule-to-Corridor, optional)</label>
                                ${makeElementSelect(`path-v2c-${i}`, '-- None --')}
                            </div>
                            <div class="form-group">
                                <label>EXT (Stair-to-Exterior, optional)</label>
                                ${makeElementSelect(`path-ext-${i}`, '-- None --')}
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

        // Corridor path — only if corridor depressurization is enabled
        const corrPathGroup = document.getElementById('corridor-path-group');
        if (corrPathGroup) corrPathGroup.style.display = corridorDepressEnabled ? '' : 'none';
        const corrSel = document.getElementById('corridor-path-name');
        if (corrSel) {
            corrSel.innerHTML = `<option value="">-- Select --</option>`;
            modelData.elements.forEach(e => {
                corrSel.innerHTML += `<option value="${e.name}">${e.name}</option>`;
            });
        }

        // Auto-populate path selections from naming conventions
        autoPopulatePaths();

        // Floor path — only if floor depressurization is enabled
        const floorPathGroup = document.getElementById('floor-path-group');
        if (floorPathGroup) floorPathGroup.style.display = floorDepressEnabled ? '' : 'none';
        const floorSel = document.getElementById('floor-path-name');
        if (floorSel) {
            const prevVal = floorSel.value;
            floorSel.innerHTML = `<option value="">-- Select --</option>`;
            modelData.elements.forEach(e => {
                floorSel.innerHTML += `<option value="${e.name}">${e.name}</option>`;
            });
            // Restore or auto-select FLR.LK
            if (prevVal) {
                floorSel.value = prevVal;
            } else {
                const flrMatch = modelData.elements.find(e => 
                    e.name === 'FLR.LK' || e.name === 'FLR_LK' || e.name.toLowerCase() === 'flr.lk');
                if (flrMatch) floorSel.value = flrMatch.name;
            }
        }
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
                        // Corridor does NOT get exhaust — the floor zone handles
                        // depressurization. Corridor dP is measured via V2C paths
                        // but no exhaust fan is imposed on the corridor itself.
                        const flowEl = document.getElementById(`corr-${i}-flow-${zoneInfo.level_num}`);
                        if (flowEl) flowEl.value = 0;
                    } else {
                        corrZonesMissed++;
                    }
                }
                const ahsSel = document.getElementById(`corr-${i}-ahs-${zoneInfo.level_num}`);
                if (ahsSel && corrAhsId) ahsSel.value = corrAhsId;
            }
        }
        console.log(`[AutoConfig] Corridor zones: ${corrZonesSet} set, ${corrZonesMissed} missed (levels: ${[...levelsWithCorridor].sort((a,b)=>a-b).join(',')})`);

        // Populate floor zones — zones + AHS + exhaust flow on all levels
        if (sg.floor_zones && sg.floor_zones.length > 0) {
            document.getElementById('num-floors').value = sg.floor_zones.length;
            updateFloorTabs();

            let floorActive = 0;
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

                    // Floor zone is the exhaust/depressurization target on ALL
                    // levels. The corridor does NOT get its own exhaust —
                    // it depressurizes naturally via leakage to the floor zone.
                    const flowEl = document.getElementById(`floor-${i}-flow-${zoneInfo.level_num}`);
                    if (flowEl) {
                        flowEl.value = 600;
                        floorActive++;
                    }
                }
            }
            console.log(`[AutoConfig] Floor zones: ${sg.floor_zones.length} groups, ${floorActive} levels active (exhaust target)`);
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
        // Count fire floors (corridor AND floor zone levels with non-zero flow)
        const numCorr = parseInt(document.getElementById('num-corridors')?.value) || 0;
        const numFloors = parseInt(document.getElementById('num-floors')?.value) || 0;
        const fireFloorSet = new Set();
        modelData.levels.forEach(lvl => {
            // Check corridors
            for (let c = 0; c < numCorr; c++) {
                const flowEl = document.getElementById(`corr-${c}-flow-${lvl.index}`);
                if (flowEl && parseFloat(flowEl.value) > 0) { fireFloorSet.add(lvl.index); break; }
            }
            // Check floor zones
            for (let f = 0; f < numFloors; f++) {
                const flowEl = document.getElementById(`floor-${f}-flow-${lvl.index}`);
                if (flowEl && parseFloat(flowEl.value) > 0) { fireFloorSet.add(lvl.index); break; }
            }
        });
        const total = scenarios.length * Math.max(fireFloorSet.size, 1);
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
            const isPressurized = document.getElementById(`stair-pressurized-${i}`)?.checked !== false;
            const levels = [];
            modelData.levels.forEach(lvl => {
                const zoneId = parseInt(document.getElementById(`stair-${i}-zone-${lvl.index}`)?.value || 0);
                const flowRate = parseFloat(document.getElementById(`stair-${i}-flow-${lvl.index}`)?.value || 0);
                const ahsId = parseInt(document.getElementById(`stair-${i}-ahs-${lvl.index}`)?.value || 0) || 1;
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
                pressurized: isPressurized,
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
                const ahsId = parseInt(document.getElementById(`corr-${i}-ahs-${lvl.index}`)?.value || 0) || 2;
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
                const ahsId = parseInt(document.getElementById(`floor-${i}-ahs-${lvl.index}`)?.value || 0) || 2;
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
                path_name: document.getElementById('floor-path-name')?.value || '',
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
                stair_groups: stairCriteriaGroups,
                min_dp_floor: parseFloat(document.getElementById('min-dp-floor')?.value || 0.05),
                max_dp_floor: parseFloat(document.getElementById('max-dp-floor')?.value || 0.45),
                min_dp_corr: parseFloat(document.getElementById('min-dp-corr')?.value || 0.05),
                max_dp_corr: parseFloat(document.getElementById('max-dp-corr')?.value || 0.45),
                // Legacy fields for backward compatibility
                min_dp_inwc: stairCriteriaGroups[0]?.min_dp || 0.05,
                max_dp_inwc: parseFloat(document.getElementById('max-dp-floor')?.value || 0.45),
                max_dp_stair_inwc: stairCriteriaGroups[0]?.max_dp || 0.17,
            },
            corridor_depress_enabled: corridorDepressEnabled,
            floor_depress_enabled: floorDepressEnabled,
            selected_floors: runAllFloors ? null : selectedFloorIndices,
            floor_path_name: document.getElementById('floor-path-name')?.value || '',
        };
    }

    // ---------------------------------------------------------------------------
    // Run Analysis
    // ---------------------------------------------------------------------------
    async function dryRun() {
        // Pre-validate: warn if any configured flow rates have no zone assigned
        const config = collectConfig();
        let missingZones = [];
        for (const s of [...(config.stairs || []), ...(config.corridors || []), ...(config.floor_zones || [])]) {
            for (const l of (s.levels || [])) {
                if (l.flow_rate > 0 && l.zone_id === 0) {
                    missingZones.push(s.label + ' Level ' + l.level_num);
                }
            }
        }
        if (missingZones.length > 0) {
            const proceed = confirm(
                'WARNING: The following have flow rates set but no zone assigned:\n\n' +
                missingZones.slice(0, 10).join('\n') +
                (missingZones.length > 10 ? '\n...and ' + (missingZones.length - 10) + ' more' : '') +
                '\n\nLevels without zones will be SKIPPED.\n' +
                'Use "Auto-Populate by Zone Name" to assign zones.\n\nContinue anyway?'
            );
            if (!proceed) return;
        }
        appendLog('Starting dry run...');
        try {
            const resp = await api('POST', '/api/analysis/dryrun', config);
            appendLog(`Dry run complete. Generated ${resp.count} PRJ files.`);
            resp.generated_files.forEach(f => appendLog('  ' + f));

            // Show PRJ warnings (icon placement issues, etc.)
            if (resp.prj_warnings && resp.prj_warnings.length > 0) {
                appendLog('');
                appendLog('⚠ Placement Warnings:');
                resp.prj_warnings.forEach(w => appendLog('  ' + w));
            }

            // Show building check results
            if (resp.building_check) {
                const bc = resp.building_check;
                appendLog('');
                if (bc.passed === true) {
                    appendLog('✅ Building Check PASSED — CONTAM accepted the PRJ file.');
                    if (resp.count > 1) {
                        appendLog(`  (Checked first file only. Use "Check All Files" to verify all ${resp.count} files.)`);
                        // Store files for batch check
                        window._dryRunFiles = resp.generated_files;
                        const checkBtn = document.getElementById('btn-check-all');
                        if (checkBtn) checkBtn.style.display = '';
                    }
                } else if (bc.passed === false) {
                    appendLog('❌ Building Check FAILED:');
                    appendLog('  ' + bc.message);
                    if (bc.details) {
                        bc.details.split('\n').forEach(d => {
                            if (d.trim()) appendLog('  ' + d.trim());
                        });
                    }
                    appendLog('');
                    appendLog('Attempting auto-repair...');
                    try {
                        const repairResp = await api('POST', '/api/analysis/repair-prj', {
                            prj_files: resp.generated_files,
                            contam_exe: config.contam_exe,
                        });
                        if (repairResp.repaired) {
                            appendLog(`✅ Auto-repair applied. ${repairResp.repaired} file(s) fixed.`);
                            repairResp.details.forEach(d => appendLog('  ' + d));
                            appendLog('Re-running building check...');
                            const recheck = await api('POST', '/api/analysis/building-check', {
                                prj_path: resp.generated_files[0],
                                contam_exe: config.contam_exe,
                            });
                            if (recheck.passed) {
                                appendLog('✅ Building Check PASSED after repair.');
                            } else {
                                appendLog('❌ Building Check still FAILED after repair.');
                                appendLog('  ' + recheck.message);
                            }
                        } else {
                            appendLog('⚠ Auto-repair could not fix the issues.');
                            if (repairResp.details) repairResp.details.forEach(d => appendLog('  ' + d));
                        }
                    } catch (repErr) {
                        appendLog('⚠ Auto-repair unavailable: ' + repErr.message);
                    }
                } else {
                    appendLog('⚠ Building Check: ' + bc.message);
                }
            } else {
                appendLog('ℹ Building check skipped (CONTAM exe not configured or not found).');
            }
        } catch (e) {
            appendLog('Dry run failed: ' + e.message);
        }
    }

    async function startAnalysis() {
        const config = collectConfig();
        // Pre-validate: warn if any configured flow rates have no zone assigned
        let missingZones = [];
        for (const s of [...(config.stairs || []), ...(config.corridors || []), ...(config.floor_zones || [])]) {
            for (const l of (s.levels || [])) {
                if (l.flow_rate > 0 && l.zone_id === 0) {
                    missingZones.push((s.label || 'Group') + ' Level ' + l.level_num);
                }
            }
        }
        if (missingZones.length > 0) {
            const proceed = confirm(
                'WARNING: Some levels have flow rates but no zone assigned:\n\n' +
                missingZones.slice(0, 5).join('\n') +
                (missingZones.length > 5 ? '\n...and ' + (missingZones.length - 5) + ' more' : '') +
                '\n\nThese will be SKIPPED. Use "Auto-Populate by Zone Name" first.\nContinue?'
            );
            if (!proceed) return;
        }
        document.getElementById('btn-start').disabled = true;
        document.getElementById('btn-cancel').disabled = false;
        document.getElementById('progress-container').style.display = 'block';

        appendLog('Starting Analysis...');

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
                    const crit = _getCriteriaForColumn(col);
                    const absVal = Math.abs(numVal);
                    let cls = '';
                    if (absVal < crit.min) cls = 'dp-fail';
                    else if (absVal > crit.max) cls = 'dp-fail';
                    else if (absVal < crit.min * 1.1 || absVal > crit.max * 0.9) cls = 'dp-warn';
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

    function _isStairColumn(colName) {
        return colName.endsWith('_S2V') || colName.endsWith('_V2C') || colName.endsWith('_EXT')
            || colName.endsWith('_S2V2') || colName.endsWith('_V2C2');
    }

    function _isFloorColumn(colName) {
        return colName.includes('dP_above') || colName.includes('dP_below') || colName.includes('Floor');
    }

    function _getCriteriaForColumn(colName) {
        if (_isStairColumn(colName)) {
            const g = getStairCriteriaForColumn(colName);
            return { min: g.min_dp, max: g.max_dp };
        }
        if (_isFloorColumn(colName)) {
            return {
                min: parseFloat(document.getElementById('min-dp-floor')?.value) || 0.05,
                max: parseFloat(document.getElementById('max-dp-floor')?.value) || 0.45,
            };
        }
        // Corridor / default
        return {
            min: parseFloat(document.getElementById('min-dp-corr')?.value) || 0.05,
            max: parseFloat(document.getElementById('max-dp-corr')?.value) || 0.45,
        };
    }

    function renderResultsTable(columns, data, subtitle) {
        const thead = document.getElementById('results-head');
        const tbody = document.getElementById('results-body');

        let headerHtml = '<tr>' + columns.map(c => `<th>${c}</th>`).join('') + '</tr>';
        if (subtitle) {
            headerHtml = `<tr><th colspan="${columns.length}" style="text-align:center;background:rgba(46,134,222,0.08);font-size:0.85rem;">${subtitle}</th></tr>` + headerHtml;
        }
        thead.innerHTML = headerHtml;

        tbody.innerHTML = data.map(row =>
            '<tr>' + row.map((val, ci) => {
                if (ci === 0) return `<td>${val}</td>`;
                const numVal = parseFloat(val);
                if (isNaN(numVal) || numVal === 0) return `<td>${val ?? ''}</td>`;
                const crit = _getCriteriaForColumn(columns[ci]);
                let cls = '';
                const absVal = Math.abs(numVal);
                if (absVal < crit.min) cls = 'dp-fail';
                else if (absVal > crit.max) cls = 'dp-fail';
                else if (absVal < crit.min * 1.1 || absVal > crit.max * 0.9) cls = 'dp-warn';
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
                list.innerHTML = '<div style="padding:1rem;color:var(--text-secondary);">Empty folder</div>';
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
        if (_pendingBrowserCallback) {
            // A callback is waiting (e.g. Excel import) — invoke it instead of filling an input
            const cb = _pendingBrowserCallback;
            _pendingBrowserCallback = null;
            closeBrowser();
            cb(path);
            return;
        }
        if (browserTargetInput && path) {
            document.getElementById(browserTargetInput).value = path;
        }
        closeBrowser();
    }

    function closeBrowser() {
        document.getElementById('file-browser-modal').style.display = 'none';
        browserSelectedPath = '';
        browserFileFilter = '';
        _pendingBrowserCallback = null;
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

    function checkEstimationTransfer() {
        const raw = localStorage.getItem('estimation_transfer');
        if (!raw) return;

        try {
            const transfer = JSON.parse(raw);
            // Build an info banner at the top of the main content
            const main = document.querySelector('.content');
            if (!main) return;

            let html = '<div id="estimation-transfer-banner" style="background:#e8f8ef;border:2px solid #27ae60;border-radius:6px;padding:12px 16px;margin-bottom:16px;">';
            html += '<strong style="color:#1a6b3c;">Estimation Results Available</strong>';
            html += '<p style="margin:6px 0 8px;font-size:9pt;color:#333;">Use these values to configure stair pressurization SCFM in Tab 3:</p>';
            html += '<table style="font-size:9pt;border-collapse:collapse;margin-bottom:8px;">';
            for (const s of transfer.stairs) {
                html += `<tr><td style="padding:2px 12px 2px 0;font-weight:600;">${s.label}</td><td style="padding:2px 8px;">${s.supply_design_cfm} CFM design supply</td><td style="padding:2px 8px;color:#777;">(${s.supply_closed_cfm} closed / ${s.supply_open_cfm} open)</td></tr>`;
            }
            html += `<tr><td style="padding:2px 12px 2px 0;font-weight:600;">Exhaust</td><td style="padding:2px 8px;">${transfer.exhaust_cfm} CFM</td><td style="padding:2px 8px;color:#777;">(fire floor depressurization)</td></tr>`;
            html += '</table>';
            html += '<button class="btn btn-sm" onclick="document.getElementById(\'estimation-transfer-banner\').remove(); localStorage.removeItem(\'estimation_transfer\');">Dismiss</button>';
            html += '</div>';

            main.insertAdjacentHTML('afterbegin', html);
        } catch (e) {
            // Invalid data — clear it
            localStorage.removeItem('estimation_transfer');
        }
    }

    function init() {
        initTabs();
        initScenarioSelectAll();
        loadRecentProjects();
        loadResultsScenarios();
        initStairCriteriaGroups();
        checkEstimationTransfer();
    }

    document.addEventListener('DOMContentLoaded', init);

    // Public API
// ---------------------------------------------------------------------------
    // Toggle Functions for Tab 3
    // ---------------------------------------------------------------------------
    function toggleCorridorDepress() {
        const cb = document.getElementById('corridor-depress-enabled');
        const content = document.getElementById('corridor-depress-content');
        corridorDepressEnabled = cb ? cb.checked : true;
        if (content) {
            content.classList.toggle('stair-disabled-overlay', !corridorDepressEnabled);
        }
        updatePathSelection();
    }

    function toggleFloorDepress() {
        const cb = document.getElementById('floor-depress-enabled');
        const content = document.getElementById('floor-depress-content');
        floorDepressEnabled = cb ? cb.checked : false;
        if (content) {
            content.classList.toggle('stair-disabled-overlay', !floorDepressEnabled);
        }
        updatePathSelection();
    }

    function toggleRunAllFloors() {
        const cb = document.getElementById('run-all-floors');
        runAllFloors = cb ? cb.checked : true;
        const content = document.getElementById('floor-selection-content');
        if (content) {
            content.classList.toggle('stair-disabled-overlay', runAllFloors);
        }
        if (runAllFloors) selectedFloorIndices = null;
    }

    function parseFloorRange() {
        const input = document.getElementById('floor-range-input')?.value?.trim();
        if (!input || modelData.levels.length === 0) return;
        const indices = new Set();
        const parts = input.split(',');
        for (const part of parts) {
            const trimmed = part.trim();
            const rangeMatch = trimmed.match(/^(\d+)\s*-\s*(\d+)$/);
            if (rangeMatch) {
                const start = parseInt(rangeMatch[1]);
                const end = parseInt(rangeMatch[2]);
                for (let i = start; i <= end; i++) indices.add(i);
            } else {
                const num = parseInt(trimmed);
                if (!isNaN(num)) indices.add(num);
            }
        }
        // Map parsed numbers to actual level indices
        selectedFloorIndices = [];
        const badgesEl = document.getElementById('floor-selection-badges');
        let html = '';
        modelData.levels.forEach((lvl, idx) => {
            const floorNum = idx + 1; // 1-based floor number
            const selected = indices.has(floorNum) || indices.has(lvl.index);
            if (selected) selectedFloorIndices.push(lvl.index);
            html += `<span class="floor-badge ${selected ? 'selected' : 'unselected'}">${lvl.name}</span>`;
        });
        if (badgesEl) badgesEl.innerHTML = html;
    }

    // ---------------------------------------------------------------------------
    // Stair Criteria Groups (Tab 6)
    // ---------------------------------------------------------------------------
    function initStairCriteriaGroups() {
        if (stairCriteriaGroups.length === 0) {
            stairCriteriaGroups.push({ id: 1, stairs: [], min_dp: 0.05, max_dp: 0.17 });
        }
        renderStairCriteriaGroups();
    }

    function addStairCriteriaGroup() {
        const nextId = stairCriteriaGroups.length > 0 ? Math.max(...stairCriteriaGroups.map(g => g.id)) + 1 : 1;
        stairCriteriaGroups.push({ id: nextId, stairs: [], min_dp: 0.05, max_dp: 0.17 });
        renderStairCriteriaGroups();
    }

    function removeStairCriteriaGroup(id) {
        stairCriteriaGroups = stairCriteriaGroups.filter(g => g.id !== id);
        renderStairCriteriaGroups();
    }

    function renderStairCriteriaGroups() {
        const container = document.getElementById('stair-criteria-list');
        if (!container) return;
        const numStairs = parseInt(document.getElementById('num-stairs')?.value) || 1;
        const stairLabels = [];
        for (let i = 0; i < numStairs; i++) {
            const isPressurized = document.getElementById(`stair-pressurized-${i}`)?.checked !== false;
            if (isPressurized) {
                stairLabels.push(document.getElementById(`stair-label-${i}`)?.value || `Stair_${i + 1}`);
            }
        }

        container.innerHTML = stairCriteriaGroups.map(g => {
            const stairChecks = stairLabels.map(label => {
                const checked = g.stairs.includes(label) ? 'checked' : '';
                return `<label><input type="checkbox" data-group="${g.id}" data-stair="${label}" ${checked} onchange="App.updateStairCriteriaGroup(${g.id})"> ${label}</label>`;
            }).join('');

            return `<div class="criteria-group">
                <div class="criteria-group-header">
                    <strong>Group ${g.id}</strong>
                    ${stairCriteriaGroups.length > 1 ? `<button class="btn btn-sm btn-danger" onclick="App.removeStairCriteriaGroup(${g.id})" style="margin-left:auto;padding:2px 8px;font-size:0.7rem;">Remove</button>` : ''}
                </div>
                <div class="criteria-stair-checks">${stairChecks || '<em style="font-size:0.8rem;color:var(--text-secondary);">No pressurized stairs configured</em>'}</div>
                <div class="form-row">
                    <div class="form-group">
                        <label>Min dP (in. w.c.)</label>
                        <input type="number" id="scg-min-${g.id}" value="${g.min_dp}" step="0.01" onchange="App.updateStairCriteriaGroup(${g.id})">
                    </div>
                    <div class="form-group">
                        <label>Max dP (in. w.c.)</label>
                        <input type="number" id="scg-max-${g.id}" value="${g.max_dp}" step="0.01" onchange="App.updateStairCriteriaGroup(${g.id})">
                    </div>
                </div>
            </div>`;
        }).join('');
    }

    function updateStairCriteriaGroup(id) {
        const group = stairCriteriaGroups.find(g => g.id === id);
        if (!group) return;
        // Read stairs checkboxes
        const checks = document.querySelectorAll(`input[data-group="${id}"]`);
        group.stairs = [];
        checks.forEach(cb => { if (cb.checked) group.stairs.push(cb.dataset.stair); });
        group.min_dp = parseFloat(document.getElementById(`scg-min-${id}`)?.value) || 0.05;
        group.max_dp = parseFloat(document.getElementById(`scg-max-${id}`)?.value) || 0.17;
    }

    function getStairCriteriaForColumn(colName) {
        // Find which criteria group applies to a column name like "Stair_1_S2V"
        for (const g of stairCriteriaGroups) {
            for (const stairLabel of g.stairs) {
                if (colName.startsWith(stairLabel + '_') || colName.startsWith(stairLabel.replace(/ /g,'_') + '_')) {
                    return g;
                }
            }
        }
        // Default: use first group
        return stairCriteriaGroups[0] || { min_dp: 0.05, max_dp: 0.17 };
    }

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
        autoPopulatePaths,
        autoPopulateFloor,
        applySuggestions,
        togglePanel,
        toggleStairPressurized,
        toggleCorridorDepress,
        toggleFloorDepress,
        toggleRunAllFloors,
        parseFloorRange,
        applyBulkRoofExhaust,
        autoPopulateRoof,
        autoPopulateRoofSingle,
        checkAllFiles,
        addStairCriteriaGroup,
        removeStairCriteriaGroup,
        updateStairCriteriaGroup,
        applyBulkSCFM,
        applyAlternatingSCFM,
        importExcelSCFM,
        generateExcelTemplates,
        saveTab3Config,
        loadTab3Config,
        updatePrjFile,
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
        browseFolder,
        navigateBrowser,
        browserItemClick,
        browserItemDblClick,
        browserUp,
        selectBrowserPath,
        closeBrowser,
    };
})();