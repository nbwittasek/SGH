"""Generate formatted HTML reports for stair pressurization analysis.

Produces a self-contained HTML file suitable for printing to PDF.
"""
import datetime
import html as html_module
from pathlib import Path
from typing import List, Optional



def _esc(text) -> str:
    """Escape text for safe HTML insertion."""
    return html_module.escape(str(text)) if text else ""


def generate_report_html(
    project_name: str,
    scenarios: list,
    stairs: list,
    corridors: list,
    results: list,
    acceptance_criteria: dict,
    model_info: dict = None,
) -> str:
    """Generate a complete HTML report.

    Args:
        project_name: Name of the project
        scenarios: List of scenario dicts {name, temp_f, wind_mph, wind_dir}
        stairs: List of stair config dicts {label, levels: [{level_num, zone_id, flow_rate}]}
        corridors: List of corridor config dicts {label, levels: [{level_num, zone_id, flow_rate}]}
        results: List of result summary dicts {scenario, columns, data}
        acceptance_criteria: {min_dp_inwc, max_dp_inwc}
        model_info: Optional {filename, num_levels, num_zones, num_paths, num_ahs}

    Returns:
        Complete HTML string for the report.
    """
    min_dp = acceptance_criteria.get("min_dp_inwc", 0.05)
    max_dp = acceptance_criteria.get("max_dp_inwc", 0.45)
    max_dp_stair = acceptance_criteria.get("max_dp_stair_inwc", 0.17)
    now = datetime.datetime.now().strftime("%B %d, %Y  %I:%M %p")

    # Build scenario table rows
    scenario_rows = ""
    for s in scenarios:
        scenario_rows += f"""
            <tr>
                <td>{_esc(s.get('name',''))}</td>
                <td>{_esc(s.get('temp_f',''))}&deg;F</td>
                <td>{_esc(s.get('wind_mph',0))} mph</td>
                <td>{_esc(s.get('wind_dir',270))}&deg;</td>
            </tr>"""

    # Build stair config summary
    stair_summary = ""
    for st in stairs:
        levels = st.get("levels", [])
        active_levels = [l for l in levels if l.get("flow_rate", 0) > 0]
        flow_rates = [l["flow_rate"] for l in active_levels]
        if flow_rates:
            min_flow = min(flow_rates)
            max_flow = max(flow_rates)
            flow_str = f"{min_flow}" if min_flow == max_flow else f"{min_flow}-{max_flow}"
        else:
            flow_str = "0"
        stair_summary += f"""
            <tr>
                <td>{_esc(st.get('label',''))}</td>
                <td>{len(levels)}</td>
                <td>{len(active_levels)}</td>
                <td>{_esc(flow_str)} SCFM</td>
            </tr>"""

    # Build corridor config summary
    corridor_summary = ""
    for cr in corridors:
        levels = cr.get("levels", [])
        active = [l for l in levels if l.get("flow_rate", 0) > 0]
        flow_rates = [l["flow_rate"] for l in active]
        flow_str = f"{min(flow_rates)}" if flow_rates and min(flow_rates) == max(flow_rates) else (f"{min(flow_rates)}-{max(flow_rates)}" if flow_rates else "0")
        corridor_summary += f"""
            <tr>
                <td>{_esc(cr.get('label',''))}</td>
                <td>{len(levels)}</td>
                <td>{len(active)}</td>
                <td>{_esc(flow_str)} SCFM</td>
            </tr>"""

    # Model info section
    model_section = ""
    if model_info:
        model_section = f"""
        <div class="section">
            <h2>Model Information</h2>
            <table class="info-table">
                <tr><td class="label">PRJ File:</td><td>{_esc(model_info.get('filename',''))}</td></tr>
                <tr><td class="label">Levels:</td><td>{_esc(model_info.get('num_levels',''))}</td></tr>
                <tr><td class="label">Zones:</td><td>{_esc(model_info.get('num_zones',''))}</td></tr>
                <tr><td class="label">Airflow Paths:</td><td>{_esc(model_info.get('num_paths',''))}</td></tr>
                <tr><td class="label">AHS Systems:</td><td>{_esc(model_info.get('num_ahs',''))}</td></tr>
            </table>
        </div>"""

    # Build results tables for each scenario
    results_html = ""
    for res in results:
        scenario_name = res.get("scenario", "")
        columns = res.get("columns", [])
        data = res.get("data", [])

        # Count pass/fail
        total_cells = 0
        pass_cells = 0
        fail_cells = 0
        warn_cells = 0

        header_row = "".join(f"<th>{_esc(c)}</th>" for c in columns)
        body_rows = ""
        for row in data:
            cells = ""
            for ci, val in enumerate(row):
                if ci == 0:
                    cells += f'<td class="level-cell">{_esc(val)}</td>'
                    continue
                try:
                    num = float(val)
                except (ValueError, TypeError):
                    cells += f"<td>{_esc(val) if val else ''}</td>"
                    continue
                if num == 0:
                    cells += "<td>-</td>"
                    continue
                total_cells += 1
                absv = abs(num)
                # Use stair max for S2V/V2C/EXT columns, floor max for others
                col_name = columns[ci] if ci < len(columns) else ""
                is_stair = col_name.endswith(("_S2V", "_V2C", "_EXT"))
                col_max = max_dp_stair if is_stair else max_dp
                if absv < min_dp or absv > col_max:
                    cls = "fail"
                    fail_cells += 1
                elif absv < min_dp * 1.1 or absv > col_max * 0.9:
                    cls = "warn"
                    warn_cells += 1
                else:
                    cls = "pass"
                    pass_cells += 1
                cells += f'<td class="{cls}">{num:.4f}</td>'
            body_rows += f"<tr>{cells}</tr>\n"

        # Summary badge
        if total_cells > 0:
            pct = pass_cells / total_cells * 100
            badge_cls = "pass-badge" if fail_cells == 0 else "fail-badge"
            badge = f'<span class="{badge_cls}">{pass_cells}/{total_cells} PASS ({pct:.0f}%)</span>'
            if fail_cells > 0:
                badge += f' <span class="fail-badge">{fail_cells} FAIL</span>'
            if warn_cells > 0:
                badge += f' <span class="warn-badge">{warn_cells} WARN</span>'
        else:
            badge = '<span class="na-badge">No data</span>'

        results_html += f"""
        <div class="section results-section">
            <h2>Results: {_esc(scenario_name)}</h2>
            <div class="summary-line">{badge}</div>
            <table class="results-table">
                <thead><tr>{header_row}</tr></thead>
                <tbody>{body_rows}</tbody>
            </table>
        </div>
        <div class="page-break"></div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Stairwell Pressurization Report — {_esc(project_name)}</title>
    <style>
        @page {{
            size: landscape;
            margin: 0.5in;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: "Segoe UI", Arial, Helvetica, sans-serif;
            font-size: 9pt;
            color: #2c3e50;
            line-height: 1.4;
            background: #fff;
        }}
        .report-header {{
            border-bottom: 3px solid #2e86de;
            padding-bottom: 12px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
        }}
        .report-header h1 {{
            font-size: 18pt;
            color: #1a2332;
            margin-bottom: 2px;
        }}
        .report-header .subtitle {{
            font-size: 11pt;
            color: #7f8c9b;
        }}
        .report-header .meta {{
            text-align: right;
            font-size: 8pt;
            color: #7f8c9b;
        }}
        .section {{
            margin-bottom: 18px;
        }}
        .section h2 {{
            font-size: 12pt;
            color: #2e86de;
            border-bottom: 1px solid #dde2e8;
            padding-bottom: 4px;
            margin-bottom: 8px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 8pt;
        }}
        th {{
            background: #2e3a4e;
            color: #fff;
            padding: 4px 6px;
            text-align: center;
            font-weight: 600;
            white-space: nowrap;
        }}
        td {{
            padding: 3px 6px;
            border-bottom: 1px solid #ecf0f4;
            text-align: center;
        }}
        .level-cell {{
            text-align: left;
            font-weight: 600;
            background: #f8f9fa;
            white-space: nowrap;
        }}
        .info-table {{ width: auto; }}
        .info-table td {{ text-align: left; padding: 2px 12px 2px 0; border: none; }}
        .info-table .label {{ font-weight: 600; color: #7f8c9b; min-width: 120px; }}
        .config-table th {{ font-size: 8pt; }}
        .config-table td {{ text-align: left; }}
        .results-table td.pass {{
            background: rgba(39,174,96,0.12);
            color: #1e8449;
            font-weight: 600;
        }}
        .results-table td.fail {{
            background: rgba(231,76,60,0.12);
            color: #c0392b;
            font-weight: 700;
        }}
        .results-table td.warn {{
            background: rgba(243,156,18,0.12);
            color: #d68910;
            font-weight: 600;
        }}
        .summary-line {{
            margin-bottom: 8px;
            font-size: 9pt;
        }}
        .pass-badge {{
            display: inline-block;
            background: #27ae60;
            color: #fff;
            padding: 2px 8px;
            border-radius: 3px;
            font-weight: 600;
            font-size: 8pt;
        }}
        .fail-badge {{
            display: inline-block;
            background: #e74c3c;
            color: #fff;
            padding: 2px 8px;
            border-radius: 3px;
            font-weight: 600;
            font-size: 8pt;
        }}
        .warn-badge {{
            display: inline-block;
            background: #f39c12;
            color: #fff;
            padding: 2px 8px;
            border-radius: 3px;
            font-weight: 600;
            font-size: 8pt;
        }}
        .na-badge {{
            display: inline-block;
            background: #bdc3c7;
            color: #fff;
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 8pt;
        }}
        .criteria-box {{
            display: inline-block;
            background: #f0f4f8;
            border: 1px solid #dde2e8;
            border-radius: 4px;
            padding: 6px 14px;
            font-size: 8pt;
            margin-bottom: 12px;
        }}
        .criteria-box strong {{ color: #2e86de; }}
        .two-col {{ display: flex; gap: 20px; }}
        .two-col > div {{ flex: 1; }}
        .page-break {{ page-break-after: always; }}
        .footer {{
            margin-top: 20px;
            padding-top: 8px;
            border-top: 1px solid #dde2e8;
            font-size: 7pt;
            color: #bdc3c7;
            text-align: center;
        }}
        @media print {{
            .no-print {{ display: none; }}
            body {{ font-size: 8pt; }}
        }}
        .print-btn {{
            position: fixed;
            top: 10px;
            right: 10px;
            background: #2e86de;
            color: #fff;
            border: none;
            padding: 8px 20px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 10pt;
            font-weight: 600;
            z-index: 1000;
        }}
        .print-btn:hover {{ background: #1b6fbf; }}
    </style>
</head>
<body>
    <button class="print-btn no-print" onclick="window.print()">Print / Save PDF</button>

    <div class="report-header">
        <div>
            <h1>Stairwell Pressurization Analysis Report</h1>
            <div class="subtitle">{_esc(project_name)}</div>
        </div>
        <div class="meta">
            <div>Generated: {now}</div>
            <div>SGH (Simpson Gumpertz &amp; Heger)</div>
        </div>
    </div>

    {model_section}

    <div class="section">
        <h2>Acceptance Criteria</h2>
        <div class="criteria-box">
            Minimum dP: <strong>{min_dp} in. w.c.</strong> &nbsp;&nbsp;|&nbsp;&nbsp;
            Maximum dP (Stairs — S2V, V2C, EXT): <strong>{max_dp_stair} in. w.c.</strong> &nbsp;&nbsp;|&nbsp;&nbsp;
            Maximum dP (Floors): <strong>{max_dp} in. w.c.</strong>
        </div>
    </div>

    <div class="section">
        <h2>Scenario Matrix</h2>
        <table class="config-table">
            <thead><tr><th>Scenario</th><th>Temperature</th><th>Wind Speed</th><th>Wind Direction</th></tr></thead>
            <tbody>{scenario_rows}</tbody>
        </table>
    </div>

    <div class="two-col">
        <div class="section">
            <h2>Stair Configuration</h2>
            <table class="config-table">
                <thead><tr><th>Stair</th><th>Total Levels</th><th>Active Levels</th><th>Flow Rate</th></tr></thead>
                <tbody>{stair_summary}</tbody>
            </table>
        </div>
        <div class="section">
            <h2>Corridor Configuration</h2>
            <table class="config-table">
                <thead><tr><th>Corridor</th><th>Total Levels</th><th>Active Levels</th><th>Flow Rate</th></tr></thead>
                <tbody>{corridor_summary}</tbody>
            </table>
        </div>
    </div>

    <div class="page-break"></div>

    {results_html}

    <div class="footer">
        CONTAM Stairwell Pressurization Analysis Tool &mdash; SGH &mdash; All pressures in inches of water column (in. w.c.)
    </div>
</body>
</html>"""
    return html
