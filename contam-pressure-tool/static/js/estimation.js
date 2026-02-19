/**
 * Stair Pressurization Estimation Tool — Frontend Logic
 * SGH (Simpson Gumpertz & Heger)
 *
 * Analytical estimation per ASHRAE HSCE / NFPA 92 / IBC 909.
 */

const Est = (() => {
    let stairwells = [];
    let lastResult = null;

    // -----------------------------------------------------------------------
    // Initialization
    // -----------------------------------------------------------------------
    function init() {
        initTabs();
        addStairwell();  // Start with one stairwell
        loadDefaults();
    }

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
    }

    function nextTab(tabId) {
        document.querySelectorAll('.nav-tab').forEach(t => {
            t.classList.toggle('active', t.dataset.tab === tabId);
        });
        document.querySelectorAll('.tab-panel').forEach(p => {
            p.classList.toggle('active', p.id === tabId);
        });
    }

    // -----------------------------------------------------------------------
    // API
    // -----------------------------------------------------------------------
    async function api(method, endpoint, body = null) {
        const opts = { method, headers: { 'Content-Type': 'application/json' } };
        if (body) opts.body = JSON.stringify(body);
        const resp = await fetch(endpoint, opts);
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(err.detail || resp.statusText);
        }
        return resp;
    }

    async function loadDefaults() {
        try {
            const resp = await api('GET', '/api/estimation/defaults');
            // Could pre-populate from server defaults if needed
        } catch (e) {
            // Defaults are already in the HTML
        }
    }

    // -----------------------------------------------------------------------
    // Stairwell Management
    // -----------------------------------------------------------------------
    function addStairwell() {
        const idx = stairwells.length;
        const label = idx === 0 ? 'Stair A' : `Stair ${String.fromCharCode(65 + idx)}`;
        stairwells.push({ label });
        renderStairwells();
    }

    function removeStairwell(idx) {
        if (stairwells.length <= 1) return;
        stairwells.splice(idx, 1);
        renderStairwells();
    }

    function renderStairwells() {
        const container = document.getElementById('stairwell-list');
        if (!container) return;
        const nAbove = parseInt(document.getElementById('est-n-floors-above')?.value) || 10;
        const nBelow = parseInt(document.getElementById('est-n-floors-below')?.value) || 0;
        const totalFloors = nAbove + nBelow;

        container.innerHTML = stairwells.map((s, i) => `
            <div class="stair-card">
                <div class="stair-card-header">
                    <strong>${esc(s.label)}</strong>
                    ${stairwells.length > 1 ? `<button class="btn btn-sm btn-danger" onclick="Est.removeStairwell(${i})">Remove</button>` : ''}
                </div>
                <div class="form-grid">
                    <div class="form-group">
                        <label>Label</label>
                        <input type="text" id="stair-${i}-label" value="${esc(s.label)}"
                               onchange="Est.updateStairLabel(${i}, this.value)">
                    </div>
                    <div class="form-group">
                        <label>Cross-section area (m&sup2;)</label>
                        <input type="number" id="stair-${i}-area" value="10" step="0.5" min="3" max="40">
                    </div>
                    <div class="form-group">
                        <label>Door width (m)</label>
                        <input type="number" id="stair-${i}-door-w" value="1.1" step="0.05" min="0.8" max="1.5">
                    </div>
                    <div class="form-group">
                        <label>Door height (m)</label>
                        <input type="number" id="stair-${i}-door-h" value="2.1" step="0.05" min="1.8" max="2.5">
                    </div>
                    <div class="form-group">
                        <label>Door gap (mm)</label>
                        <input type="number" id="stair-${i}-gap" value="3" step="0.5" min="1" max="10">
                    </div>
                    <div class="form-group">
                        <label>Doors per floor</label>
                        <input type="number" id="stair-${i}-doors" value="1" min="1" max="2">
                    </div>
                    <div class="form-group">
                        <label>Serves bottom floor</label>
                        <input type="number" id="stair-${i}-bottom" value="1" min="1" max="${totalFloors}">
                    </div>
                    <div class="form-group">
                        <label>Serves top floor</label>
                        <input type="number" id="stair-${i}-top" value="${totalFloors}" min="1" max="${totalFloors}">
                    </div>
                    <div class="form-group">
                        <label>Exterior walls (n)</label>
                        <input type="number" id="stair-${i}-ext-walls" value="1" min="0" max="4">
                    </div>
                    <div class="form-group">
                        <label>Ext wall length (m)</label>
                        <input type="number" id="stair-${i}-ext-len" value="4" step="0.5" min="0" max="20">
                    </div>
                </div>
            </div>
        `).join('');
    }

    function updateStairLabel(idx, val) {
        stairwells[idx].label = val;
    }

    // -----------------------------------------------------------------------
    // Collect Inputs
    // -----------------------------------------------------------------------
    function val(id) {
        const el = document.getElementById(id);
        if (!el) return '';
        return el.value;
    }
    function numVal(id) {
        return parseFloat(val(id)) || 0;
    }
    function intVal(id) {
        return parseInt(val(id)) || 0;
    }

    function collectInputs() {
        const totalFloors = intVal('est-n-floors-above') + intVal('est-n-floors-below');
        const stairData = stairwells.map((s, i) => ({
            label: val(`stair-${i}-label`) || s.label,
            cross_section_area: numVal(`stair-${i}-area`),
            cross_section_perimeter: Math.sqrt(numVal(`stair-${i}-area`)) * 4, // approx
            door_width: numVal(`stair-${i}-door-w`),
            door_height: numVal(`stair-${i}-door-h`),
            door_gap_mm: numVal(`stair-${i}-gap`),
            doors_per_floor: intVal(`stair-${i}-doors`),
            serves_bottom: intVal(`stair-${i}-bottom`),
            serves_top: intVal(`stair-${i}-top`) || totalFloors,
            n_exterior_walls: intVal(`stair-${i}-ext-walls`),
            exterior_wall_length: numVal(`stair-${i}-ext-len`),
        }));

        return {
            building: {
                n_floors_above: intVal('est-n-floors-above'),
                n_floors_below: intVal('est-n-floors-below'),
                floor_height: numVal('est-floor-height'),
                building_perimeter: numVal('est-bldg-perimeter'),
                floor_area: numVal('est-floor-area'),
                wall_construction: val('est-wall-construction'),
            },
            stairwells: stairData,
            elevators: {
                n_shafts: intVal('est-elev-n'),
                shaft_area: numVal('est-elev-area'),
                door_type: val('est-elev-door-type'),
                vent_area: numVal('est-elev-vent'),
            },
            conditions: {
                T_outdoor_winter: numVal('est-t-winter'),
                T_outdoor_summer: numVal('est-t-summer'),
                T_indoor: numVal('est-t-indoor'),
                T_fire: numVal('est-t-fire'),
                wind_speed: numVal('est-wind-speed'),
                wind_direction: numVal('est-wind-dir'),
                P_atm: numVal('est-p-atm'),
                n_open_doors: intVal('est-n-open-doors'),
                is_sprinklered: val('est-sprinklered') === 'yes',
                design_fire_hrr: numVal('est-fire-hrr'),
            },
            leakage: {
                exterior_wall: val('est-leak-ext-wall'),
                interior_wall: val('est-leak-int-wall'),
                floor_ceiling: val('est-leak-floor'),
                stair_door: val('est-leak-stair-door'),
                elevator_door: val('est-leak-elev-door'),
            },
            criteria: {
                min_dp_closed: numVal('est-min-dp'),
                max_dp_closed: numVal('est-max-dp'),
                min_door_velocity: numVal('est-min-velocity'),
                max_door_force: numVal('est-max-force'),
                floor_exhaust_dp: numVal('est-exhaust-dp'),
                door_closer_force: numVal('est-closer-force'),
            },
            stairwell_temp_assumption: val('est-stair-temp'),
            fire_floor: intVal('est-fire-floor'),
        };
    }

    // -----------------------------------------------------------------------
    // Run Estimation
    // -----------------------------------------------------------------------
    async function runEstimation() {
        nextTab('est-run');
        showStatus('est-status', 'Running estimation...', 'info');
        hideResults();

        const body = collectInputs();

        try {
            const resp = await api('POST', '/api/estimation/run', body);
            const data = await resp.json();
            lastResult = data;

            if (data.status !== 'ok') {
                showStatus('est-status', 'Calculation failed: ' + (data.detail || 'Unknown error'), 'error');
                return;
            }

            const badge = data.all_constraints_met
                ? '<span class="badge badge-pass">ALL CONSTRAINTS MET</span>'
                : '<span class="badge badge-fail">CONSTRAINTS VIOLATED</span>';
            showStatus('est-status', badge, 'raw');

            // Show warnings
            if (data.warnings && data.warnings.length > 0) {
                const warnDiv = document.getElementById('est-warnings');
                warnDiv.style.display = 'block';
                warnDiv.innerHTML = '<div class="warn-box">' +
                    data.warnings.map(w => `<p>${esc(w)}</p>`).join('') + '</div>';
            }

            renderSystemSummary(data);
            renderFloorTables(data);
            renderExhaust(data);
            renderSensitivity(data);

        } catch (e) {
            showStatus('est-status', 'Error: ' + e.message, 'error');
        }
    }

    // -----------------------------------------------------------------------
    // Render Results
    // -----------------------------------------------------------------------
    function hideResults() {
        document.getElementById('est-warnings').style.display = 'none';
        document.getElementById('est-system-summary').style.display = 'none';
        document.getElementById('est-floor-tables').style.display = 'none';
        document.getElementById('est-exhaust-section').style.display = 'none';
        document.getElementById('est-sensitivity-section').style.display = 'none';
    }

    function renderSystemSummary(data) {
        const div = document.getElementById('est-system-summary');
        div.style.display = 'block';
        let html = '<table class="est-table"><thead><tr><th>Parameter</th><th>Value</th></tr></thead><tbody>';

        for (const sr of data.stair_results) {
            html += `<tr><td><strong>${esc(sr.label)} Supply (all closed)</strong></td>
                     <td>${sr.q_supply_closed.toFixed(4)} m&sup3;/s (${sr.q_supply_closed_cfm} CFM)</td></tr>`;
            html += `<tr><td><strong>${esc(sr.label)} Supply (doors open)</strong></td>
                     <td>${sr.q_supply_open.toFixed(4)} m&sup3;/s (${sr.q_supply_open_cfm} CFM)</td></tr>`;
            html += `<tr class="highlight-row"><td><strong>${esc(sr.label)} DESIGN Supply</strong></td>
                     <td><strong>${sr.q_supply_design.toFixed(4)} m&sup3;/s (${sr.q_supply_design_cfm} CFM)</strong></td></tr>`;
            html += `<tr><td>${esc(sr.label)} Critical Floor (min dP)</td><td>${esc(sr.critical_floor_min_dp)}</td></tr>`;
            html += `<tr><td>${esc(sr.label)} Critical Floor (max force)</td><td>${esc(sr.critical_floor_max_force)}</td></tr>`;
        }

        const er = data.exhaust_result;
        html += '<tr><td colspan="2" style="border-top:2px solid #2e3a4e;"></td></tr>';
        html += `<tr class="highlight-row"><td><strong>Fire Floor Exhaust (at fire temp)</strong></td>
                 <td><strong>${er.q_exhaust_total.toFixed(4)} m&sup3;/s (${er.q_exhaust_total_cfm} CFM)</strong></td></tr>`;
        html += `<tr class="highlight-row"><td><strong>Fire Floor Exhaust (std 20&deg;C)</strong></td>
                 <td><strong>${er.q_exhaust_std.toFixed(4)} m&sup3;/s (${er.q_exhaust_std_cfm} CFM)</strong></td></tr>`;
        html += `<tr><td>NPP Height</td><td>${data.npp_height} m above grade</td></tr>`;

        html += '</tbody></table>';
        document.getElementById('est-summary-content').innerHTML = html;
    }

    function renderFloorTables(data) {
        const div = document.getElementById('est-floor-tables');
        div.style.display = 'block';
        let html = '';

        for (const sr of data.stair_results) {
            html += `<h4>${esc(sr.label)}</h4>`;
            html += `<table class="est-table results-table">
                <thead><tr>
                    <th>Floor</th><th>Height (m)</th>
                    <th>&Delta;P_stack (Pa)</th><th>&Delta;P_wind (Pa)</th>
                    <th>&Delta;P_net (Pa)</th>
                    <th>Q_leak (m&sup3;/s)</th><th>Q_leak (CFM)</th>
                    <th>Q_open (m&sup3;/s)</th><th>Q_open (CFM)</th>
                    <th>F_total (N)</th><th>Status</th>
                </tr></thead><tbody>`;

            for (const fr of sr.floor_results) {
                const cls = fr.status === 'PASS' ? 'pass' : 'fail';
                const title = fr.failure_reasons.length ? ` title="${esc(fr.failure_reasons.join('; '))}"` : '';
                html += `<tr>
                    <td class="level-cell">${esc(fr.floor_label)}</td>
                    <td>${fr.height.toFixed(1)}</td>
                    <td>${fr.dp_stack.toFixed(2)}</td>
                    <td>${fr.dp_wind.toFixed(2)}</td>
                    <td class="${cls}">${fr.dp_net.toFixed(2)}</td>
                    <td>${fr.q_leak_closed.toFixed(4)}</td>
                    <td>${fr.q_leak_closed_cfm.toFixed(0)}</td>
                    <td>${fr.q_flow_open > 0 ? fr.q_flow_open.toFixed(4) : '-'}</td>
                    <td>${fr.q_flow_open_cfm > 0 ? fr.q_flow_open_cfm.toFixed(0) : '-'}</td>
                    <td${fr.f_total > numVal('est-max-force') ? ' class="fail"' : ''}>${fr.f_total.toFixed(1)}</td>
                    <td class="${cls}"${title}>${fr.status}</td>
                </tr>`;
            }
            html += '</tbody></table>';
        }

        document.getElementById('est-floor-content').innerHTML = html;
    }

    function renderExhaust(data) {
        const div = document.getElementById('est-exhaust-section');
        div.style.display = 'block';
        const er = data.exhaust_result;

        let html = `<table class="est-table">
            <thead><tr><th>Component</th><th>Flow (m&sup3;/s)</th><th>Flow (CFM)</th><th>% of Total</th></tr></thead>
            <tbody>`;
        const total = er.q_exhaust_total || 1;
        const items = [
            ['Stair leakage (EQ-19)', er.q_leak_stairs, er.q_leak_stairs_cfm],
            ['Elevator leakage (EQ-20)', er.q_leak_elevators, er.q_leak_elevators_cfm],
            ['Exterior wall leakage (EQ-21)', er.q_leak_exterior, er.q_leak_exterior_cfm],
            ['Vertical leakage (EQ-22)', er.q_leak_vertical, er.q_leak_vertical_cfm],
            ['Thermal expansion (EQ-23)', er.q_expansion, er.q_expansion_cfm],
        ];
        for (const [name, val, cfm] of items) {
            const pct = (val / total * 100).toFixed(1);
            html += `<tr><td>${name}</td><td>${val.toFixed(4)}</td><td>${cfm}</td><td>${pct}%</td></tr>`;
        }
        html += `<tr class="highlight-row"><td><strong>TOTAL (EQ-25)</strong></td>
                 <td><strong>${er.q_exhaust_total.toFixed(4)}</strong></td>
                 <td><strong>${er.q_exhaust_total_cfm}</strong></td><td>100%</td></tr>`;
        html += '</tbody></table>';

        document.getElementById('est-exhaust-content').innerHTML = html;
    }

    function renderSensitivity(data) {
        if (!data.sensitivity_cases || data.sensitivity_cases.length === 0) return;
        const div = document.getElementById('est-sensitivity-section');
        div.style.display = 'block';

        let html = `<table class="est-table results-table">
            <thead><tr>
                <th>Parameter</th><th>Value</th>
                <th>Supply (CFM)</th><th>Supply Change</th>
                <th>Exhaust (CFM)</th><th>Exhaust Change</th>
                <th>Critical Floor</th><th>Violated?</th>
            </tr></thead><tbody>`;

        for (const sc of data.sensitivity_cases) {
            const vcls = sc.constraints_violated ? 'fail' : 'pass';
            html += `<tr>
                <td>${esc(sc.parameter)}</td>
                <td>${esc(sc.value_description)}</td>
                <td>${sc.stair_supply_total_cfm}</td>
                <td>${sc.stair_supply_change_pct > 0 ? '+' : ''}${sc.stair_supply_change_pct.toFixed(1)}%</td>
                <td>${sc.exhaust_total_cfm}</td>
                <td>${sc.exhaust_change_pct > 0 ? '+' : ''}${sc.exhaust_change_pct.toFixed(1)}%</td>
                <td>${esc(sc.critical_floor)}</td>
                <td class="${vcls}">${sc.constraints_violated ? 'YES' : 'No'}</td>
            </tr>`;
        }
        html += '</tbody></table>';

        document.getElementById('est-sensitivity-content').innerHTML = html;
    }

    // -----------------------------------------------------------------------
    // Report Generation
    // -----------------------------------------------------------------------
    async function generateReport() {
        const body = collectInputs();
        try {
            const resp = await fetch('/api/estimation/report', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            if (!resp.ok) throw new Error('Report generation failed');
            const html = await resp.text();
            const win = window.open('', '_blank');
            win.document.write(html);
            win.document.close();
        } catch (e) {
            alert('Error generating report: ' + e.message);
        }
    }

    // -----------------------------------------------------------------------
    // Helpers
    // -----------------------------------------------------------------------
    function esc(text) {
        const d = document.createElement('div');
        d.textContent = text || '';
        return d.innerHTML;
    }

    function showStatus(id, msg, type) {
        const el = document.getElementById(id);
        if (!el) return;
        if (type === 'raw') {
            el.innerHTML = msg;
            el.className = 'status-msg';
        } else {
            el.innerHTML = msg;
            el.className = 'status-msg ' + (type || '');
        }
    }

    // -----------------------------------------------------------------------
    // Bootstrap
    // -----------------------------------------------------------------------
    document.addEventListener('DOMContentLoaded', init);

    return {
        nextTab,
        addStairwell,
        removeStairwell,
        updateStairLabel,
        runEstimation,
        generateReport,
    };
})();
