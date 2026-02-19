"""Standalone CONTAM PRJ File Viewer.

Drag-and-drop a .prj file to instantly parse and explore its contents.
No project setup required — just drop and go.

Usage:
    python prj_viewer.py
"""

import json
import os
import sys
import uuid
import webbrowser
from pathlib import Path
from typing import Dict, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse

# Ensure core module is importable
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from core.prj_parser import (
    ParsedModel,
    auto_detect_config,
    get_zone_display_name,
    parse_prj_file,
)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="CONTAM PRJ Viewer")

parsed_models: Dict[str, ParsedModel] = {}

# ---------------------------------------------------------------------------
# Embedded HTML
# ---------------------------------------------------------------------------
HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CONTAM PRJ Viewer</title>
<style>
:root {
    --bg: #f7f8fa;
    --surface: #ffffff;
    --accent: #2e86de;
    --accent-light: rgba(46,134,222,0.08);
    --success: #27ae60;
    --danger: #e74c3c;
    --warn: #f39c12;
    --text: #2c3e50;
    --text-secondary: #7f8c8d;
    --border: #dfe6e9;
    --border-light: #ecf0f1;
    --radius: 8px;
    --shadow: 0 2px 8px rgba(0,0,0,0.06);
}
* { margin:0; padding:0; box-sizing:border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
}

/* Header */
.header {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 1rem 2rem;
    display: flex;
    align-items: center;
    gap: 1rem;
    box-shadow: var(--shadow);
}
.header h1 { font-size: 1.2rem; font-weight: 700; color: var(--accent); }
.header .subtitle { font-size: 0.85rem; color: var(--text-secondary); }
.header .file-name {
    margin-left: auto;
    font-size: 0.85rem;
    color: var(--text-secondary);
    font-weight: 500;
}
.header .new-btn {
    margin-left: 0.5rem;
    padding: 0.4rem 1rem;
    background: var(--accent);
    color: #fff;
    border: none;
    border-radius: var(--radius);
    cursor: pointer;
    font-size: 0.8rem;
    font-weight: 500;
}
.header .new-btn:hover { opacity: 0.9; }

/* Landing */
.landing {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: calc(100vh - 60px);
    padding: 2rem;
}
.drop-zone {
    width: 100%;
    max-width: 600px;
    border: 3px dashed var(--border);
    border-radius: 20px;
    padding: 4rem 2rem;
    text-align: center;
    cursor: pointer;
    transition: all 0.3s ease;
    background: var(--surface);
}
.drop-zone:hover {
    border-color: var(--accent);
    background: var(--accent-light);
}
.drop-zone.drag-over {
    border-color: var(--accent);
    background: rgba(46,134,222,0.12);
    transform: scale(1.02);
    box-shadow: 0 0 40px rgba(46,134,222,0.15);
}
.drop-zone svg { color: var(--accent); opacity: 0.6; margin-bottom: 1.5rem; }
.drop-zone h2 { font-size: 1.6rem; margin-bottom: 0.5rem; }
.drop-zone p { color: var(--text-secondary); margin-bottom: 1.5rem; }
.drop-zone .hint { font-size: 0.8rem; color: var(--text-secondary); opacity: 0.6; }

/* Spinner */
.spinner-wrap {
    display: none;
    flex-direction: column;
    align-items: center;
    gap: 1rem;
    padding: 3rem;
}
.spinner {
    width: 48px; height: 48px;
    border: 5px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.spinner-wrap p { color: var(--text-secondary); font-weight: 500; }

/* Results layout */
.results { display: none; }
.results.visible { display: block; }

/* Summary bar */
.summary-bar {
    display: flex;
    gap: 0.75rem;
    padding: 1rem 2rem;
    background: var(--surface);
    border-bottom: 1px solid var(--border-light);
    flex-wrap: wrap;
}
.badge {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.35rem 0.85rem;
    background: var(--accent-light);
    color: var(--accent);
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 600;
}
.badge.green { background: rgba(39,174,96,0.1); color: var(--success); }

/* Config banner */
.config-banner {
    margin: 1rem 2rem;
    padding: 1rem 1.25rem;
    background: rgba(39,174,96,0.06);
    border: 1px solid rgba(39,174,96,0.3);
    border-radius: var(--radius);
    font-size: 0.85rem;
    line-height: 1.6;
}
.config-banner h3 { color: var(--success); margin-bottom: 0.5rem; font-size: 0.95rem; }
.config-banner ul { padding-left: 1.25rem; margin: 0.5rem 0; }
.config-banner li { margin-bottom: 0.2rem; }

/* Tabs */
.tab-bar {
    display: flex;
    gap: 0;
    padding: 0 2rem;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
}
.tab-btn {
    padding: 0.7rem 1.25rem;
    border: none;
    background: none;
    font-size: 0.85rem;
    font-weight: 500;
    color: var(--text-secondary);
    cursor: pointer;
    border-bottom: 2px solid transparent;
    transition: all 0.2s;
}
.tab-btn:hover { color: var(--text); }
.tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); }

/* Data panels */
.data-panel { display: none; padding: 1rem 2rem 2rem; }
.data-panel.active { display: block; }

/* Filters */
.filter-row {
    display: flex;
    gap: 0.75rem;
    align-items: center;
    margin-bottom: 0.75rem;
    flex-wrap: wrap;
}
.filter-row label { font-size: 0.8rem; color: var(--text-secondary); font-weight: 500; }
.filter-row select, .filter-row input[type="text"] {
    padding: 0.4rem 0.6rem;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    font-size: 0.8rem;
    background: var(--surface);
}
.filter-row input[type="text"] { min-width: 180px; }

/* Tables */
.table-wrap {
    overflow-x: auto;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
}
table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.8rem;
}
th {
    background: #f8f9fa;
    font-weight: 600;
    text-align: left;
    padding: 0.6rem 0.75rem;
    border-bottom: 2px solid var(--border);
    position: sticky;
    top: 0;
    white-space: nowrap;
}
td {
    padding: 0.45rem 0.75rem;
    border-bottom: 1px solid var(--border-light);
    white-space: nowrap;
}
tr:hover td { background: var(--accent-light); }

/* Stair/corridor cards */
.config-cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 1rem;
}
.config-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
}
.config-card .card-header {
    padding: 0.7rem 1rem;
    background: #f8f9fa;
    border-bottom: 1px solid var(--border-light);
    font-weight: 600;
    font-size: 0.9rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.config-card .card-header .tag {
    font-size: 0.7rem;
    padding: 0.15rem 0.5rem;
    border-radius: 10px;
    font-weight: 500;
}
.tag-stair { background: rgba(46,134,222,0.1); color: var(--accent); }
.tag-corridor { background: rgba(243,156,18,0.1); color: var(--warn); }
.tag-floor { background: rgba(155,89,182,0.1); color: #8e44ad; }
.config-card .card-body { padding: 0.75rem 1rem; font-size: 0.8rem; }
.config-card .card-body .detail { margin-bottom: 0.3rem; color: var(--text-secondary); }
.config-card .card-body .detail strong { color: var(--text); }
.config-card .card-body .zone-count {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.2rem 0.5rem;
    background: var(--accent-light);
    border-radius: 10px;
    font-size: 0.75rem;
    color: var(--accent);
    font-weight: 500;
}

/* Scrollable table container */
.table-scroll { max-height: 70vh; overflow-y: auto; }

/* Responsive */
@media (max-width: 768px) {
    .header { padding: 0.75rem 1rem; }
    .summary-bar { padding: 0.75rem 1rem; }
    .tab-bar { padding: 0 1rem; overflow-x: auto; }
    .data-panel { padding: 0.75rem 1rem 1.5rem; }
    .config-banner { margin: 0.75rem 1rem; }
}
</style>
</head>
<body>

<!-- Header -->
<div class="header">
    <h1>CONTAM PRJ Viewer</h1>
    <span class="subtitle">Drop a file to explore</span>
    <span class="file-name" id="file-name"></span>
    <button class="new-btn" id="new-file-btn" style="display:none" onclick="resetView()">New File</button>
</div>

<!-- Landing / Drop Zone -->
<div class="landing" id="landing">
    <div class="drop-zone" id="drop-zone">
        <svg width="72" height="72" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
            <polyline points="14 2 14 8 20 8"></polyline>
            <line x1="12" y1="18" x2="12" y2="12"></line>
            <line x1="9" y1="15" x2="12" y2="12"></line>
            <line x1="15" y1="15" x2="12" y2="12"></line>
        </svg>
        <h2>Drop your .prj file here</h2>
        <p>or click to browse</p>
        <div class="hint">CONTAM project files (.prj) are instantly parsed and displayed</div>
    </div>
    <input type="file" id="file-input" accept=".prj" style="display:none">
    <div class="spinner-wrap" id="spinner">
        <div class="spinner"></div>
        <p id="spinner-text">Parsing...</p>
    </div>
</div>

<!-- Results -->
<div class="results" id="results">
    <!-- Summary badges -->
    <div class="summary-bar" id="summary-bar"></div>

    <!-- Auto-config banner -->
    <div class="config-banner" id="config-banner" style="display:none"></div>

    <!-- Tabs -->
    <div class="tab-bar" id="tab-bar">
        <button class="tab-btn active" data-tab="overview">Overview</button>
        <button class="tab-btn" data-tab="levels">Levels</button>
        <button class="tab-btn" data-tab="zones">Zones</button>
        <button class="tab-btn" data-tab="ahs">AHS</button>
        <button class="tab-btn" data-tab="elements">Elements</button>
        <button class="tab-btn" data-tab="paths">Paths</button>
    </div>

    <!-- Overview -->
    <div class="data-panel active" id="panel-overview">
        <div class="config-cards" id="config-cards"></div>
    </div>

    <!-- Levels -->
    <div class="data-panel" id="panel-levels">
        <div class="table-wrap"><div class="table-scroll">
            <table><thead><tr><th>Index</th><th>Name</th><th>Ref Height (m)</th><th>Delta Height (m)</th><th>Icons</th></tr></thead>
            <tbody id="tbl-levels"></tbody></table>
        </div></div>
    </div>

    <!-- Zones -->
    <div class="data-panel" id="panel-zones">
        <div class="filter-row">
            <label>Level:</label>
            <select id="zone-level-filter"><option value="">All</option></select>
            <label>Search:</label>
            <input type="text" id="zone-search" placeholder="Filter zones...">
        </div>
        <div class="table-wrap"><div class="table-scroll">
            <table><thead><tr><th>ID</th><th>Name</th><th>Level</th><th>Level Name</th><th>Volume (m3)</th><th>Temp (K)</th></tr></thead>
            <tbody id="tbl-zones"></tbody></table>
        </div></div>
    </div>

    <!-- AHS -->
    <div class="data-panel" id="panel-ahs">
        <div class="table-wrap"><div class="table-scroll">
            <table><thead><tr><th>ID</th><th>Name</th><th>Return Zone</th><th>Supply Zone</th><th>Return Path</th><th>Supply Path</th><th>Exhaust Path</th></tr></thead>
            <tbody id="tbl-ahs"></tbody></table>
        </div></div>
    </div>

    <!-- Elements -->
    <div class="data-panel" id="panel-elements">
        <div class="filter-row">
            <label>Search:</label>
            <input type="text" id="elem-search" placeholder="Filter elements...">
        </div>
        <div class="table-wrap"><div class="table-scroll">
            <table><thead><tr><th>ID</th><th>Name</th><th>Type</th></tr></thead>
            <tbody id="tbl-elements"></tbody></table>
        </div></div>
    </div>

    <!-- Paths -->
    <div class="data-panel" id="panel-paths">
        <div class="filter-row">
            <label>Level:</label>
            <select id="path-level-filter"><option value="">All</option></select>
            <label>Element:</label>
            <select id="path-elem-filter"><option value="">All</option></select>
        </div>
        <div class="table-wrap"><div class="table-scroll">
            <table><thead><tr><th>ID</th><th>From</th><th>To</th><th>Element</th><th>AHS</th><th>Level</th><th>Icon</th><th>Dir</th></tr></thead>
            <tbody id="tbl-paths"></tbody></table>
        </div></div>
    </div>
</div>

<script>
const V = (() => {
    let data = null;
    let allZones = [], allElements = [], allPaths = [];

    // -----------------------------------------------------------------------
    // Init
    // -----------------------------------------------------------------------
    function init() {
        const dz = document.getElementById('drop-zone');
        const fi = document.getElementById('file-input');

        dz.addEventListener('click', () => fi.click());
        fi.addEventListener('change', () => { if (fi.files.length) upload(fi.files[0]); });

        dz.addEventListener('dragenter', e => { e.preventDefault(); dz.classList.add('drag-over'); });
        dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('drag-over'); });
        dz.addEventListener('dragleave', e => { e.preventDefault(); dz.classList.remove('drag-over'); });
        dz.addEventListener('drop', e => {
            e.preventDefault(); dz.classList.remove('drag-over');
            const f = e.dataTransfer.files;
            if (f.length && f[0].name.toLowerCase().endsWith('.prj')) upload(f[0]);
            else if (f.length) alert('Please drop a .prj file.');
        });

        // Page-level drop
        document.body.addEventListener('dragover', e => {
            e.preventDefault();
            if (document.getElementById('landing').style.display !== 'none') dz.classList.add('drag-over');
        });
        document.body.addEventListener('drop', e => {
            e.preventDefault(); dz.classList.remove('drag-over');
            const f = e.dataTransfer.files;
            if (f.length && f[0].name.toLowerCase().endsWith('.prj') && document.getElementById('landing').style.display !== 'none')
                upload(f[0]);
        });

        // Tab switching
        document.getElementById('tab-bar').addEventListener('click', e => {
            const btn = e.target.closest('.tab-btn');
            if (!btn) return;
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.data-panel').forEach(p => p.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById('panel-' + btn.dataset.tab).classList.add('active');
        });

        // Filters
        document.getElementById('zone-level-filter').addEventListener('change', filterZones);
        document.getElementById('zone-search').addEventListener('input', filterZones);
        document.getElementById('elem-search').addEventListener('input', filterElements);
        document.getElementById('path-level-filter').addEventListener('change', filterPaths);
        document.getElementById('path-elem-filter').addEventListener('change', filterPaths);
    }

    // -----------------------------------------------------------------------
    // Upload
    // -----------------------------------------------------------------------
    async function upload(file) {
        const dz = document.getElementById('drop-zone');
        const sp = document.getElementById('spinner');
        const st = document.getElementById('spinner-text');

        dz.style.display = 'none';
        sp.style.display = 'flex';
        st.textContent = 'Uploading ' + file.name + '...';

        try {
            const fd = new FormData();
            fd.append('file', file);
            st.textContent = 'Parsing ' + file.name + '...';

            const resp = await fetch('/api/parse', { method: 'POST', body: fd });
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({ detail: resp.statusText }));
                throw new Error(err.detail || resp.statusText);
            }

            data = await resp.json();
            st.textContent = 'Rendering...';
            render(data, file.name);

        } catch (e) {
            dz.style.display = '';
            sp.style.display = 'none';
            alert('Error: ' + e.message);
        }
    }

    // -----------------------------------------------------------------------
    // Render
    // -----------------------------------------------------------------------
    function render(d, fileName) {
        allZones = d.zones;
        allElements = d.elements;
        allPaths = d.paths;

        // Header
        document.getElementById('file-name').textContent = fileName;
        document.getElementById('new-file-btn').style.display = '';

        // Summary badges
        const sb = document.getElementById('summary-bar');
        const ac = d.auto_config;
        const conf = ac ? ac.confidence : '';
        const confBadge = conf === 'high' ? '<span class="badge green">High Confidence</span>'
            : conf === 'medium' ? '<span class="badge">Medium Confidence</span>' : '';
        sb.innerHTML = [
            `<span class="badge">Levels: ${d.num_levels}</span>`,
            `<span class="badge">Zones: ${d.num_zones}</span>`,
            `<span class="badge">Elements: ${d.num_flow_elements}</span>`,
            `<span class="badge">Paths: ${d.num_airflow_paths}</span>`,
            `<span class="badge">AHS: ${d.num_ahs}</span>`,
            ac ? `<span class="badge green">Stairs: ${ac.summary.stairs_detected}</span>` : '',
            ac ? `<span class="badge green">Corridors: ${ac.summary.corridors_detected}</span>` : '',
            confBadge,
        ].filter(Boolean).join('');

        // Auto-config banner
        if (ac && ac.confidence !== 'low') {
            const banner = document.getElementById('config-banner');
            const details = (ac.detection_details || []).map(d => `<li>${d}</li>`).join('');
            const vestCount = ac.summary.vestibules_detected || 0;
            banner.innerHTML = `
                <h3>Auto-Detected Configuration</h3>
                <ul>${details}
                    ${vestCount > 0 ? `<li>Vestibule zones detected: ${vestCount}</li>` : ''}
                    ${ac.supply_ahs ? `<li>Supply AHS: ${ac.supply_ahs.name} (#${ac.supply_ahs.id})</li>` : ''}
                    ${ac.return_ahs ? `<li>Return AHS: ${ac.return_ahs.name} (#${ac.return_ahs.id})</li>` : ''}
                    ${ac.corridor_path_element ? `<li>Corridor path element: ${ac.corridor_path_element}</li>` : ''}
                </ul>`;
            banner.style.display = '';
        }

        // Overview cards
        renderOverview(d, ac);

        // Tables
        document.getElementById('tbl-levels').innerHTML = d.levels.map(l =>
            `<tr><td>${l.index}</td><td>${l.name}</td><td>${l.ref_height.toFixed(3)}</td><td>${l.delta_height.toFixed(3)}</td><td>${l.num_icons}</td></tr>`
        ).join('');

        renderZonesTable(d.zones);
        populateSelect('zone-level-filter', [...new Set(d.zones.map(z => z.level_num))].sort((a,b) => a-b), d.zones);

        document.getElementById('tbl-ahs').innerHTML = d.ahs.map(a =>
            `<tr><td>${a.id}</td><td>${a.name}</td><td>${a.return_zone}</td><td>${a.supply_zone}</td><td>${a.return_path}</td><td>${a.supply_path}</td><td>${a.exhaust_path}</td></tr>`
        ).join('');

        renderElementsTable(d.elements);
        renderPathsTable(d.paths);

        const plf = document.getElementById('path-level-filter');
        plf.innerHTML = '<option value="">All</option>';
        [...new Set(d.paths.map(p => p.level_num))].sort((a,b) => a-b).forEach(l => {
            plf.innerHTML += `<option value="${l}">${l}</option>`;
        });
        const pef = document.getElementById('path-elem-filter');
        pef.innerHTML = '<option value="">All</option>';
        [...new Set(d.paths.map(p => p.flow_elem_name))].sort().forEach(n => {
            pef.innerHTML += `<option value="${n}">${n}</option>`;
        });

        // Show results
        document.getElementById('landing').style.display = 'none';
        document.getElementById('results').classList.add('visible');
    }

    function renderOverview(d, ac) {
        const cards = document.getElementById('config-cards');
        let html = '';

        if (ac && ac.stairs) {
            for (const s of ac.stairs) {
                const paths = s.paths || {};
                const pathList = Object.entries(paths).filter(([,v]) => v).map(([k,v]) => `${k}: ${v}`).join(', ');
                html += `<div class="config-card">
                    <div class="card-header">
                        ${s.label}
                        <span class="tag tag-stair">Stair</span>
                        <span class="zone-count">${s.zones.length} levels</span>
                    </div>
                    <div class="card-body">
                        <div class="detail"><strong>Zone name:</strong> ${s.zone_name}</div>
                        ${s.vestibules && s.vestibules.length ? `<div class="detail"><strong>Vestibules:</strong> ${s.vestibules.length} detected</div>` : ''}
                        ${pathList ? `<div class="detail"><strong>Paths:</strong> ${pathList}</div>` : ''}
                        ${s.ahs_id ? `<div class="detail"><strong>AHS:</strong> #${s.ahs_id}</div>` : ''}
                    </div>
                </div>`;
            }
        }

        if (ac && ac.corridors) {
            for (const c of ac.corridors) {
                html += `<div class="config-card">
                    <div class="card-header">
                        ${c.label}
                        <span class="tag tag-corridor">Corridor</span>
                        <span class="zone-count">${c.zones.length} levels</span>
                    </div>
                    <div class="card-body">
                        <div class="detail"><strong>Zone name:</strong> ${c.zone_name}</div>
                        ${c.path_name ? `<div class="detail"><strong>Path element:</strong> ${c.path_name}</div>` : ''}
                        ${c.ahs_id ? `<div class="detail"><strong>AHS:</strong> #${c.ahs_id}</div>` : ''}
                    </div>
                </div>`;
            }
        }

        if (ac && ac.floor_zones) {
            for (const f of ac.floor_zones) {
                html += `<div class="config-card">
                    <div class="card-header">
                        ${f.label}
                        <span class="tag tag-floor">Floor Zone</span>
                        <span class="zone-count">${f.zones.length} levels</span>
                    </div>
                    <div class="card-body">
                        <div class="detail"><strong>Zone name:</strong> ${f.zone_name}</div>
                    </div>
                </div>`;
            }
        }

        if (!html) {
            html = `<p style="color:var(--text-secondary);padding:1rem;">No stairs, corridors, or floor zones detected. Browse the raw data using the tabs above.</p>`;
        }

        cards.innerHTML = html;
    }

    // -----------------------------------------------------------------------
    // Tables
    // -----------------------------------------------------------------------
    function renderZonesTable(zones) {
        document.getElementById('tbl-zones').innerHTML = zones.map(z =>
            `<tr><td>${z.id}</td><td>${z.name}</td><td>${z.level_num}</td><td>${z.level_name}</td><td>${z.volume.toFixed(3)}</td><td>${z.temperature.toFixed(1)}</td></tr>`
        ).join('');
    }
    function renderElementsTable(elems) {
        document.getElementById('tbl-elements').innerHTML = elems.map(e =>
            `<tr><td>${e.id}</td><td>${e.name}</td><td>${e.type}</td></tr>`
        ).join('');
    }
    function renderPathsTable(paths) {
        const display = paths.slice(0, 500);
        let html = display.map(p =>
            `<tr><td>${p.id}</td><td>${p.from_zone}</td><td>${p.to_zone}</td><td>${p.flow_elem_name}</td><td>${p.ahs}</td><td>${p.level_num}</td><td>${p.icon_type}</td><td>${p.direction}</td></tr>`
        ).join('');
        if (paths.length > 500)
            html += `<tr><td colspan="8" style="text-align:center;color:var(--text-secondary);">Showing 500 of ${paths.length}. Use filters.</td></tr>`;
        document.getElementById('tbl-paths').innerHTML = html;
    }

    function populateSelect(id, values, zones) {
        const sel = document.getElementById(id);
        sel.innerHTML = '<option value="">All</option>';
        values.forEach(v => {
            const name = zones ? (zones.find(z => z.level_num === v)?.level_name || v) : v;
            sel.innerHTML += `<option value="${v}">${name} (${v})</option>`;
        });
    }

    // -----------------------------------------------------------------------
    // Filters
    // -----------------------------------------------------------------------
    function filterZones() {
        const level = document.getElementById('zone-level-filter').value;
        const search = document.getElementById('zone-search').value.toLowerCase();
        let filtered = allZones;
        if (level) filtered = filtered.filter(z => z.level_num == level);
        if (search) filtered = filtered.filter(z => z.name.toLowerCase().includes(search));
        renderZonesTable(filtered);
    }
    function filterElements() {
        const search = document.getElementById('elem-search').value.toLowerCase();
        renderElementsTable(allElements.filter(e => e.name.toLowerCase().includes(search) || e.type.toLowerCase().includes(search)));
    }
    function filterPaths() {
        const level = document.getElementById('path-level-filter').value;
        const elem = document.getElementById('path-elem-filter').value;
        let filtered = allPaths;
        if (level) filtered = filtered.filter(p => p.level_num == level);
        if (elem) filtered = filtered.filter(p => p.flow_elem_name === elem);
        renderPathsTable(filtered);
    }

    document.addEventListener('DOMContentLoaded', init);
    return {};
})();

function resetView() {
    document.getElementById('landing').style.display = '';
    document.getElementById('drop-zone').style.display = '';
    document.getElementById('spinner').style.display = 'none';
    document.getElementById('results').classList.remove('visible');
    document.getElementById('file-name').textContent = '';
    document.getElementById('new-file-btn').style.display = 'none';
    document.getElementById('config-banner').style.display = 'none';
    document.getElementById('file-input').value = '';
}
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(content=HTML_PAGE)


@app.post("/api/parse")
async def parse_upload(file: UploadFile = File(...)):
    """Accept a .prj file, parse it, auto-detect config, return everything."""
    if not file.filename or not file.filename.lower().endswith(".prj"):
        raise HTTPException(400, "Please upload a .prj file")

    # Save to temp location
    tmp_dir = BASE_DIR / "tmp_uploads"
    tmp_dir.mkdir(exist_ok=True)
    dest = tmp_dir / file.filename
    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)

    try:
        model = parse_prj_file(str(dest))
    except Exception as e:
        raise HTTPException(422, f"Failed to parse PRJ file: {e}")

    model_id = str(uuid.uuid4())[:8]
    parsed_models[model_id] = model

    # Auto-detect configuration
    try:
        auto_config = auto_detect_config(model)
    except Exception:
        auto_config = None

    # Build response
    levels_data = [
        {"index": lvl.index, "name": lvl.name, "ref_height": lvl.ref_height,
         "delta_height": lvl.delta_height, "num_icons": lvl.num_icons}
        for lvl in model.levels
    ]
    zones_data = [
        {"id": z.id, "name": z.name, "display_name": get_zone_display_name(z),
         "level_num": z.level_num, "level_name": z.level_name,
         "volume": z.volume, "temperature": z.temperature}
        for z in model.zones
    ]
    elements_data = [
        {"id": elem.id, "name": elem.name, "type": elem.elem_type}
        for elem in model.flow_elements
    ]
    paths_data = [
        {"id": p.id, "from_zone": p.from_zone, "to_zone": p.to_zone,
         "flow_elem_id": p.flow_elem_id, "flow_elem_name": p.flow_elem_name,
         "ahs": p.ahs, "level_num": p.level_num, "multiplier": p.multiplier,
         "icon_type": p.icon_type, "direction": p.direction}
        for p in model.airflow_paths
    ]
    ahs_data = [
        {"id": ahs.id, "name": ahs.name, "return_zone": ahs.return_zone,
         "supply_zone": ahs.supply_zone, "return_path": ahs.return_path,
         "supply_path": ahs.supply_path, "exhaust_path": ahs.exhaust_path}
        for ahs in model.ahs_systems
    ]

    return {
        "model_id": model_id,
        "filepath": str(dest),
        "version": model.version,
        "project_name": model.project_name,
        "num_levels": len(model.levels),
        "num_zones": len(model.zones),
        "num_flow_elements": len(model.flow_elements),
        "num_airflow_paths": len(model.airflow_paths),
        "num_ahs": len(model.ahs_systems),
        "levels": levels_data,
        "zones": zones_data,
        "elements": elements_data,
        "paths": paths_data,
        "ahs": ahs_data,
        "auto_config": auto_config,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    port = int(os.environ.get("PORT", 5050))
    print(f"\n  CONTAM PRJ Viewer running at http://localhost:{port}\n")

    if not os.environ.get("NO_BROWSER"):
        import threading
        def open_browser():
            import time
            time.sleep(1.2)
            webbrowser.open(f"http://localhost:{port}")
        threading.Thread(target=open_browser, daemon=True).start()

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
