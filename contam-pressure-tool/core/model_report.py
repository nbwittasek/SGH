"""Generate a beautiful, print-optimized HTML report for a parsed CONTAM model.

Used by both the standalone PRJ Viewer and the main Pressurization Tool.
"""

import datetime
from pathlib import Path
from typing import Dict, Optional


def _esc(text) -> str:
    """Escape HTML entities."""
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def generate_model_report_html(model, auto_config: Optional[dict] = None) -> str:
    """Generate a complete HTML report for a ParsedModel.

    Args:
        model: A ParsedModel instance from core.prj_parser.
        auto_config: Optional auto_detect_config() result dict.

    Returns:
        A complete HTML string suitable for rendering in a browser.
    """
    filename = Path(model.filepath).name if model.filepath else "Unknown"
    project_name = model.project_name or filename
    version = model.version or "Unknown"
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    n_levels = len(model.levels)
    n_zones = len(model.zones)
    n_elements = len(model.flow_elements)
    n_paths = len(model.airflow_paths)
    n_ahs = len(model.ahs_systems)

    # Build table rows
    levels_rows = ""
    for lvl in model.levels:
        levels_rows += (
            f"<tr><td>{lvl.index}</td><td>{_esc(lvl.name)}</td>"
            f"<td>{lvl.ref_height:.3f}</td><td>{lvl.delta_height:.3f}</td>"
            f"<td>{lvl.num_icons}</td></tr>\n"
        )

    zones_rows = ""
    for z in sorted(model.zones, key=lambda x: (x.level_num, x.id)):
        zones_rows += (
            f"<tr><td>{z.id}</td><td>{_esc(z.name)}</td>"
            f"<td>{z.level_num}</td><td>{_esc(z.level_name)}</td>"
            f"<td>{z.volume:.1f}</td><td>{z.temperature:.1f}</td></tr>\n"
        )

    ahs_rows = ""
    for a in model.ahs_systems:
        ahs_rows += (
            f"<tr><td>{a.id}</td><td>{_esc(a.name)}</td>"
            f"<td>{a.return_zone}</td><td>{a.supply_zone}</td>"
            f"<td>{a.return_path}</td><td>{a.supply_path}</td>"
            f"<td>{a.exhaust_path}</td></tr>\n"
        )

    elements_rows = ""
    for e in model.flow_elements:
        elements_rows += (
            f"<tr><td>{e.id}</td><td>{_esc(e.name)}</td>"
            f"<td>{_esc(e.elem_type)}</td></tr>\n"
        )

    # Top flow elements by frequency
    elem_freq: Dict[str, int] = {}
    for p in model.airflow_paths:
        elem_freq[p.flow_elem_name] = elem_freq.get(p.flow_elem_name, 0) + 1
    top_paths_rows = ""
    for name, count in sorted(elem_freq.items(), key=lambda x: -x[1])[:20]:
        top_paths_rows += f"<tr><td>{_esc(name)}</td><td>{count}</td></tr>\n"

    # Auto-config section
    config_html = _build_config_section(auto_config)

    return _REPORT_TEMPLATE.format(
        project_name=_esc(project_name),
        filename=_esc(filename),
        version=_esc(version),
        now_str=now_str,
        n_levels=n_levels,
        n_zones=n_zones,
        n_elements=n_elements,
        n_paths=n_paths,
        n_ahs=n_ahs,
        config_html=config_html,
        levels_rows=levels_rows,
        zones_rows=zones_rows,
        ahs_rows=ahs_rows,
        elements_rows=elements_rows,
        top_paths_rows=top_paths_rows,
    )


def _build_config_section(ac: Optional[dict]) -> str:
    """Build the auto-detected configuration section of the report."""
    if not ac or ac.get("confidence", "low") == "low":
        return ""

    conf_label = "High" if ac["confidence"] == "high" else "Medium"
    details_html = "".join(
        f"<li>{_esc(d)}</li>" for d in ac.get("detection_details", [])
    )
    vest_count = ac.get("summary", {}).get("vestibules_detected", 0)

    # Stair cards
    stair_cards = ""
    for s in ac.get("stairs", []):
        zone_count = len(s.get("zones", []))
        paths = s.get("paths", {})
        path_items = "".join(
            f"<li><strong>{k}:</strong> {v}</li>"
            for k, v in paths.items() if v
        )
        vest_info = ""
        if s.get("vestibules"):
            vest_info = (
                f'<div class="detail"><strong>Vestibules:</strong> '
                f'{len(s["vestibules"])} detected</div>'
            )
        stair_cards += f"""
        <div class="config-card stair">
            <div class="card-title">{_esc(s["label"])}
                <span class="tag tag-stair">Stair</span></div>
            <div class="card-info">
                <div class="detail"><strong>Zone name:</strong> {_esc(s["zone_name"])}</div>
                <div class="detail"><strong>Levels:</strong> {zone_count}</div>
                {vest_info}
                {f'<div class="detail"><strong>AHS:</strong> #{s["ahs_id"]}</div>' if s.get("ahs_id") else ""}
                {f'<ul class="path-list">{path_items}</ul>' if path_items else ""}
            </div>
        </div>"""

    # Corridor cards
    corridor_cards = ""
    for c in ac.get("corridors", []):
        zone_count = len(c.get("zones", []))
        corridor_cards += f"""
        <div class="config-card corridor">
            <div class="card-title">{_esc(c["label"])}
                <span class="tag tag-corridor">Corridor</span></div>
            <div class="card-info">
                <div class="detail"><strong>Zone name:</strong> {_esc(c["zone_name"])}</div>
                <div class="detail"><strong>Levels:</strong> {zone_count}</div>
                {f'<div class="detail"><strong>Path element:</strong> {_esc(c["path_name"])}</div>' if c.get("path_name") else ""}
                {f'<div class="detail"><strong>AHS:</strong> #{c["ahs_id"]}</div>' if c.get("ahs_id") else ""}
            </div>
        </div>"""

    # Floor zone cards
    floor_cards = ""
    for fz in ac.get("floor_zones", []):
        zone_count = len(fz.get("zones", []))
        floor_cards += f"""
        <div class="config-card floor">
            <div class="card-title">{_esc(fz["label"])}
                <span class="tag tag-floor">Floor Zone</span></div>
            <div class="card-info">
                <div class="detail"><strong>Zone name:</strong> {_esc(fz["zone_name"])}</div>
                <div class="detail"><strong>Levels:</strong> {zone_count}</div>
            </div>
        </div>"""

    supply_info = (
        f'{ac["supply_ahs"]["name"]} (#{ac["supply_ahs"]["id"]})'
        if ac.get("supply_ahs") else "Not detected"
    )
    return_info = (
        f'{ac["return_ahs"]["name"]} (#{ac["return_ahs"]["id"]})'
        if ac.get("return_ahs") else "Not detected"
    )

    return f"""
    <section class="report-section">
        <h2>Auto-Detected Configuration</h2>
        <div class="confidence-badge conf-{ac['confidence']}">{conf_label} Confidence</div>
        <ul class="detection-list">{details_html}
            {f'<li>Vestibule zones detected: {vest_count}</li>' if vest_count > 0 else ''}
            <li>Supply AHS: {_esc(supply_info)}</li>
            <li>Return AHS: {_esc(return_info)}</li>
            {f'<li>Corridor path element: {_esc(ac["corridor_path_element"])}</li>' if ac.get("corridor_path_element") else ''}
        </ul>
        <div class="card-grid">
            {stair_cards}
            {corridor_cards}
            {floor_cards}
        </div>
    </section>"""


# ---------------------------------------------------------------------------
# Full HTML template
# ---------------------------------------------------------------------------
_REPORT_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Model Report — {project_name}</title>
<style>
@page {{
    size: landscape;
    margin: 0.5in;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 11px;
    color: #2c3e50;
    line-height: 1.5;
    background: #fff;
    padding: 24px 32px;
}}

/* Header */
.report-header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    border-bottom: 3px solid #2e86de;
    padding-bottom: 12px;
    margin-bottom: 20px;
}}
.report-header h1 {{ font-size: 20px; color: #2e86de; font-weight: 700; }}
.report-header .subtitle {{ font-size: 12px; color: #7f8c8d; margin-top: 2px; }}
.report-header .meta {{ text-align: right; font-size: 10px; color: #7f8c8d; }}
.report-header .meta strong {{ color: #2c3e50; }}

/* Print button */
.print-btn {{
    display: inline-block;
    padding: 8px 20px;
    background: #2e86de;
    color: #fff;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 500;
    margin-bottom: 16px;
}}
.print-btn:hover {{ background: #1b6fbf; }}

/* Summary cards */
.summary-row {{
    display: flex;
    gap: 10px;
    margin-bottom: 20px;
    flex-wrap: wrap;
}}
.summary-card {{
    flex: 1;
    min-width: 100px;
    background: #f8f9fa;
    border: 1px solid #e9ecef;
    border-radius: 8px;
    padding: 12px 16px;
    text-align: center;
}}
.summary-card .num {{ font-size: 24px; font-weight: 700; color: #2e86de; }}
.summary-card .label {{ font-size: 10px; color: #7f8c8d; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600; }}

/* Sections */
.report-section {{
    margin-bottom: 24px;
    page-break-inside: avoid;
}}
.report-section h2 {{
    font-size: 14px;
    font-weight: 700;
    color: #2e86de;
    border-bottom: 1px solid #e9ecef;
    padding-bottom: 4px;
    margin-bottom: 10px;
}}

/* Tables */
table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 10px;
    margin-bottom: 8px;
}}
th {{
    background: #2e86de;
    color: #fff;
    padding: 6px 8px;
    text-align: left;
    font-weight: 600;
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.3px;
}}
td {{
    padding: 5px 8px;
    border-bottom: 1px solid #e9ecef;
}}
tr:nth-child(even) td {{ background: #f8f9fa; }}
tr:hover td {{ background: rgba(46,134,222,0.06); }}

/* Confidence badge */
.confidence-badge {{
    display: inline-block;
    padding: 3px 12px;
    border-radius: 12px;
    font-size: 10px;
    font-weight: 600;
    margin-bottom: 8px;
}}
.conf-high {{ background: rgba(39,174,96,0.12); color: #27ae60; }}
.conf-medium {{ background: rgba(243,156,18,0.12); color: #f39c12; }}

/* Detection list */
.detection-list {{
    padding-left: 18px;
    font-size: 10px;
    margin-bottom: 12px;
    color: #555;
}}
.detection-list li {{ margin-bottom: 2px; }}

/* Config cards */
.card-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 10px;
    margin-top: 8px;
}}
.config-card {{
    border: 1px solid #e9ecef;
    border-radius: 8px;
    overflow: hidden;
    page-break-inside: avoid;
}}
.config-card.stair {{ border-left: 3px solid #2e86de; }}
.config-card.corridor {{ border-left: 3px solid #f39c12; }}
.config-card.floor {{ border-left: 3px solid #8e44ad; }}
.card-title {{
    padding: 6px 10px;
    background: #f8f9fa;
    font-weight: 600;
    font-size: 11px;
    border-bottom: 1px solid #e9ecef;
    display: flex;
    align-items: center;
    gap: 6px;
}}
.tag {{
    font-size: 8px;
    padding: 1px 6px;
    border-radius: 8px;
    font-weight: 500;
}}
.tag-stair {{ background: rgba(46,134,222,0.1); color: #2e86de; }}
.tag-corridor {{ background: rgba(243,156,18,0.1); color: #f39c12; }}
.tag-floor {{ background: rgba(142,68,173,0.1); color: #8e44ad; }}
.card-info {{ padding: 8px 10px; font-size: 10px; }}
.card-info .detail {{ margin-bottom: 2px; color: #555; }}
.card-info .detail strong {{ color: #2c3e50; }}
.path-list {{ padding-left: 16px; margin-top: 4px; font-size: 9px; }}
.path-list li {{ margin-bottom: 1px; }}

/* Two-column layout */
.two-col {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
}}

/* Footer */
.report-footer {{
    margin-top: 24px;
    padding-top: 8px;
    border-top: 1px solid #e9ecef;
    font-size: 9px;
    color: #95a5a6;
    display: flex;
    justify-content: space-between;
}}

/* Print styles */
@media print {{
    .print-btn {{ display: none; }}
    body {{ padding: 0; }}
    .report-section {{ page-break-inside: avoid; }}
}}
</style>
</head>
<body>

<button class="print-btn" onclick="window.print()">Print / Save as PDF</button>

<div class="report-header">
    <div>
        <h1>CONTAM Model Report</h1>
        <div class="subtitle">{project_name}</div>
    </div>
    <div class="meta">
        <div><strong>File:</strong> {filename}</div>
        <div><strong>CONTAM Version:</strong> {version}</div>
        <div><strong>Generated:</strong> {now_str}</div>
    </div>
</div>

<!-- Summary Cards -->
<div class="summary-row">
    <div class="summary-card"><div class="num">{n_levels}</div><div class="label">Levels</div></div>
    <div class="summary-card"><div class="num">{n_zones}</div><div class="label">Zones</div></div>
    <div class="summary-card"><div class="num">{n_elements}</div><div class="label">Flow Elements</div></div>
    <div class="summary-card"><div class="num">{n_paths}</div><div class="label">Airflow Paths</div></div>
    <div class="summary-card"><div class="num">{n_ahs}</div><div class="label">AHS Systems</div></div>
</div>

{config_html}

<!-- Levels -->
<section class="report-section">
    <h2>Levels</h2>
    <table>
        <thead><tr><th>Index</th><th>Name</th><th>Ref Height (m)</th><th>Delta Height (m)</th><th>Icons</th></tr></thead>
        <tbody>{levels_rows}</tbody>
    </table>
</section>

<!-- Zones -->
<section class="report-section">
    <h2>Zones ({n_zones})</h2>
    <table>
        <thead><tr><th>ID</th><th>Name</th><th>Level</th><th>Level Name</th><th>Volume (m&sup3;)</th><th>Temp (K)</th></tr></thead>
        <tbody>{zones_rows}</tbody>
    </table>
</section>

<div class="two-col">
    <!-- AHS -->
    <section class="report-section">
        <h2>AHS Systems ({n_ahs})</h2>
        <table>
            <thead><tr><th>ID</th><th>Name</th><th>Ret Zone</th><th>Sup Zone</th><th>Ret Path</th><th>Sup Path</th><th>Exh Path</th></tr></thead>
            <tbody>{ahs_rows}</tbody>
        </table>
    </section>

    <!-- Top path elements -->
    <section class="report-section">
        <h2>Flow Elements by Frequency (Top 20)</h2>
        <table>
            <thead><tr><th>Element Name</th><th>Path Count</th></tr></thead>
            <tbody>{top_paths_rows}</tbody>
        </table>
    </section>
</div>

<!-- Flow Elements -->
<section class="report-section">
    <h2>Flow Elements ({n_elements})</h2>
    <table>
        <thead><tr><th>ID</th><th>Name</th><th>Type</th></tr></thead>
        <tbody>{elements_rows}</tbody>
    </table>
</section>

<div class="report-footer">
    <span>CONTAM PRJ Viewer — Model Summary Report</span>
    <span>SGH (Simpson Gumpertz &amp; Heger)</span>
</div>

</body>
</html>"""
