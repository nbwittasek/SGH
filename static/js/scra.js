/**
 * SCRA Generator — Frontend Logic
 * Handles the 5-step wizard for generating Smoke Control Rational Analysis reports.
 */

let currentStep = 1;
let prjData = null;      // Extracted PRJ data
let reportHtml = null;   // Generated report HTML
let stairs = [];         // Stair definitions

// ---------------------------------------------------------------------------
// Step Navigation
// ---------------------------------------------------------------------------
function goToStep(step) {
    // Validate before advancing
    if (step > currentStep) {
        for (let s = currentStep; s < step; s++) {
            if (!validateStep(s)) return;
        }
    }

    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.step').forEach(s => {
        const sn = parseInt(s.dataset.step);
        s.classList.remove('active');
        if (sn < step) s.classList.add('done');
        else s.classList.remove('done');
        if (sn === step) s.classList.add('active');
    });
    document.getElementById(`panel-${step}`).classList.add('active');
    currentStep = step;

    if (step === 5) buildSummary();
}

function validateStep(step) {
    if (step === 1) {
        const name = document.getElementById('project_name').value.trim();
        if (!name) {
            showStatus('Please enter a project name.', 'error');
            return false;
        }
    }
    return true;
}

// ---------------------------------------------------------------------------
// Status Messages
// ---------------------------------------------------------------------------
function showStatus(msg, type) {
    const el = document.getElementById('status');
    el.textContent = msg;
    el.className = `status-msg ${type}`;
    if (type !== 'error') {
        setTimeout(() => { el.className = 'status-msg'; }, 5000);
    }
}

// ---------------------------------------------------------------------------
// PRJ File Upload
// ---------------------------------------------------------------------------
async function handlePrjUpload(input) {
    const file = input.files[0];
    if (!file) return;

    const dropzone = document.getElementById('prj-dropzone');
    const info = document.getElementById('prj-file-info');

    info.textContent = `Selected: ${file.name} (${(file.size / 1024).toFixed(0)} KB)`;
    dropzone.classList.add('has-file');

    // Upload and parse
    showStatus('Parsing PRJ file...', 'info');
    const formData = new FormData();
    formData.append('file', file);

    try {
        const resp = await fetch('/api/scra/parse-prj', {
            method: 'POST',
            body: formData,
        });
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || 'Parse failed');
        }
        prjData = await resp.json();
        showPrjSummary(prjData);
        populateStairsFromPrj(prjData);
        showStatus('PRJ file parsed successfully.', 'success');
    } catch (e) {
        showStatus(`Failed to parse PRJ: ${e.message}`, 'error');
    }
}

function showPrjSummary(data) {
    const div = document.getElementById('prj-data');
    const nLevels = data.n_levels || 0;
    const nStairs = (data.stairs || []).length;
    const labels = (data.floor_labels || {});
    const labelList = Object.values(labels).slice(0, 10).join(', ');

    div.innerHTML = `
        <table class="stair-table" style="width:auto;">
            <tr><td style="font-weight:600;text-align:left;">Levels</td><td>${nLevels}</td></tr>
            <tr><td style="font-weight:600;text-align:left;">Stairs Detected</td><td>${nStairs}</td></tr>
            <tr><td style="font-weight:600;text-align:left;">Elevator Shafts</td><td>${data.elevator_zones || 0}</td></tr>
            <tr><td style="font-weight:600;text-align:left;">Level Names</td>
                <td style="font-size:8pt;">${labelList}${nLevels > 10 ? '...' : ''}</td></tr>
        </table>
    `;
    document.getElementById('prj-summary').style.display = 'block';
}

// ---------------------------------------------------------------------------
// Stairs Table
// ---------------------------------------------------------------------------
function populateStairsFromPrj(data) {
    stairs = [];
    for (const s of (data.stairs || [])) {
        stairs.push({
            label: s.label,
            bottom: s.served_levels ? Math.min(...s.served_levels) : 1,
            top: s.served_levels ? Math.max(...s.served_levels) : 1,
            doorW: 1.1,
            doorH: 2.1,
            gap: 3.0,
            vestibule: s.has_vestibule,
        });
    }
    if (stairs.length === 0) addStair();
    else renderStairs();
}

function addStair() {
    stairs.push({
        label: `Stair ${stairs.length + 1}`,
        bottom: 1,
        top: parseInt(document.getElementById('total_stories')?.value) || 10,
        doorW: 1.1,
        doorH: 2.1,
        gap: 3.0,
        vestibule: true,
    });
    renderStairs();
}

function removeStair(idx) {
    stairs.splice(idx, 1);
    renderStairs();
}

function renderStairs() {
    const tbody = document.getElementById('stairs-body');
    tbody.innerHTML = '';
    stairs.forEach((s, i) => {
        tbody.innerHTML += `
        <tr>
            <td><input value="${s.label}" onchange="stairs[${i}].label=this.value"></td>
            <td><input type="number" value="${s.bottom}" onchange="stairs[${i}].bottom=+this.value" style="width:60px;"></td>
            <td><input type="number" value="${s.top}" onchange="stairs[${i}].top=+this.value" style="width:60px;"></td>
            <td><input type="number" value="${s.doorW}" step="0.1" onchange="stairs[${i}].doorW=+this.value"></td>
            <td><input type="number" value="${s.doorH}" step="0.1" onchange="stairs[${i}].doorH=+this.value"></td>
            <td><input type="number" value="${s.gap}" step="0.5" onchange="stairs[${i}].gap=+this.value"></td>
            <td><select onchange="stairs[${i}].vestibule=this.value==='true'">
                <option value="true" ${s.vestibule ? 'selected' : ''}>Yes</option>
                <option value="false" ${!s.vestibule ? 'selected' : ''}>No</option>
            </select></td>
            <td><button class="remove-btn" onclick="removeStair(${i})">X</button></td>
        </tr>`;
    });
}

// ---------------------------------------------------------------------------
// Summary (Step 5)
// ---------------------------------------------------------------------------
function buildSummary() {
    const name = document.getElementById('project_name').value;
    const addr = document.getElementById('project_address').value;
    const city = document.getElementById('project_city').value;
    const bldg = document.getElementById('building_name').value;
    const stories = document.getElementById('total_stories').value;
    const nStairs = stairs.length;
    const prjFile = prjData ? 'Loaded' : 'Not loaded';

    document.getElementById('generation-summary').innerHTML = `
        <table class="stair-table" style="width:auto;min-width:400px;">
            <tr><td style="font-weight:600;text-align:left;">Project</td><td style="text-align:left;">${name}</td></tr>
            <tr><td style="font-weight:600;text-align:left;">Address</td><td style="text-align:left;">${addr}, ${city}</td></tr>
            <tr><td style="font-weight:600;text-align:left;">Building</td><td style="text-align:left;">${bldg} (${stories} stories)</td></tr>
            <tr><td style="font-weight:600;text-align:left;">Stairs</td><td style="text-align:left;">${nStairs} stairwell(s)</td></tr>
            <tr><td style="font-weight:600;text-align:left;">PRJ Model</td><td style="text-align:left;">${prjFile}</td></tr>
        </table>
    `;
}

// ---------------------------------------------------------------------------
// Generate Report
// ---------------------------------------------------------------------------
async function generateReport() {
    const btn = document.getElementById('btn-generate');
    btn.disabled = true;
    btn.textContent = 'Generating...';

    const progressBar = document.getElementById('progress-bar');
    const progressFill = document.getElementById('progress-fill');
    progressBar.style.display = 'block';
    progressFill.style.width = '20%';

    showStatus('Running SCRA generation...', 'info');

    // Collect all form data
    const winterDb = parseFloat(document.getElementById('winter_db').value) || 44.4;
    const summerDb = parseFloat(document.getElementById('summer_db').value) || 83.7;
    const indoorTemp = parseFloat(document.getElementById('indoor_temp').value) || 68;

    const payload = {
        project: {
            project_name: document.getElementById('project_name').value,
            project_number: document.getElementById('project_number').value,
            project_address: document.getElementById('project_address').value,
            project_city: document.getElementById('project_city').value,
            project_state: document.getElementById('project_state').value,
            submittal_type: document.getElementById('submittal_type').value,
            report_date: document.getElementById('report_date').value,
            prepared_for_name: document.getElementById('client_name').value,
            prepared_for_address: document.getElementById('client_address').value,
            prepared_by_name: document.getElementById('firm_name').value,
            prepared_by_address: document.getElementById('firm_address').value,
            prepared_by_phone: document.getElementById('firm_phone').value,
        },
        building: {
            building_name: document.getElementById('building_name').value,
            building_abbreviation: document.getElementById('building_abbr').value,
            total_stories: parseInt(document.getElementById('total_stories').value) || 37,
            above_grade_parking: parseInt(document.getElementById('above_grade_parking').value) || 0,
            subterranean_levels: parseInt(document.getElementById('subterranean_levels').value) || 0,
            building_type: document.getElementById('building_type').value,
            is_sprinklered: document.getElementById('is_sprinklered').value === 'true',
            tenant_name: document.getElementById('tenant_name').value,
            scope_bottom_level: parseInt(document.getElementById('scope_bottom').value) || 1,
            scope_top_level: parseInt(document.getElementById('scope_top').value) || 10,
            base_scra_author: document.getElementById('base_scra_author').value,
            base_scra_date: document.getElementById('base_scra_date').value,
            base_scra_revision: document.getElementById('base_scra_revision').value,
        },
        climate: {
            weather_station: document.getElementById('weather_station').value,
            winter_design_db: winterDb,
            summer_design_db: summerDb,
            indoor_design_temp: indoorTemp,
            winter_design_db_C: (winterDb - 32) * 5 / 9,
            summer_design_db_C: (summerDb - 32) * 5 / 9,
            indoor_design_temp_C: (indoorTemp - 32) * 5 / 9,
        },
        stairs: stairs.map(s => ({
            label: s.label,
            serves_bottom_level: s.bottom,
            serves_top_level: s.top,
            door_width_m: s.doorW,
            door_height_m: s.doorH,
            door_gap_mm: s.gap,
            has_vestibule: s.vestibule,
        })),
        criteria: {
            min_dp_inwg: parseFloat(document.getElementById('min_dp').value) || 0.05,
            max_door_force_lbf: parseFloat(document.getElementById('max_force_stair').value) || 30,
            max_door_force_egress_lbf: parseFloat(document.getElementById('max_force_egress').value) || 15,
        },
        code_jurisdiction: document.getElementById('code_jurisdiction').value,
    };

    progressFill.style.width = '40%';

    try {
        const resp = await fetch('/api/scra/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });

        progressFill.style.width = '80%';

        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || 'Generation failed');
        }

        reportHtml = await resp.text();
        progressFill.style.width = '100%';

        // Display in iframe
        const frame = document.getElementById('report-frame');
        frame.srcdoc = reportHtml;
        document.getElementById('report-container').style.display = 'block';

        showStatus('SCRA report generated successfully!', 'success');
    } catch (e) {
        showStatus(`Generation failed: ${e.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Generate SCRA Report';
        setTimeout(() => { progressBar.style.display = 'none'; }, 2000);
    }
}

function openReportNewTab() {
    if (!reportHtml) return;
    const w = window.open('', '_blank');
    w.document.write(reportHtml);
    w.document.close();
}

function printReport() {
    const frame = document.getElementById('report-frame');
    if (frame.contentWindow) {
        frame.contentWindow.print();
    }
}

// ---------------------------------------------------------------------------
// Drag & Drop for PRJ
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
    const dz = document.getElementById('prj-dropzone');
    if (dz) {
        dz.addEventListener('dragover', e => { e.preventDefault(); dz.style.borderColor = '#1a3a6b'; });
        dz.addEventListener('dragleave', () => { dz.style.borderColor = '#ccc'; });
        dz.addEventListener('drop', e => {
            e.preventDefault();
            dz.style.borderColor = '#ccc';
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                document.getElementById('prj-file').files = files;
                handlePrjUpload(document.getElementById('prj-file'));
            }
        });
    }

    // Initialize with one default stair if empty
    if (stairs.length === 0) addStair();
});
