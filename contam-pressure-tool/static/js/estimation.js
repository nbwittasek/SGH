/**
 * Stair Pressurization Estimation Tool — Frontend Logic
 * SGH (Simpson Gumpertz & Heger)
 *
 * Analytical estimation per ASHRAE HSCE / NFPA 92 / IBC 909.
 */

const Est = (() => {
    let stairwells = [];
    let lastResult = null;
    let lastCriteria = {};  // Cache criteria at run time for result rendering

    // Default stairwell field values
    const STAIR_DEFAULTS = {
        area: 10, doorW: 1.1, doorH: 2.1, gap: 3, doors: 1,
        bottom: 1, top: 0, extWalls: 1, extLen: 4,
    };

    // -----------------------------------------------------------------------
    // Initialization
    // -----------------------------------------------------------------------
    function init() {
        initTabs();
        initDropZone();
        addStairwell();  // Start with one stairwell
        // Auto-load from localStorage if estimation data was forwarded from CONTAM tool
        tryLoadFromStorage();
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
    async function apiJson(method, endpoint, body = null) {
        const opts = { method, headers: { 'Content-Type': 'application/json' } };
        if (body) opts.body = JSON.stringify(body);
        const resp = await fetch(endpoint, opts);
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(err.detail || resp.statusText);
        }
        return resp.json();
    }

    // -----------------------------------------------------------------------
    // Stairwell Management
    // -----------------------------------------------------------------------
    function captureStairwellValues() {
        // Read current DOM values back into the stairwells array before re-render
        stairwells.forEach((s, i) => {
            const el = document.getElementById(`stair-${i}-label`);
            if (!el) return;  // Not rendered yet
            s.label = el.value || s.label;
            s.area = parseFloat(document.getElementById(`stair-${i}-area`)?.value) || s.area || STAIR_DEFAULTS.area;
            s.doorW = parseFloat(document.getElementById(`stair-${i}-door-w`)?.value) || s.doorW || STAIR_DEFAULTS.doorW;
            s.doorH = parseFloat(document.getElementById(`stair-${i}-door-h`)?.value) || s.doorH || STAIR_DEFAULTS.doorH;
            s.gap = parseFloat(document.getElementById(`stair-${i}-gap`)?.value) || s.gap || STAIR_DEFAULTS.gap;
            s.doors = parseInt(document.getElementById(`stair-${i}-doors`)?.value) || s.doors || STAIR_DEFAULTS.doors;
            s.bottom = parseInt(document.getElementById(`stair-${i}-bottom`)?.value) || s.bottom || STAIR_DEFAULTS.bottom;
            s.top = parseInt(document.getElementById(`stair-${i}-top`)?.value) || s.top || STAIR_DEFAULTS.top;
            s.extWalls = parseInt(document.getElementById(`stair-${i}-ext-walls`)?.value) ?? s.extWalls ?? STAIR_DEFAULTS.extWalls;
            s.extLen = parseFloat(document.getElementById(`stair-${i}-ext-len`)?.value) || s.extLen || STAIR_DEFAULTS.extLen;
        });
    }

    function addStairwell() {
        captureStairwellValues();
        const idx = stairwells.length;
        const label = idx === 0 ? 'Stair A' : `Stair ${String.fromCharCode(65 + idx)}`;
        const nAbove = parseInt(document.getElementById('est-n-floors-above')?.value) || 10;
        const nBelow = parseInt(document.getElementById('est-n-floors-below')?.value) || 0;
        stairwells.push({
            label,
            area: STAIR_DEFAULTS.area, doorW: STAIR_DEFAULTS.doorW, doorH: STAIR_DEFAULTS.doorH,
            gap: STAIR_DEFAULTS.gap, doors: STAIR_DEFAULTS.doors,
            bottom: STAIR_DEFAULTS.bottom, top: nAbove + nBelow,
            extWalls: STAIR_DEFAULTS.extWalls, extLen: STAIR_DEFAULTS.extLen,
        });
        renderStairwells();
    }

    function removeStairwell(idx) {
        if (stairwells.length <= 1) return;
        captureStairwellValues();
        stairwells.splice(idx, 1);
        renderStairwells();
    }

    function renderStairwells() {
        const container = document.getElementById('stairwell-list');
        if (!container) return;
        const nAbove = parseInt(document.getElementById('est-n-floors-above')?.value) || 10;
        const nBelow = parseInt(document.getElementById('est-n-floors-below')?.value) || 0;
        const totalFloors = nAbove + nBelow;

        container.innerHTML = stairwells.map((s, i) => {
            const top = s.top || totalFloors;
            return `
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
                        <input type="number" id="stair-${i}-area" value="${s.area}" step="0.5" min="3" max="200">
                    </div>
                    <div class="form-group">
                        <label>Door width (m)</label>
                        <input type="number" id="stair-${i}-door-w" value="${s.doorW}" step="0.05" min="0.8" max="1.5">
                    </div>
                    <div class="form-group">
                        <label>Door height (m)</label>
                        <input type="number" id="stair-${i}-door-h" value="${s.doorH}" step="0.05" min="1.8" max="2.5">
                    </div>
                    <div class="form-group">
                        <label>Door gap (mm)</label>
                        <input type="number" id="stair-${i}-gap" value="${s.gap}" step="0.5" min="1" max="10">
                    </div>
                    <div class="form-group">
                        <label>Doors per floor</label>
                        <input type="number" id="stair-${i}-doors" value="${s.doors}" min="1" max="2">
                    </div>
                    <div class="form-group">
                        <label>Serves bottom floor</label>
                        <input type="number" id="stair-${i}-bottom" value="${s.bottom}" min="1" max="${totalFloors}">
                    </div>
                    <div class="form-group">
                        <label>Serves top floor</label>
                        <input type="number" id="stair-${i}-top" value="${top}" min="1" max="${totalFloors}">
                    </div>
                    <div class="form-group">
                        <label>Exterior walls (n)</label>
                        <input type="number" id="stair-${i}-ext-walls" value="${s.extWalls}" min="0" max="4">
                    </div>
                    <div class="form-group">
                        <label>Ext wall length (m)</label>
                        <input type="number" id="stair-${i}-ext-len" value="${s.extLen}" step="0.5" min="0" max="20">
                    </div>
                    <div class="form-group">
                        <label>Perimeter (m)</label>
                        <input type="number" id="stair-${i}-perim" value="${(s.perim || 6 * Math.sqrt(s.area / 2)).toFixed(1)}" step="0.5" min="4" max="80">
                    </div>
                </div>
            </div>`;
        }).join('');
    }

    function updateStairLabel(idx, newLabel) {
        stairwells[idx].label = newLabel;
    }

    // -----------------------------------------------------------------------
    // Collect Inputs
    // -----------------------------------------------------------------------
    function domVal(id) {
        const el = document.getElementById(id);
        if (!el) return '';
        return el.value;
    }
    function numVal(id) {
        return parseFloat(domVal(id)) || 0;
    }
    function intVal(id) {
        return parseInt(domVal(id)) || 0;
    }

    function collectInputs() {
        const totalFloors = intVal('est-n-floors-above') + intVal('est-n-floors-below');
        const stairData = stairwells.map((s, i) => ({
            label: domVal(`stair-${i}-label`) || s.label,
            cross_section_area: numVal(`stair-${i}-area`),
            // Use explicit perimeter input; fallback to 2:1 rectangle approximation
            cross_section_perimeter: numVal(`stair-${i}-perim`) || 6 * Math.sqrt(numVal(`stair-${i}-area`) / 2),
            door_width: numVal(`stair-${i}-door-w`),
            door_height: numVal(`stair-${i}-door-h`),
            door_gap_mm: numVal(`stair-${i}-gap`),
            doors_per_floor: intVal(`stair-${i}-doors`),
            serves_bottom: intVal(`stair-${i}-bottom`),
            serves_top: intVal(`stair-${i}-top`) || totalFloors,
            n_exterior_walls: intVal(`stair-${i}-ext-walls`),
            exterior_wall_length: numVal(`stair-${i}-ext-len`),
        }));

        const criteria = {
            min_dp_closed: numVal('est-min-dp'),
            max_dp_closed: numVal('est-max-dp'),
            min_door_velocity: numVal('est-min-velocity'),
            max_door_force: numVal('est-max-force'),
            floor_exhaust_dp: numVal('est-exhaust-dp'),
            door_closer_force: numVal('est-closer-force'),
        };
        lastCriteria = criteria;

        return {
            building: {
                n_floors_above: intVal('est-n-floors-above'),
                n_floors_below: intVal('est-n-floors-below'),
                floor_height: numVal('est-floor-height'),
                building_perimeter: numVal('est-bldg-perimeter'),
                floor_area: numVal('est-floor-area'),
                wall_construction: domVal('est-wall-construction'),
            },
            stairwells: stairData,
            elevators: {
                n_shafts: intVal('est-elev-n'),
                shaft_area: numVal('est-elev-area'),
                door_type: domVal('est-elev-door-type'),
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
                is_sprinklered: domVal('est-sprinklered') === 'yes',
                design_fire_hrr: numVal('est-fire-hrr'),
            },
            leakage: {
                exterior_wall: domVal('est-leak-ext-wall'),
                interior_wall: domVal('est-leak-int-wall'),
                floor_ceiling: domVal('est-leak-floor'),
                stair_door: domVal('est-leak-stair-door'),
                elevator_door: domVal('est-leak-elev-door'),
            },
            criteria: criteria,
            stairwell_temp_assumption: domVal('est-stair-temp'),
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
            const data = await apiJson('POST', '/api/estimation/run', body);
            lastResult = data;

            if (data.status !== 'ok') {
                showStatus('est-status', 'Calculation failed: ' + (data.detail || 'Unknown error'), 'error');
                return;
            }

            const badge = data.all_constraints_met
                ? '<span class="est-badge est-badge-pass">ALL CONSTRAINTS MET</span>'
                : '<span class="est-badge est-badge-fail">CONSTRAINTS VIOLATED</span>';
            showStatus('est-status', badge, 'raw');

            // Show warnings
            if (data.warnings && data.warnings.length > 0) {
                const warnDiv = document.getElementById('est-warnings');
                warnDiv.style.display = 'block';
                warnDiv.innerHTML = '<div class="warn-box">' +
                    data.warnings.map(w => `<p>${esc(w)}</p>`).join('') + '</div>';
            }

            renderMethodology(data);
            renderSystemSummary(data);
            renderFloorTables(data);
            renderExhaust(data);
            renderSensitivity(data);
            renderCalculationTraces(data);

            // Show report buttons
            document.getElementById('est-report-btns').style.display = '';

        } catch (e) {
            showStatus('est-status', 'Error: ' + e.message, 'error');
        }
    }

    // -----------------------------------------------------------------------
    // Render Results
    // -----------------------------------------------------------------------
    function hideResults() {
        document.getElementById('est-warnings').style.display = 'none';
        const methDiv = document.getElementById('est-methodology-section');
        if (methDiv) methDiv.style.display = 'none';
        document.getElementById('est-system-summary').style.display = 'none';
        document.getElementById('est-floor-tables').style.display = 'none';
        document.getElementById('est-exhaust-section').style.display = 'none';
        document.getElementById('est-sensitivity-section').style.display = 'none';
        document.getElementById('est-report-btns').style.display = 'none';
        const tracesDiv = document.getElementById('est-traces-section');
        if (tracesDiv) tracesDiv.style.display = 'none';
    }

    // Unit conversion helpers (SI → Imperial)
    function paToInwg(pa) { return pa / 249.089; }
    function nToLbf(n) { return n * 0.224809; }
    function fmtDP(pa) { return `${pa.toFixed(2)} Pa (${paToInwg(pa).toFixed(4)} in.&nbsp;w.g.)`; }
    function fmtForce(n) { return `${n.toFixed(1)} N (${nToLbf(n).toFixed(1)} lbf)`; }

    function renderSystemSummary(data) {
        if (!data.stair_results) return;
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

        if (data.exhaust_result) {
            const er = data.exhaust_result;
            html += '<tr><td colspan="2" style="border-top:2px solid #2e3a4e;"></td></tr>';
            html += `<tr class="highlight-row"><td><strong>Fire Floor Exhaust (at fire temp)</strong></td>
                     <td><strong>${er.q_exhaust_total.toFixed(4)} m&sup3;/s (${er.q_exhaust_total_cfm} CFM)</strong></td></tr>`;
            html += `<tr class="highlight-row"><td><strong>Fire Floor Exhaust (std 20&deg;C)</strong></td>
                     <td><strong>${er.q_exhaust_std.toFixed(4)} m&sup3;/s (${er.q_exhaust_std_cfm} CFM)</strong></td></tr>`;
        }
        html += `<tr><td>NPP Height</td><td>${data.npp_height} m above grade</td></tr>`;

        html += '</tbody></table>';
        document.getElementById('est-summary-content').innerHTML = html;
    }

    function renderFloorTables(data) {
        if (!data.stair_results) return;
        const div = document.getElementById('est-floor-tables');
        div.style.display = 'block';
        let html = '';
        const maxForce = lastCriteria.max_door_force || 133;

        for (const sr of data.stair_results) {
            html += `<h4>${esc(sr.label)}</h4>`;
            html += `<table class="est-table results-table">
                <thead><tr>
                    <th>Floor</th><th>Height (m)</th>
                    <th>&Delta;P_stack<br>(Pa / in.w.g.)</th>
                    <th>&Delta;P_wind<br>(Pa / in.w.g.)</th>
                    <th>&Delta;P_net<br>(Pa / in.w.g.)</th>
                    <th>Q_leak (CFM)</th>
                    <th>Q_open (CFM)</th>
                    <th>F_total<br>(N / lbf)</th><th>Status</th>
                </tr></thead><tbody>`;

            for (const fr of (sr.floor_results || [])) {
                const cls = fr.status === 'PASS' ? 'pass' : 'fail';
                const reasons = fr.failure_reasons || [];
                const title = reasons.length ? ` title="${esc(reasons.join('; '))}"` : '';
                const dpStackInwg = paToInwg(fr.dp_stack).toFixed(4);
                const dpWindInwg = paToInwg(fr.dp_wind).toFixed(4);
                const dpNetInwg = paToInwg(fr.dp_net).toFixed(4);
                const fLbf = nToLbf(fr.f_total).toFixed(1);
                html += `<tr>
                    <td class="level-cell">${esc(fr.floor_label)}</td>
                    <td>${fr.height.toFixed(1)}</td>
                    <td>${fr.dp_stack.toFixed(2)}<br><small>${dpStackInwg}</small></td>
                    <td>${fr.dp_wind.toFixed(2)}<br><small>${dpWindInwg}</small></td>
                    <td class="${cls}">${fr.dp_net.toFixed(2)}<br><small>${dpNetInwg}</small></td>
                    <td>${fr.q_leak_closed_cfm.toFixed(0)}</td>
                    <td>${fr.q_flow_open_cfm > 0 ? fr.q_flow_open_cfm.toFixed(0) : '-'}</td>
                    <td${fr.f_total > maxForce ? ' class="fail"' : ''}>${fr.f_total.toFixed(1)}<br><small>${fLbf}</small></td>
                    <td class="${cls}"${title}>${fr.status}</td>
                </tr>`;
            }
            html += '</tbody></table>';
        }

        document.getElementById('est-floor-content').innerHTML = html;
    }

    function renderExhaust(data) {
        if (!data.exhaust_result) return;
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
        for (const [name, flowVal, cfm] of items) {
            const safeVal = flowVal || 0;
            const pct = (safeVal / total * 100).toFixed(1);
            html += `<tr><td>${name}</td><td>${safeVal.toFixed(4)}</td><td>${cfm || 0}</td><td>${pct}%</td></tr>`;
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
    // Calculation Methodology (KaTeX-rendered LaTeX equations)
    // -----------------------------------------------------------------------

    /** Trigger KaTeX auto-render on a container element */
    function renderKaTeX(el) {
        if (typeof renderMathInElement === 'function') {
            renderMathInElement(el, {
                delimiters: [
                    { left: '$$', right: '$$', display: true },
                    { left: '\\(', right: '\\)', display: false },
                ],
                throwOnError: false,
            });
        }
    }

    function renderMethodology(data) {
        const div = document.getElementById('est-methodology-section');
        if (!div) return;
        div.style.display = 'block';

        const cr = lastCriteria;
        const minDpInwg = paToInwg(cr.min_dp_closed || 12.5).toFixed(2);
        const maxDpInwg = paToInwg(cr.max_dp_closed || 87).toFixed(2);
        const exhDpInwg = paToInwg(cr.floor_exhaust_dp || 25).toFixed(2);
        const maxForceLbf = nToLbf(cr.max_door_force || 133).toFixed(0);

        const html = `
        <div class="meth-intro">
            This section documents the step-by-step procedure used to determine the
            <strong>minimum stair pressurization supply air</strong> and the <strong>minimum
            fire-floor exhaust (depressurization)</strong> rates. All equations reference
            ASHRAE <em>Handbook of Smoke Control Engineering</em> (HSCE).
        </div>

        <div class="meth-group">
            <h4 class="meth-group-title">Design Criteria (Code-Driven Inputs)</h4>
            <table class="est-table meth-criteria-table">
                <thead><tr><th>Parameter</th><th>Symbol</th><th>Value</th><th>Source</th></tr></thead>
                <tbody>
                    <tr><td>Min stairwell-to-corridor pressure (all doors closed)</td>
                        <td>\\(\\Delta P_{\\min}\\)</td>
                        <td>${cr.min_dp_closed || 12.5} Pa (${minDpInwg} in.&nbsp;w.g.)</td>
                        <td>IBC 909.20.5.1</td></tr>
                    <tr><td>Max stairwell-to-corridor pressure (all doors closed)</td>
                        <td>\\(\\Delta P_{\\max}\\)</td>
                        <td>${cr.max_dp_closed || 87} Pa (${maxDpInwg} in.&nbsp;w.g.)</td>
                        <td>NFPA 92 &sect;4.4.2.1</td></tr>
                    <tr><td>Min door opening velocity (sprinklered)</td>
                        <td>\\(V_{\\min}\\)</td>
                        <td>${cr.min_door_velocity || 1.0} m/s</td>
                        <td>IBC 909.20.5.2</td></tr>
                    <tr><td>Max door-opening force</td>
                        <td>\\(F_{\\max}\\)</td>
                        <td>${cr.max_door_force || 133} N (${maxForceLbf} lbf)</td>
                        <td>IBC 1010.1.3</td></tr>
                    <tr><td>Fire-floor exhaust pressure differential</td>
                        <td>\\(\\Delta P_{\\mathrm{exhaust}}\\)</td>
                        <td>${cr.floor_exhaust_dp || 25} Pa (${exhDpInwg} in.&nbsp;w.g.)</td>
                        <td>IBC 909.20.6</td></tr>
                </tbody>
            </table>
        </div>

        <div class="meth-group">
            <h4 class="meth-group-title">Step 1 &mdash; Air Densities</h4>
            <div class="meth-eq">
                <span class="meth-id">EQ-01</span>
                <div class="meth-body">
                    <div class="meth-name">Air density (ideal gas law)</div>
                    <div class="meth-formula">$$\\rho = \\frac{P_{\\mathrm{atm}}}{R_{\\mathrm{air}} \\cdot T}$$</div>
                    <div class="meth-where">where \\(R_{\\mathrm{air}} = 287.058\\;\\text{J/(kg\\cdot K)}\\), \\(T\\) in Kelvin; computed for outdoor, indoor, stairwell, and fire-floor temperatures</div>
                </div>
            </div>
        </div>

        <div class="meth-group">
            <h4 class="meth-group-title">Step 2 &mdash; Leakage Areas</h4>
            <div class="meth-eq">
                <span class="meth-id">EQ-02</span>
                <div class="meth-body">
                    <div class="meth-name">Door crack leakage area</div>
                    <div class="meth-formula">$$A_{Ld} = g_d \\cdot \\bigl(2\\,w_d + 2\\,h_d - w_{\\mathrm{threshold}}\\bigr)$$</div>
                    <div class="meth-where">where \\(g_d\\) = door gap (m), \\(w_d\\) = door width, \\(h_d\\) = door height</div>
                </div>
            </div>
            <div class="meth-eq">
                <span class="meth-id">EQ-05</span>
                <div class="meth-body">
                    <div class="meth-name">Parallel leakage areas</div>
                    <div class="meth-formula">$$A_{\\mathrm{eff}} = A_1 + A_2 + \\cdots + A_n$$</div>
                </div>
            </div>
            <div class="meth-eq">
                <span class="meth-id">EQ-06</span>
                <div class="meth-body">
                    <div class="meth-name">Series leakage areas</div>
                    <div class="meth-formula">$$\\frac{1}{A_{\\mathrm{eff}}^{\\,2}} = \\frac{1}{A_1^{\\,2}} + \\frac{1}{A_2^{\\,2}} + \\cdots + \\frac{1}{A_n^{\\,2}}$$</div>
                </div>
            </div>
            <table class="est-table meth-leak-table">
                <thead><tr><th>Component</th><th>Tight</th><th>Average</th><th>Loose</th><th>Unit</th></tr></thead>
                <tbody>
                    <tr><td>Stair door</td><td>0.01</td><td>0.02</td><td>0.04</td><td>m&sup2; per door</td></tr>
                    <tr><td>Elevator door</td><td>0.02</td><td>0.06</td><td>0.11</td><td>m&sup2; per door</td></tr>
                    <tr><td>Exterior wall</td><td>\\(0.5\\!\\times\\!10^{-4}\\)</td><td>\\(1.7\\!\\times\\!10^{-4}\\)</td><td>\\(5.0\\!\\times\\!10^{-4}\\)</td><td>m&sup2;/m&sup2; wall</td></tr>
                    <tr><td>Floor/ceiling</td><td>\\(0.2\\!\\times\\!10^{-4}\\)</td><td>\\(0.8\\!\\times\\!10^{-4}\\)</td><td>\\(2.5\\!\\times\\!10^{-4}\\)</td><td>m&sup2;/m&sup2; floor</td></tr>
                </tbody>
            </table>
        </div>

        <div class="meth-group">
            <h4 class="meth-group-title">Step 3 &mdash; Stack Effect at Each Floor</h4>
            <div class="meth-eq">
                <span class="meth-id">EQ-07</span>
                <div class="meth-body">
                    <div class="meth-name">Stack-effect pressure differential</div>
                    <div class="meth-formula">$$\\Delta P_s(h) = 3460 \\left(\\frac{1}{T_o} - \\frac{1}{T_s}\\right) \\left(h - h_{\\mathrm{NPP}}\\right)$$</div>
                    <div class="meth-where">where \\(h_{\\mathrm{NPP}}\\) = neutral pressure plane height, found iteratively via mass balance (EQ-08)</div>
                </div>
            </div>
        </div>

        <div class="meth-group">
            <h4 class="meth-group-title">Step 4 &mdash; Wind Pressure</h4>
            <div class="meth-eq">
                <span class="meth-id">EQ-09</span>
                <div class="meth-body">
                    <div class="meth-name">Wind-induced pressure on building face</div>
                    <div class="meth-formula">$$\\Delta P_w = \\tfrac{1}{2}\\, C_p\\, \\rho_o\\, V_w^{\\,2}$$</div>
                    <div class="meth-where">where \\(C_p\\): windward = +0.70, leeward = &minus;0.45, side = &minus;0.60</div>
                </div>
            </div>
        </div>

        <div class="meth-group">
            <h4 class="meth-group-title">Step 5 &mdash; Net Pressure at Each Floor</h4>
            <div class="meth-eq">
                <span class="meth-id">EQ-15</span>
                <div class="meth-body">
                    <div class="meth-name">Net stairwell-to-floor pressure differential</div>
                    <div class="meth-formula">$$\\Delta P_{\\mathrm{net}} = \\Delta P_{\\mathrm{mech}} + \\Delta P_{\\mathrm{stack}} + \\Delta P_{\\mathrm{wind}} - \\Delta P_{\\mathrm{exhaust}}$$</div>
                    <div class="meth-where">
                        \\(\\Delta P_{\\mathrm{exhaust}}\\) applies only on fire floor; must satisfy
                        \\(\\Delta P_{\\min} \\le \\Delta P_{\\mathrm{net}} \\le \\Delta P_{\\max}\\)
                    </div>
                </div>
            </div>
        </div>

        <div class="meth-group">
            <h4 class="meth-group-title">Step 6 &mdash; Leakage Flow Through Closed Doors</h4>
            <div class="meth-eq">
                <span class="meth-id">EQ-03</span>
                <div class="meth-body">
                    <div class="meth-name">Volumetric orifice flow</div>
                    <div class="meth-formula">$$Q = C_d \\cdot A \\sqrt{\\frac{2\\,|\\Delta P|}{\\rho}}$$</div>
                    <div class="meth-where">where \\(C_d = 0.65\\) (discharge coefficient); summed across all floors</div>
                </div>
            </div>
        </div>

        <div class="meth-group">
            <h4 class="meth-group-title">Step 7 &mdash; Open-Door Flow Requirement</h4>
            <div class="meth-eq">
                <span class="meth-id">EQ-12</span>
                <div class="meth-body">
                    <div class="meth-name">Required flow through each open door</div>
                    <div class="meth-formula">$$Q_{\\mathrm{open}} = V_{\\min} \\cdot w_d \\cdot h_d$$</div>
                    <div class="meth-where">Prevents smoke migration through open doorway into stairwell</div>
                </div>
            </div>
        </div>

        <div class="meth-group">
            <h4 class="meth-group-title">Step 8 &mdash; Door-Opening Force Check</h4>
            <div class="meth-eq">
                <span class="meth-id">EQ-10b</span>
                <div class="meth-body">
                    <div class="meth-name">Total door-opening force</div>
                    <div class="meth-formula">$$F_{\\mathrm{total}} = F_{\\mathrm{closer}} + \\frac{\\Delta P \\cdot w_d \\cdot h_d}{2} \\cdot \\frac{w_d}{w_d - d}$$</div>
                    <div class="meth-where">where \\(d\\) = handle-to-latch distance; \\(F_{\\mathrm{total}} \\le F_{\\max} = ${cr.max_door_force || 133}\\) N (${maxForceLbf} lbf)</div>
                </div>
            </div>
            <div class="meth-eq">
                <span class="meth-id">EQ-10b'</span>
                <div class="meth-body">
                    <div class="meth-name">Maximum allowable pressure from force constraint (rearranged)</div>
                    <div class="meth-formula">$$\\Delta P_{\\max} = \\frac{2\\,(F_{\\max} - F_{\\mathrm{closer}})\\,(w_d - d)}{w_d^{\\,2} \\cdot h_d}$$</div>
                </div>
            </div>
        </div>

        <div class="meth-group">
            <h4 class="meth-group-title">Step 9 &mdash; Minimum Stair Supply Air</h4>
            <div class="meth-eq">
                <span class="meth-id">EQ-13</span>
                <div class="meth-body">
                    <div class="meth-name">Total supply &mdash; all doors closed</div>
                    <div class="meth-formula">$$Q_{\\mathrm{supply,closed}} = \\sum Q_{\\mathrm{leak,doors}} + \\sum Q_{\\mathrm{leak,walls}}$$</div>
                </div>
            </div>
            <div class="meth-eq">
                <span class="meth-id">EQ-14</span>
                <div class="meth-body">
                    <div class="meth-name">Total supply &mdash; design doors open</div>
                    <div class="meth-formula">$$Q_{\\mathrm{supply,open}} = \\sum Q_{\\mathrm{closed\\;floors}} + n_{\\mathrm{open}} \\cdot Q_{\\mathrm{open}} + \\sum Q_{\\mathrm{walls}}$$</div>
                </div>
            </div>
            <div class="meth-eq meth-eq-highlight">
                <span class="meth-id">DESIGN</span>
                <div class="meth-body">
                    <div class="meth-name">Governing supply air rate (primary output for fan sizing)</div>
                    <div class="meth-formula">$$\\boxed{Q_{\\mathrm{design}} = \\max\\!\\left(Q_{\\mathrm{supply,closed}},\\; Q_{\\mathrm{supply,open}}\\right)}$$</div>
                </div>
            </div>
        </div>

        <div class="meth-group">
            <h4 class="meth-group-title">Step 10 &mdash; Minimum Fire-Floor Exhaust (Depressurization)</h4>
            <div class="meth-eq">
                <span class="meth-id">EQ-19</span>
                <div class="meth-body">
                    <div class="meth-name">Stairwell leakage into fire floor</div>
                    <div class="meth-formula">$$Q_{\\mathrm{stair}} = C_d \\cdot A_{Ld} \\cdot n_d \\cdot \\sqrt{\\frac{2\\,(\\Delta P_{\\mathrm{mech}} + \\Delta P_{\\mathrm{exhaust}})}{\\rho_s}}$$</div>
                </div>
            </div>
            <div class="meth-eq">
                <span class="meth-id">EQ-20</span>
                <div class="meth-body">
                    <div class="meth-name">Elevator shaft leakage into fire floor</div>
                    <div class="meth-formula">$$Q_{\\mathrm{elev}} = C_d \\cdot A_{Le} \\cdot n_{\\mathrm{elev}} \\cdot \\sqrt{\\frac{2\\,\\Delta P_{\\mathrm{elev}}}{\\rho_i}}$$</div>
                </div>
            </div>
            <div class="meth-eq">
                <span class="meth-id">EQ-21</span>
                <div class="meth-body">
                    <div class="meth-name">Exterior wall leakage into fire floor</div>
                    <div class="meth-formula">$$Q_{\\mathrm{ext}} = C_d \\cdot (A_{Lw} \\cdot P_{\\mathrm{face}} \\cdot h_f) \\cdot \\sqrt{\\frac{2\\,(\\Delta P_{\\mathrm{exh}} + \\Delta P_{\\mathrm{wind}})}{\\rho_o}}$$</div>
                    <div class="meth-where">Summed across all four building faces</div>
                </div>
            </div>
            <div class="meth-eq">
                <span class="meth-id">EQ-22</span>
                <div class="meth-body">
                    <div class="meth-name">Vertical leakage (floor above + below fire floor)</div>
                    <div class="meth-formula">$$Q_{\\mathrm{vert}} = 2\\,C_d \\cdot (A_{Lf} \\cdot A_{\\mathrm{floor}}) \\cdot \\sqrt{\\frac{2\\,\\Delta P_{\\mathrm{exhaust}}}{\\rho_i}}$$</div>
                </div>
            </div>
            <div class="meth-eq">
                <span class="meth-id">EQ-24</span>
                <div class="meth-body">
                    <div class="meth-name">Fire plume air entrainment</div>
                    <div class="meth-formula">$$Q_{\\mathrm{fire}} = \\frac{\\dot{H}}{\\rho_i \\cdot c_p \\cdot (T_f - T_i)}$$</div>
                    <div class="meth-where">where \\(\\dot{H}\\) = design fire HRR (W), \\(c_p = 1005\\;\\text{J/(kg\\cdot K)}\\)</div>
                </div>
            </div>
            <div class="meth-eq">
                <span class="meth-id">EQ-23</span>
                <div class="meth-body">
                    <div class="meth-name">Thermal expansion volume</div>
                    <div class="meth-formula">$$Q_{\\mathrm{expansion}} = Q_{\\mathrm{fire}} \\cdot \\left(\\frac{T_f}{T_i} - 1\\right)$$</div>
                </div>
            </div>
            <div class="meth-eq meth-eq-highlight">
                <span class="meth-id">EQ-25</span>
                <div class="meth-body">
                    <div class="meth-name">Total fire-floor exhaust (at fire temperature)</div>
                    <div class="meth-formula">$$\\boxed{Q_{\\mathrm{exhaust}} = Q_{\\mathrm{stair}} + Q_{\\mathrm{elev}} + Q_{\\mathrm{ext}} + Q_{\\mathrm{vert}} + Q_{\\mathrm{expansion}}}$$</div>
                </div>
            </div>
            <div class="meth-eq">
                <span class="meth-id">EQ-26</span>
                <div class="meth-body">
                    <div class="meth-name">Exhaust corrected to standard conditions (20&deg;C)</div>
                    <div class="meth-formula">$$Q_{\\mathrm{std}} = Q_{\\mathrm{exhaust}} \\cdot \\frac{T_f}{T_{\\mathrm{std}}}$$</div>
                    <div class="meth-where">where \\(T_{\\mathrm{std}} = 293.15\\;\\text{K}\\) (20&deg;C)</div>
                </div>
            </div>
        </div>

        <div class="meth-group">
            <h4 class="meth-group-title">Steps 11&ndash;12 &mdash; Convergence &amp; Sensitivity</h4>
            <div class="meth-note">
                Steps 3&ndash;10 are solved <strong>iteratively</strong> because the NPP, stack pressures,
                and flow rates are mutually dependent. The procedure repeats until supply and exhaust
                totals converge within 0.5%. A mandatory <strong>sensitivity analysis</strong> then varies
                wall leakage, door leakage, outdoor temperature, number of open doors, fire temperature,
                wind speed, and elevator shaft configuration to identify the governing case.
            </div>
        </div>
        `;

        const content = document.getElementById('est-methodology-content');
        content.innerHTML = html;
        renderKaTeX(content);
    }

    let methodologyCollapsed = false;
    function toggleMethodology() {
        methodologyCollapsed = !methodologyCollapsed;
        const content = document.getElementById('est-methodology-content');
        const btn = document.getElementById('meth-toggle-btn');
        if (content) content.style.display = methodologyCollapsed ? 'none' : '';
        if (btn) btn.textContent = methodologyCollapsed ? 'Expand' : 'Collapse';
    }

    function renderCalculationTraces(data) {
        if (!data.calculation_traces || data.calculation_traces.length === 0) return;
        const div = document.getElementById('est-traces-section');
        if (!div) return;
        div.style.display = 'block';

        let html = '';
        for (const tr of data.calculation_traces) {
            const inputs = Object.entries(tr.inputs || {}).map(([k,v]) => `${esc(k)} = ${esc(v)}`).join(', ');
            html += `<div class="trace-block">
                <div class="trace-eq">${esc(tr.equation_id)}: ${esc(tr.description)}</div>
                <div>Formula: ${esc(tr.formula)}</div>
                <div>Inputs: ${esc(inputs)}</div>
                <div>Substitution: ${esc(tr.substitution)}</div>
                <div>Result: <strong>${esc(tr.result)}</strong></div>
            </div>`;
        }

        document.getElementById('est-traces-content').innerHTML = html;
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
        if (text === null || text === undefined) return '';
        const d = document.createElement('div');
        d.textContent = String(text);
        return d.innerHTML;
    }

    function showStatus(id, msg, type) {
        const el = document.getElementById(id);
        if (!el) return;
        el.innerHTML = msg;
        if (type === 'raw') {
            el.className = 'status-msg';
            el.style.display = 'block';
        } else {
            el.className = 'status-msg ' + (type || '');
            el.style.display = '';  // Reset inline style; let CSS class control
        }
    }

    // -----------------------------------------------------------------------
    // PRJ Import & Auto-Fill
    // -----------------------------------------------------------------------
    function initDropZone() {
        const banner = document.getElementById('est-drop-banner');
        const fileInput = document.getElementById('est-prj-input');
        if (!banner || !fileInput) return;

        // Click banner to browse
        banner.addEventListener('click', (e) => {
            if (e.target.tagName !== 'INPUT') fileInput.click();
        });

        fileInput.addEventListener('change', () => {
            if (fileInput.files.length > 0) {
                importPrjFile(fileInput.files[0]);
                fileInput.value = '';  // reset so same file can be re-dropped
            }
        });

        // Banner drag events
        banner.addEventListener('dragover', (e) => { e.preventDefault(); e.stopPropagation(); banner.classList.add('drag-over'); });
        banner.addEventListener('dragleave', (e) => { e.preventDefault(); e.stopPropagation(); banner.classList.remove('drag-over'); });
        banner.addEventListener('drop', (e) => {
            e.preventDefault(); e.stopPropagation();
            banner.classList.remove('drag-over');
            const f = e.dataTransfer.files;
            if (f.length > 0 && f[0].name.toLowerCase().endsWith('.prj')) importPrjFile(f[0]);
        });

        // Page-level drag/drop (so user can drop anywhere)
        document.body.addEventListener('dragover', (e) => {
            e.preventDefault();
            banner.classList.add('drag-over');
        });
        document.body.addEventListener('dragleave', (e) => {
            if (!e.relatedTarget || e.relatedTarget === document.documentElement) {
                banner.classList.remove('drag-over');
            }
        });
        document.body.addEventListener('drop', (e) => {
            e.preventDefault();
            banner.classList.remove('drag-over');
            const f = e.dataTransfer.files;
            if (f.length > 0 && f[0].name.toLowerCase().endsWith('.prj')) {
                importPrjFile(f[0]);
            }
        });
    }

    async function importPrjFile(file) {
        const banner = document.getElementById('est-drop-banner');
        const statusSpan = document.getElementById('est-drop-status');

        console.log('[EST] importPrjFile called with:', file.name);

        banner.classList.remove('success', 'error');
        banner.classList.add('loading');
        statusSpan.innerHTML = `Parsing <strong>${esc(file.name)}</strong>...`;

        try {
            const formData = new FormData();
            formData.append('file', file);

            console.log('[EST] Sending POST to /api/estimation/extract-from-prj');
            const resp = await fetch('/api/estimation/extract-from-prj', {
                method: 'POST',
                body: formData,
            });

            console.log('[EST] Response status:', resp.status);
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({ detail: resp.statusText }));
                throw new Error(err.detail || resp.statusText);
            }

            const data = await resp.json();
            console.log('[EST] Received data:', JSON.stringify(data).substring(0, 500));
            applyPrjData(data);

            banner.classList.remove('loading');
            banner.classList.add('success');

            // Build details summary
            const details = data.detection_details || [];
            const detailText = details.length > 0
                ? ' &mdash; ' + details.map(d => esc(d)).join('; ')
                : '';
            statusSpan.innerHTML = `Values loaded from <strong>${esc(file.name)}</strong>${detailText}`;
        } catch (e) {
            console.error('[EST] importPrjFile error:', e);
            banner.classList.remove('loading');
            banner.classList.add('error');
            statusSpan.textContent = 'Error: ' + e.message;
        }
    }

    function applyPrjData(data) {
        const b = data.building || {};
        const c = data.conditions || {};
        const e = data.elevators || {};

        console.log('[EST] applyPrjData — building:', b, 'conditions:', c, 'elevators:', e,
                     'stairwells:', (data.stairwells || []).length);

        // --- Building geometry ---
        setFormVal('est-n-floors-above', b.n_floors_above);
        setFormVal('est-n-floors-below', b.n_floors_below);
        setFormVal('est-floor-height', b.floor_height);
        setFormVal('est-bldg-perimeter', b.building_perimeter);
        setFormVal('est-floor-area', b.floor_area);

        // --- Design conditions ---
        if (c.T_outdoor_winter !== undefined) setFormVal('est-t-winter', c.T_outdoor_winter);
        if (c.wind_speed !== undefined) setFormVal('est-wind-speed', c.wind_speed);
        if (c.wind_direction !== undefined) setFormVal('est-wind-dir', c.wind_direction);

        // --- Elevators ---
        if (e.n_shafts !== undefined) setFormVal('est-elev-n', e.n_shafts);
        if (e.shaft_area !== undefined) setFormVal('est-elev-area', e.shaft_area);

        // --- Fire floor (default to mid-building) ---
        const totalFloors = (b.n_floors_above || 10) + (b.n_floors_below || 0);
        setFormVal('est-fire-floor', Math.max(1, Math.floor(totalFloors / 2)));

        // --- Stairwells ---
        const stairData = data.stairwells || [];
        if (stairData.length > 0) {
            // Replace the stairwell array and re-render
            stairwells = [];
            for (const s of stairData) {
                stairwells.push({
                    label: s.label || `Stair ${String.fromCharCode(65 + stairwells.length)}`,
                    area: s.area || STAIR_DEFAULTS.area,
                    doorW: s.doorW || STAIR_DEFAULTS.doorW,
                    doorH: s.doorH || STAIR_DEFAULTS.doorH,
                    gap: s.gap || STAIR_DEFAULTS.gap,
                    doors: s.doors || STAIR_DEFAULTS.doors,
                    bottom: s.bottom || 1,
                    top: s.top || totalFloors,
                    extWalls: s.extWalls ?? STAIR_DEFAULTS.extWalls,
                    extLen: s.extLen || STAIR_DEFAULTS.extLen,
                    perim: s.perim || 6 * Math.sqrt((s.area || STAIR_DEFAULTS.area) / 2),
                });
            }
            renderStairwells();
            console.log('[EST] Rendered', stairwells.length, 'stairwells from PRJ');
        }

        // Store imported data in localStorage so it persists across page visits
        try { localStorage.setItem('est_prj_data', JSON.stringify(data)); } catch (_) {}

        console.log('[EST] applyPrjData complete');
    }

    function setFormVal(id, value) {
        const el = document.getElementById(id);
        if (el && value !== undefined && value !== null) {
            el.value = value;
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }
    }

    // -----------------------------------------------------------------------
    // Cross-page auto-fill (from CONTAM tool → Estimation via localStorage)
    // -----------------------------------------------------------------------
    function tryLoadFromStorage() {
        try {
            const raw = localStorage.getItem('est_prj_pending');
            if (!raw) return;
            // Only apply once — remove immediately
            localStorage.removeItem('est_prj_pending');
            const data = JSON.parse(raw);
            console.log('[EST] Auto-loading estimation data from localStorage (forwarded from CONTAM tool)');
            applyPrjData(data);
            const banner = document.getElementById('est-drop-banner');
            const statusSpan = document.getElementById('est-drop-status');
            if (banner && statusSpan) {
                banner.classList.add('success');
                const name = data.filename || 'CONTAM model';
                statusSpan.innerHTML = `Values auto-filled from <strong>${esc(name)}</strong>`;
            }
        } catch (e) {
            console.warn('[EST] Failed to load from localStorage:', e);
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
        importPrjFile,
        toggleMethodology,
    };
})();
