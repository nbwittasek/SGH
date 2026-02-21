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

            // Show report buttons (top + bottom)
            document.getElementById('est-report-top').style.display = '';
            document.getElementById('est-report-btns').style.display = '';

        } catch (e) {
            console.error('[Est] runEstimation error:', e);
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
        document.getElementById('est-report-top').style.display = 'none';
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
            html += `<tr class="highlight-row"><td><strong>Fire Floor Exhaust (ambient)</strong></td>
                     <td><strong>${er.q_exhaust_total.toFixed(4)} m&sup3;/s (${er.q_exhaust_total_cfm} CFM)</strong></td></tr>`;
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
    // Calculation Methodology (pure HTML equations — no KaTeX dependency)
    // -----------------------------------------------------------------------

    /** Build an inline stacked fraction (pure HTML/CSS). */
    function frac(num, den) {
        return '<span class="eq-frac"><span class="eq-num">' + num +
               '</span><span class="eq-den">' + den + '</span></span>';
    }

    /** Build a square-root with overline bar on the radicand. */
    function sqrtH(inner) {
        return '<span class="eq-sqrt">&radic;<span class="eq-rad">' + inner + '</span></span>';
    }

    function renderMethodology(data) {
        console.log('[Est] renderMethodology called');
        const div = document.getElementById('est-methodology-section');
        if (!div) { console.warn('[Est] methodology section not found'); return; }
        div.style.display = 'block';

        const cr = lastCriteria;
        const minDp = cr.min_dp_closed || 12.5;
        const maxDp = cr.max_dp_closed || 87;
        const minDpInwg = paToInwg(minDp).toFixed(2);
        const maxDpInwg = paToInwg(maxDp).toFixed(2);
        const exhDp = cr.floor_exhaust_dp || 25;
        const exhDpInwg = paToInwg(exhDp).toFixed(2);
        const maxForce = cr.max_door_force || 133;
        const maxForceLbf = nToLbf(maxForce).toFixed(0);
        const minVel = cr.min_door_velocity || 1.0;

        const html = `
        <div class="meth-intro">
            <strong>Calculation Methodology &mdash; ASHRAE <em>Handbook of Smoke Control Engineering</em></strong><br>
            This section presents the analytical procedure used to determine the minimum stair
            pressurization supply air and fire-floor exhaust rates. The methodology follows the
            algebraic equation method from ASHRAE HSCE, with design criteria drawn from
            NFPA&nbsp;92 and IBC&nbsp;Section&nbsp;909. Equation numbers (EQ-01 through EQ-26)
            correspond to those in the calculation engine and trace output.
        </div>

        <!-- 1. DESIGN OBJECTIVE -->
        <div class="meth-section">
            <h4 class="meth-section-title">1. Design Objective</h4>
            <p class="meth-prose">
                The fundamental goal of stair pressurization is to maintain a positive pressure
                differential between each pressurized stairwell and the adjacent building floor,
                so that smoke cannot migrate into the stairwell during a fire event. Simultaneously,
                the system must not over-pressurize the stairwell to the point where occupants
                cannot open egress doors. These competing requirements define the design window.
            </p>
            <p class="meth-prose">
                The design must satisfy four concurrent constraints drawn from the applicable
                building code (IBC 909, NFPA 92):
            </p>
            <table class="est-table meth-criteria-table">
                <thead><tr><th>Constraint</th><th>Symbol</th><th>Limit</th><th>Code Reference</th></tr></thead>
                <tbody>
                    <tr><td>Minimum stairwell-to-corridor pressure (all doors closed)</td>
                        <td>&Delta;P<sub>min</sub></td>
                        <td>${minDp} Pa (${minDpInwg} in.&nbsp;w.g.)</td>
                        <td>IBC 909.20.5.1</td></tr>
                    <tr><td>Maximum stairwell-to-corridor pressure (all doors closed)</td>
                        <td>&Delta;P<sub>max</sub></td>
                        <td>${maxDp} Pa (${maxDpInwg} in.&nbsp;w.g.)</td>
                        <td>NFPA 92 &sect;4.4.2.1</td></tr>
                    <tr><td>Minimum air velocity through open doors (sprinklered)</td>
                        <td>V<sub>min</sub></td>
                        <td>${minVel} m/s</td>
                        <td>IBC 909.20.5.2</td></tr>
                    <tr><td>Maximum door-opening force</td>
                        <td>F<sub>max</sub></td>
                        <td>${maxForce} N (${maxForceLbf} lbf)</td>
                        <td>IBC 1010.1.3</td></tr>
                </tbody>
            </table>
            <p class="meth-prose">
                When fire-floor exhaust (depressurization) is provided, an additional pressure
                differential of &Delta;P<sub>exhaust</sub> = ${exhDp} Pa
                (${exhDpInwg} in.&nbsp;w.g.) is maintained across the fire floor per IBC 909.20.6.
                The calculation determines both the <strong>minimum stairwell supply air</strong>
                (for fan sizing) and the <strong>minimum fire-floor exhaust rate</strong>.
            </p>
        </div>

        <!-- 2. AIR PROPERTIES -->
        <div class="meth-section">
            <h4 class="meth-section-title">2. Air Properties</h4>
            <p class="meth-prose">
                All flow and pressure calculations depend on the density of air, which varies
                significantly between the heated fire floor, the conditioned building interior,
                the outdoor environment, and the stairwell shaft. Because the stair pressurization
                problem involves buoyancy-driven stack effects, correctly computing density at
                each temperature is essential. Air density is determined from the ideal gas law:
            </p>
            <div class="meth-eq-block">
                <span class="meth-eq-label">EQ-01</span>
                <div class="meth-eq-formula">&rho; = ${frac('P<sub>atm</sub>', 'R<sub>air</sub> &middot; T')}</div>
                <div class="meth-eq-where">
                    where R<sub>air</sub> = 287.058 J/(kg&middot;K) is the specific gas
                    constant for dry air and <em>T</em> is the absolute temperature in Kelvin.
                </div>
            </div>
            <p class="meth-prose">
                This equation is evaluated four times to obtain &rho;<sub>o</sub> (outdoor),
                &rho;<sub>i</sub> (indoor), &rho;<sub>s</sub> (stairwell), and &rho;<sub>f</sub> (fire floor).
                The stairwell temperature may be assumed equal to either the indoor or outdoor
                temperature, depending on shaft insulation and exposure.
            </p>
        </div>

        <!-- 3. BUILDING LEAKAGE CHARACTERIZATION -->
        <div class="meth-section">
            <h4 class="meth-section-title">3. Building Leakage Characterization</h4>
            <p class="meth-prose">
                Real buildings are not airtight. Air leaks through door cracks, wall joints, and
                floor penetrations. The pressurization fan must supply enough air to overcome all
                of these leakage paths while still maintaining the target pressure differential.
                Characterizing these leakage areas is therefore a critical input to the analysis.
            </p>
            <p class="meth-prose">
                For stairwell doors, the leakage area is computed directly from the door geometry
                using the crack method:
            </p>
            <div class="meth-eq-block">
                <span class="meth-eq-label">EQ-02</span>
                <div class="meth-eq-formula">A<sub>Ld</sub> = g<sub>d</sub> &middot; (2 w<sub>d</sub> + 2 h<sub>d</sub> &minus; w<sub>threshold</sub>)</div>
                <div class="meth-eq-where">
                    where g<sub>d</sub> is the uniform gap width around the door perimeter (m),
                    w<sub>d</sub> is the door width, and h<sub>d</sub> is the door height.
                    The threshold width w<sub>threshold</sub> is subtracted because
                    doors typically seal against the threshold.
                </div>
            </div>
            <p class="meth-prose">
                For other building components (exterior walls, floor slabs, elevator doors),
                leakage areas are taken from ASHRAE HSCE tabulated values based on construction
                tightness classification:
            </p>
            <table class="est-table meth-leak-table">
                <thead><tr><th>Component</th><th>Tight</th><th>Average</th><th>Loose</th><th>Unit</th></tr></thead>
                <tbody>
                    <tr><td>Stair door</td><td>0.01</td><td>0.02</td><td>0.04</td><td>m&sup2; per door</td></tr>
                    <tr><td>Elevator door</td><td>0.02</td><td>0.06</td><td>0.11</td><td>m&sup2; per door</td></tr>
                    <tr><td>Exterior wall</td><td>0.5&times;10<sup>&minus;4</sup></td><td>1.7&times;10<sup>&minus;4</sup></td><td>5.0&times;10<sup>&minus;4</sup></td><td>m&sup2;/m&sup2; wall</td></tr>
                    <tr><td>Floor/ceiling</td><td>0.2&times;10<sup>&minus;4</sup></td><td>0.8&times;10<sup>&minus;4</sup></td><td>2.5&times;10<sup>&minus;4</sup></td><td>m&sup2;/m&sup2; floor</td></tr>
                </tbody>
            </table>
            <p class="meth-prose">
                When multiple leakage paths exist on the same floor, they are combined. Paths
                in parallel (e.g., multiple doors on the same floor) are added directly:
            </p>
            <div class="meth-eq-block">
                <span class="meth-eq-label">EQ-05</span>
                <div class="meth-eq-formula">A<sub>eff</sub> = A<sub>1</sub> + A<sub>2</sub> + &hellip; + A<sub>n</sub></div>
            </div>
            <p class="meth-prose">
                Paths in series (e.g., a stair door in series with a corridor wall) combine with
                reduced effective area:
            </p>
            <div class="meth-eq-block">
                <span class="meth-eq-label">EQ-06</span>
                <div class="meth-eq-formula">${frac('1', 'A<sub>eff</sub><sup>2</sup>')} = ${frac('1', 'A<sub>1</sub><sup>2</sup>')} + ${frac('1', 'A<sub>2</sub><sup>2</sup>')} + &hellip; + ${frac('1', 'A<sub>n</sub><sup>2</sup>')}</div>
            </div>
        </div>

        <!-- 4. PRESSURE DISTRIBUTION -->
        <div class="meth-section">
            <h4 class="meth-section-title">4. Pressure Distribution Across the Building Height</h4>
            <p class="meth-prose">
                The net pressure differential between the stairwell and each floor is not
                constant&mdash;it varies with height due to two natural phenomena:
                <strong>stack effect</strong> (buoyancy) and <strong>wind</strong>. Understanding
                this distribution is essential because the critical floor (where the minimum
                pressure or maximum door force occurs) governs the design.
            </p>

            <p class="meth-prose">
                <strong>Stack Effect.</strong>&ensp;When the outdoor temperature differs from the
                stairwell temperature, a buoyancy-driven pressure gradient develops across the
                building height. The stack-effect pressure at any height <em>h</em> relative to the
                neutral pressure plane (NPP) is:
            </p>
            <div class="meth-eq-block">
                <span class="meth-eq-label">EQ-07</span>
                <div class="meth-eq-formula">&Delta;P<sub>s</sub>(h) = 3460 &middot; (${frac('1', 'T<sub>o</sub>')} &minus; ${frac('1', 'T<sub>s</sub>')}) &middot; (h &minus; h<sub>NPP</sub>)</div>
                <div class="meth-eq-where">
                    where the constant 3460 Pa&middot;K/m derives from
                    g &middot; P<sub>atm</sub> / R<sub>air</sub>, and
                    h<sub>NPP</sub> is the neutral pressure plane height.
                </div>
            </div>
            <p class="meth-prose">
                The NPP is the height at which the indoor-to-outdoor pressure difference is zero.
                Its location depends on the distribution of leakage openings in the building
                envelope. The NPP height is found by iteratively solving the mass balance
                condition (EQ-08):
            </p>
            <div class="meth-eq-block">
                <span class="meth-eq-label">EQ-08</span>
                <div class="meth-eq-formula">&Sigma; ṁ<sub>in</sub> = &Sigma; ṁ<sub>out</sub></div>
                <div class="meth-eq-where">
                    The height h<sub>NPP</sub> is adjusted by bisection until the net
                    mass flow through the building envelope equals zero.
                </div>
            </div>
            <p class="meth-prose">
                In winter (cold outdoor air), the stack effect creates positive pressure at
                lower floors and negative pressure at upper floors, making the top of the
                building the critical location for minimum pressure differential. In summer,
                the pattern reverses.
            </p>

            <p class="meth-prose">
                <strong>Wind Effect.</strong>&ensp;Wind striking the building creates positive
                pressure on the windward face and suction on leeward and side faces. The
                wind-induced pressure on each building face is:
            </p>
            <div class="meth-eq-block">
                <span class="meth-eq-label">EQ-09</span>
                <div class="meth-eq-formula">&Delta;P<sub>w</sub> = ${frac('1', '2')} &middot; C<sub>p</sub> &middot; &rho;<sub>o</sub> &middot; V<sub>w</sub><sup>2</sup></div>
                <div class="meth-eq-where">
                    where C<sub>p</sub> is the wind pressure coefficient:
                    windward&nbsp;=&nbsp;+0.70, leeward&nbsp;=&nbsp;&minus;0.45,
                    side&nbsp;=&nbsp;&minus;0.60.
                </div>
            </div>
            <p class="meth-prose">
                Wind can either assist or oppose stairwell pressurization depending on which
                face the stairwell is located on and the wind direction.
            </p>

            <p class="meth-prose">
                <strong>Net Pressure Differential.</strong>&ensp;The total pressure difference between
                the stairwell and each floor combines the mechanical pressurization, stack
                effect, wind, and (on the fire floor) the exhaust depressurization:
            </p>
            <div class="meth-eq-block">
                <span class="meth-eq-label">EQ-15</span>
                <div class="meth-eq-formula">&Delta;P<sub>net</sub> = &Delta;P<sub>mech</sub> + &Delta;P<sub>stack</sub> + &Delta;P<sub>wind</sub> &minus; &Delta;P<sub>exhaust</sub></div>
                <div class="meth-eq-where">
                    &Delta;P<sub>exhaust</sub> applies only on the fire floor.
                    The design must satisfy
                    &Delta;P<sub>min</sub> &le; &Delta;P<sub>net</sub> &le; &Delta;P<sub>max</sub>
                    at every floor.
                </div>
            </div>
        </div>

        <!-- 5. FLOW THROUGH OPENINGS -->
        <div class="meth-section">
            <h4 class="meth-section-title">5. Airflow Through Closed and Open Doors</h4>
            <p class="meth-prose">
                Once the net pressure differential at each floor is known, the resulting
                airflow through each leakage path is computed using the orifice equation.
                This is the fundamental flow relationship used throughout the analysis:
            </p>
            <div class="meth-eq-block">
                <span class="meth-eq-label">EQ-03</span>
                <div class="meth-eq-formula">Q = C<sub>d</sub> &middot; A &middot; ${sqrtH(frac('2 |&Delta;P|', '&rho;'))}</div>
                <div class="meth-eq-where">
                    where C<sub>d</sub> = 0.65 is the discharge coefficient for building leakage
                    paths, A is the effective leakage area, and &rho; is the air
                    density on the upstream side.
                </div>
            </div>
            <p class="meth-prose">
                This equation is applied to every closed door and wall leakage path on every
                floor. The sum of all these flows equals the supply air that the fan must
                deliver.
            </p>

            <p class="meth-prose">
                For the design number of <strong>open doors</strong> (doors held open during
                evacuation), the code requires a minimum air velocity through the doorway to
                prevent smoke migration:
            </p>
            <div class="meth-eq-block">
                <span class="meth-eq-label">EQ-12</span>
                <div class="meth-eq-formula">Q<sub>open</sub> = V<sub>min</sub> &middot; w<sub>d</sub> &middot; h<sub>d</sub></div>
                <div class="meth-eq-where">
                    where V<sub>min</sub> = ${minVel} m/s for sprinklered buildings
                    (1.7 m/s if non-sprinklered). This flow rate per open door is added directly
                    to the supply requirement.
                </div>
            </div>
        </div>

        <!-- 6. DOOR FORCE CONSTRAINT -->
        <div class="meth-section">
            <h4 class="meth-section-title">6. Door-Opening Force Constraint</h4>
            <p class="meth-prose">
                Pressurizing the stairwell makes it harder for occupants to push open egress
                doors. The door-opening force is the sum of the door closer force and the
                force required to overcome the pressure differential acting on the door leaf.
                The moment arm from the pivot (hinge) to the door handle amplifies this force:
            </p>
            <div class="meth-eq-block">
                <span class="meth-eq-label">EQ-10b</span>
                <div class="meth-eq-formula">F<sub>total</sub> = F<sub>closer</sub> + ${frac('&Delta;P &middot; w<sub>d</sub> &middot; h<sub>d</sub>', '2')} &middot; ${frac('w<sub>d</sub>', 'w<sub>d</sub> &minus; d')}</div>
                <div class="meth-eq-where">
                    where <em>d</em> is the handle-to-latch distance. The term
                    w<sub>d</sub> / (w<sub>d</sub> &minus; d) is the lever-arm ratio.
                    This must satisfy F<sub>total</sub> &le; ${maxForce} N (${maxForceLbf} lbf).
                </div>
            </div>
            <p class="meth-prose">
                This constraint can be rearranged to find the maximum allowable pressure
                differential at each door, which sets the upper bound on mechanical
                pressurization:
            </p>
            <div class="meth-eq-block">
                <span class="meth-eq-label">EQ-10b&prime;</span>
                <div class="meth-eq-formula">&Delta;P<sub>max,force</sub> = ${frac('2 (F<sub>max</sub> &minus; F<sub>closer</sub>) (w<sub>d</sub> &minus; d)', 'w<sub>d</sub><sup>2</sup> &middot; h<sub>d</sub>')}</div>
            </div>
            <p class="meth-prose">
                If the required mechanical pressure exceeds this limit, the design must use
                multiple injection points, barometric dampers, or other measures to reduce
                the local pressure differential while maintaining overall shaft pressurization.
            </p>
        </div>

        <!-- 7. STAIRWELL SUPPLY AIR -->
        <div class="meth-section">
            <h4 class="meth-section-title">7. Stairwell Supply Air Determination</h4>
            <p class="meth-prose">
                The supply air rate must be sufficient for two governing scenarios. In the
                <strong>all-doors-closed</strong> case, the fan must supply enough air to
                compensate for leakage through every closed door and wall opening:
            </p>
            <div class="meth-eq-block">
                <span class="meth-eq-label">EQ-13</span>
                <div class="meth-eq-formula">Q<sub>supply,closed</sub> = &Sigma;<sub>all floors</sub> Q<sub>leak,doors</sub> + &Sigma; Q<sub>leak,walls</sub></div>
            </div>
            <p class="meth-prose">
                In the <strong>doors-open</strong> scenario (design number of doors held open
                during evacuation), the fan must supply leakage for the remaining closed
                floors plus the open-door velocity flow:
            </p>
            <div class="meth-eq-block">
                <span class="meth-eq-label">EQ-14</span>
                <div class="meth-eq-formula">Q<sub>supply,open</sub> = &Sigma;<sub>closed floors</sub> Q<sub>leak</sub> + n<sub>open</sub> &middot; Q<sub>open</sub> + &Sigma; Q<sub>leak,walls</sub></div>
            </div>
            <p class="meth-prose">
                The <strong>design supply air rate</strong>&mdash;the primary output for fan
                sizing&mdash;is the larger of these two scenarios:
            </p>
            <div class="meth-eq-block highlight">
                <span class="meth-eq-label">DESIGN</span>
                <div class="meth-eq-formula"><span class="meth-eq-boxed">Q<sub>design</sub> = max(Q<sub>supply,closed</sub>, Q<sub>supply,open</sub>)</span></div>
            </div>
        </div>

        <!-- 8. FIRE FLOOR EXHAUST -->
        <div class="meth-section">
            <h4 class="meth-section-title">8. Fire Floor Exhaust (Depressurization)</h4>
            <p class="meth-prose">
                Per ASHRAE, the fire floor exhaust is calculated at <strong>ambient
                temperature</strong>, targeting a depressurization of
                <strong>0.08&nbsp;in.&nbsp;w.g.</strong> (&asymp;&nbsp;20&nbsp;Pa) on the
                fire floor (&Delta;P<sub>exhaust</sub> = ${exhDp} Pa). The exhaust
                rate equals the sum of all leakage inflows entering the fire floor.
                No design fire, thermal expansion, or elevated-temperature correction
                is applied.
            </p>
            <p class="meth-prose">
                <strong>Stairwell leakage</strong> into the fire floor is driven by both the
                mechanical pressurization and the exhaust-induced negative pressure:
            </p>
            <div class="meth-eq-block">
                <span class="meth-eq-label">EQ-19</span>
                <div class="meth-eq-formula">Q<sub>stair</sub> = C<sub>d</sub> &middot; A<sub>Ld</sub> &middot; n<sub>d</sub> &middot; ${sqrtH(frac('2 (&Delta;P<sub>mech</sub> + &Delta;P<sub>exhaust</sub>)', '&rho;<sub>s</sub>'))}</div>
            </div>
            <p class="meth-prose">
                <strong>Elevator shaft leakage</strong> enters through elevator doors, driven
                by the combination of stack-induced shaft pressure and exhaust:
            </p>
            <div class="meth-eq-block">
                <span class="meth-eq-label">EQ-20</span>
                <div class="meth-eq-formula">Q<sub>elev</sub> = C<sub>d</sub> &middot; A<sub>Le</sub> &middot; n<sub>elev</sub> &middot; ${sqrtH(frac('2 &Delta;P<sub>elev</sub>', '&rho;<sub>i</sub>'))}</div>
            </div>
            <p class="meth-prose">
                <strong>Exterior wall leakage</strong> is summed across all four building faces,
                each experiencing different wind pressures:
            </p>
            <div class="meth-eq-block">
                <span class="meth-eq-label">EQ-21</span>
                <div class="meth-eq-formula">Q<sub>ext</sub> = &Sigma;<sub>faces</sub> C<sub>d</sub> &middot; (A<sub>Lw</sub> &middot; P<sub>face</sub> &middot; h<sub>f</sub>) &middot; ${sqrtH(frac('2 (&Delta;P<sub>exhaust</sub> + &Delta;P<sub>wind</sub>)', '&rho;<sub>o</sub>'))}</div>
            </div>
            <p class="meth-prose">
                <strong>Vertical leakage</strong> from the floors directly above and below the
                fire floor enters through floor/ceiling assemblies:
            </p>
            <div class="meth-eq-block">
                <span class="meth-eq-label">EQ-22</span>
                <div class="meth-eq-formula">Q<sub>vert</sub> = 2 C<sub>d</sub> &middot; (A<sub>Lf</sub> &middot; A<sub>floor</sub>) &middot; ${sqrtH(frac('2 &Delta;P<sub>exhaust</sub>', '&rho;<sub>i</sub>'))}</div>
                <div class="meth-eq-where">
                    The factor of 2 accounts for leakage from both the floor above and below.
                </div>
            </div>
            <p class="meth-prose">
                The <strong>total required exhaust</strong> at ambient conditions is the
                sum of all four leakage components:
            </p>
            <div class="meth-eq-block highlight">
                <span class="meth-eq-label">EQ-25</span>
                <div class="meth-eq-formula"><span class="meth-eq-boxed">Q<sub>exhaust</sub> = Q<sub>stair</sub> + Q<sub>elev</sub> + Q<sub>ext</sub> + Q<sub>vert</sub></span></div>
            </div>
        </div>

        <!-- 9. SOLUTION PROCEDURE -->
        <div class="meth-section">
            <h4 class="meth-section-title">9. Iterative Solution and Sensitivity Analysis</h4>
            <p class="meth-prose">
                The equations above are mutually dependent: the NPP location depends on leakage
                flows, which depend on pressure differentials, which depend on the NPP. The
                solution procedure therefore uses an <strong>iterative approach</strong>:
            </p>
            <p class="meth-prose" style="padding-left:16px;">
                1. Assume an initial NPP height (mid-building).<br>
                2. Compute stack-effect and wind pressures at every floor (EQ-07, EQ-09).<br>
                3. Compute net pressure differentials (EQ-15) and leakage flows (EQ-03).<br>
                4. Sum supply air requirements (EQ-13, EQ-14) and exhaust flows (EQ-19&ndash;EQ-25).<br>
                5. Update the NPP based on the new mass balance (EQ-08).<br>
                6. Repeat until supply and exhaust totals converge within 0.5%.
            </p>
            <p class="meth-prose">
                After convergence, a mandatory <strong>sensitivity analysis</strong> varies
                key parameters&mdash;wall leakage classification, door leakage area (&plusmn;50%),
                outdoor temperature (winter vs. summer), number of open doors (0&ndash;3),
                fire-floor temperature, wind speed, and elevator shaft configuration&mdash;to
                identify the governing case and ensure the design is robust across the
                expected range of operating conditions.
            </p>
        </div>
        `;

        const content = document.getElementById('est-methodology-content');
        content.innerHTML = html;
        content.style.display = '';  // reset in case previously collapsed
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

        // Group traces by equation_id, preserving order
        const groups = [];
        const seen = new Set();
        for (const tr of data.calculation_traces) {
            if (!seen.has(tr.equation_id)) {
                seen.add(tr.equation_id);
                groups.push({ eqId: tr.equation_id, traces: [] });
            }
            groups.find(g => g.eqId === tr.equation_id).traces.push(tr);
        }

        let html = '';
        for (const group of groups) {
            const eqId = group.eqId;
            const isHighlight = (eqId === 'EQ-25' || eqId === 'DESIGN');

            html += `<div class="journal-eq-group${isHighlight ? ' journal-highlight' : ''}">`;
            html += `<div class="journal-eq-header">
                <span class="journal-eq-id">${esc(eqId)}</span>
            </div>`;

            for (const tr of group.traces) {
                html += `<div class="journal-eq-instance">`;
                html += `<div class="journal-eq-desc">${esc(tr.description)}</div>`;

                // Formula in styled block
                html += `<div class="journal-eq-formula">${esc(tr.formula)}</div>`;

                // Inputs as a compact table
                const entries = Object.entries(tr.inputs || {});
                if (entries.length > 0) {
                    html += '<div class="journal-eq-where"><span class="journal-where-label">where</span>';
                    html += '<table class="journal-inputs-table">';
                    for (const [k, v] of entries) {
                        html += `<tr><td class="journal-var">${esc(k)}</td><td class="journal-eq-sep">=</td><td class="journal-val">${esc(v)}</td></tr>`;
                    }
                    html += '</table></div>';
                }

                // Substitution
                html += `<div class="journal-eq-sub">${esc(tr.substitution)}</div>`;

                // Result in highlighted box
                html += `<div class="journal-eq-result">${esc(tr.result)}</div>`;
                html += '</div>';
            }
            html += '</div>';
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
    // Transfer to CONTAM Tool
    // -----------------------------------------------------------------------
    function transferToCONTAM() {
        if (!lastResult || !lastResult.stair_results) {
            alert('Run the estimation first to generate results.');
            return;
        }

        // Build transfer payload with design supply CFM per stair + exhaust CFM
        const transfer = {
            timestamp: new Date().toISOString(),
            stairs: lastResult.stair_results.map(sr => ({
                label: sr.label,
                supply_design_cfm: sr.q_supply_design_cfm,
                supply_closed_cfm: sr.q_supply_closed_cfm,
                supply_open_cfm: sr.q_supply_open_cfm,
            })),
            exhaust_cfm: lastResult.exhaust_result ? lastResult.exhaust_result.q_exhaust_total_cfm : 0,
            npp_height_m: lastResult.npp_height,
            all_constraints_met: lastResult.all_constraints_met,
        };

        localStorage.setItem('estimation_transfer', JSON.stringify(transfer));

        // Build a summary message
        let msg = 'Estimation results ready for CONTAM tool:\n\n';
        for (const s of transfer.stairs) {
            msg += `  ${s.label}: ${s.supply_design_cfm} CFM (design supply)\n`;
        }
        msg += `  Exhaust: ${transfer.exhaust_cfm} CFM\n\n`;
        msg += 'Opening the CONTAM tool now. Use the values above to configure your stair pressurization SCFM and corridor exhaust rates.';

        alert(msg);
        window.open('/', '_blank');
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
        transferToCONTAM,
    };
})();
