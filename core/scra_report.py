"""SCRA HTML Report Generator.

Produces a self-contained HTML document replicating the SGH Smoke Control
Rational Analysis format: 8 main sections + 6 appendices (A–F).
"""

import datetime
import html as html_mod
from typing import List, Dict, Optional

from .estimation_engine import cms_to_cfm, n_to_lbf, pa_to_inwg
from .estimation_models import (
    CalculationTrace,
    EstimationResult,
    FloorResult,
    StairResult,
)
from .estimation_report import _build_ashrae_trace, _fmt_flow, _fmt_dp, _fmt_force
from .scra_models import (
    ADORequirement,
    SCRAConfig,
    SCRAResults,
    StairDefinition,
    SmokeZone,
    PassiveSubzone,
    SequenceStep,
    LeakageComponent,
    CONTAMResult,
)


def _esc(text) -> str:
    return html_mod.escape(str(text)) if text else ""


def _status_cls(status: str) -> str:
    return "pass" if status == "PASS" else "fail"


# ---------------------------------------------------------------------------
# CSS Stylesheet
# ---------------------------------------------------------------------------
_CSS = r"""
@page { size: letter; margin: 0.75in 1in; }
* { margin:0; padding:0; box-sizing:border-box; }
body {
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 10pt; color: #222; line-height: 1.5; background: #fff;
    max-width: 8.5in; margin: 0 auto; padding: 40px 60px;
}
h1 { font-size: 18pt; color: #1a2332; margin-bottom: 4px; }
h2 { font-size: 13pt; color: #1a3a6b; border-bottom: 2px solid #1a3a6b;
     padding-bottom: 3px; margin: 24px 0 10px; }
h3 { font-size: 11pt; color: #333; margin: 16px 0 6px; }
h4 { font-size: 10pt; color: #555; margin: 12px 0 4px; }
p, li { margin-bottom: 6px; text-align: justify; }
ul, ol { padding-left: 24px; }
table { width: 100%; border-collapse: collapse; font-size: 9pt; margin: 8px 0; }
th { background: #1a3a6b; color: #fff; padding: 5px 8px; text-align: center;
     font-weight: 600; font-size: 8pt; }
td { padding: 4px 8px; border-bottom: 1px solid #ddd; text-align: center; }
td.left { text-align: left; }
.imperial { font-size: 7.5pt; color: #888; display: block; }
.pass { background: rgba(39,174,96,0.10); color: #1a7a3a; font-weight: 700; }
.fail { background: rgba(220,53,69,0.10); color: #c0392b; font-weight: 700; }
.cover { text-align: center; padding: 80px 0 40px; }
.cover h1 { font-size: 22pt; margin-bottom: 8px; }
.cover .subtitle { font-size: 14pt; color: #555; margin-bottom: 30px; }
.cover .meta { font-size: 11pt; color: #333; margin: 6px 0; }
.cover .org-block { margin: 30px auto; max-width: 500px; text-align: left;
                    display: flex; justify-content: space-between; gap: 40px; }
.cover .org { font-size: 10pt; }
.cover .org-label { font-weight: 700; color: #1a3a6b; font-size: 9pt;
                    text-transform: uppercase; margin-bottom: 4px; }
.toc { margin: 20px 0; }
.toc ul { list-style: none; padding-left: 0; }
.toc li { margin: 3px 0; font-size: 10pt; }
.toc .toc-l2 { padding-left: 20px; font-size: 9.5pt; color: #555; }
.toc .toc-l3 { padding-left: 40px; font-size: 9pt; color: #777; }
.section { margin-bottom: 20px; }
.info-table { width: auto; }
.info-table td { text-align: left; padding: 2px 14px 2px 0; border: none; }
.info-table .label { font-weight: 600; color: #666; min-width: 220px; }
.page-break { page-break-after: always; margin: 30px 0; border-bottom: 1px dashed #ccc; }
.eq-block { background: #f6f8fb; border: 1px solid #dde; border-radius: 4px;
            padding: 8px 14px; margin: 8px 0; text-align: center; font-size: 10pt; }
.eq-label { font-family: monospace; font-weight: 700; color: #1a3a6b;
            font-size: 8pt; float: left; }
.summary-line { font-size: 9pt; margin-top: 6px; }
.note { font-size: 8.5pt; color: #666; font-style: italic; margin: 6px 0; }
/* Calc trace reuse from estimation_report */
.calc-section { margin-bottom: 22px; }
.calc-section-title { font-size: 10pt; font-weight: 700; color: #1a2332;
    border-bottom: 2px solid #1a3a6b; padding-bottom: 3px; margin-bottom: 6px; }
.calc-section-prose { font-size: 8.5pt; color: #444; line-height: 1.6;
    margin: 4px 0 10px; text-align: justify; }
.calc-eq-reference { background: #f6f8fb; border: 1px solid #dde2e8;
    border-radius: 5px; padding: 8px 14px; margin: 10px 0 6px; position: relative; }
.calc-eq-display { text-align: center; padding: 6px 0; font-size: 10pt; color: #1a2332; }
.eq-frac { display: inline-flex; flex-direction: column; align-items: center;
    vertical-align: middle; margin: 0 3px; line-height: 1.2; }
.eq-num { border-bottom: 1.5px solid #333; padding: 0 5px 2px; }
.eq-den { padding: 2px 5px 0; }
.eq-sqrt { white-space: nowrap; }
.eq-rad { border-top: 1.5px solid #333; padding: 1px 4px 0 2px; margin-left: 1px; }
.calc-eq-highlight { background: #eef6ff; border-color: #a0c4e8; border-width: 2px; }
.calc-eq-tag { position: absolute; top: -9px; left: 12px;
    font-family: monospace; font-weight: 700; font-size: 7.5pt; color: #1a3a6b;
    background: #e0ecf8; border-radius: 3px; padding: 1px 7px; border: 1px solid #b6d4f0; }
.calc-instance { margin: 4px 0 8px 12px; padding: 6px 10px;
    border-left: 3px solid #d0d8e4; background: #fdfdfe; font-size: 8pt; }
.calc-instance-header { font-weight: 600; color: #2e3a4e; font-size: 8.5pt; margin-bottom: 4px; }
.calc-inputs-table { width: auto !important; margin: 3px 0 5px 6px; }
.calc-inputs-table td { padding: 1px 10px 1px 0; border: none; text-align: left; font-size: 7.5pt; }
.calc-var { font-weight: 600; color: #7f8c9b; white-space: nowrap; min-width: 80px; }
.calc-val { color: #2c3e50; font-family: monospace; }
.calc-substitution { margin: 4px 0 4px 6px; font-size: 7.5pt; }
.calc-sub-label { color: #7f8c9b; font-weight: 600; }
.calc-sub-expr { color: #444; font-family: monospace; }
.calc-result-box { margin: 4px 0 2px 6px; padding: 3px 8px;
    background: #e8f5e9; border-radius: 3px; display: inline-block; font-size: 8pt; }
.calc-result-arrow { color: #27ae60; font-weight: 700; margin-right: 4px; }
.calc-result-value { color: #1a5e2a; font-weight: 700; font-family: monospace; }
.print-btn { position: fixed; top: 10px; right: 10px; background: #1a3a6b; color: #fff;
    border: none; padding: 8px 20px; border-radius: 4px; cursor: pointer;
    font-size: 10pt; font-weight: 600; z-index: 1000; }
.print-btn:hover { background: #143058; }
@media print { .no-print { display: none; } .page-break { page-break-after: always; } }
.appendix-title { font-size: 14pt; color: #1a3a6b; text-align: center;
    margin: 30px 0 20px; padding: 10px; border: 2px solid #1a3a6b; }
.matrix-table th, .matrix-table td { font-size: 7.5pt; padding: 2px 4px; text-align: center; }
.ado-table td { text-align: left; }
"""


# ---------------------------------------------------------------------------
# Cover Page
# ---------------------------------------------------------------------------
def _render_cover(cfg: SCRAConfig) -> str:
    proj = cfg.project
    return f"""
    <div class="cover">
        <div class="subtitle">smoke control rational analysis</div>
        <div class="meta">{_esc(proj.submittal_type)}</div>
        <h1>{_esc(proj.project_name)}</h1>
        <div class="meta">{_esc(proj.project_city)}, {_esc(proj.project_state)}</div>
        <div class="meta">{_esc(proj.report_date)}</div>
        <div class="meta">SGH Project {_esc(proj.project_number)}</div>
        <div class="org-block">
            <div class="org">
                <div class="org-label">Prepared For</div>
                <div>{_esc(proj.prepared_for_name)}</div>
                <div style="font-size:9pt;color:#666;">{_esc(proj.prepared_for_address)}</div>
            </div>
            <div class="org">
                <div class="org-label">Prepared By</div>
                <div>{_esc(proj.prepared_by_name)}</div>
                <div style="font-size:9pt;color:#666;">{_esc(proj.prepared_by_address)}</div>
                <div style="font-size:9pt;color:#666;">{_esc(proj.prepared_by_phone)}</div>
            </div>
        </div>
    </div>
    <div class="page-break"></div>
    """


# ---------------------------------------------------------------------------
# Executive Summary
# ---------------------------------------------------------------------------
def _render_executive_summary(cfg: SCRAConfig, results: SCRAResults) -> str:
    bldg = cfg.building
    proj = cfg.project
    tenant = bldg.tenant_name or "the tenant"
    scope = bldg.scope_description or f"Level {bldg.scope_bottom_level} to Level {bldg.scope_top_level}"

    stair_list = ", ".join(s.label for s in cfg.stairs) if cfg.stairs else "the pressurized stairs"

    # Build modifications list
    mods = []
    for ps in cfg.passive_subzones:
        if ps.ato_status == "removed":
            mods.append(f"{ps.subzone_type} spaces are treated as passive subzones. "
                        f"{ps.rationale}")
        elif ps.ato_status == "unchanged":
            mods.append(f"{ps.subzone_type} remain unchanged.")

    mods_html = ""
    for i, m in enumerate(mods, 1):
        mods_html += f"<li>{_esc(m)}</li>\n"

    return f"""
    <div class="section">
        <h2>Executive Summary</h2>
        <p>The purpose of this smoke control rational analysis (SCRA) is to summarize
        analysis methods, design assumptions, conceptual exhaust and supply arrangement,
        simulation results pertaining to the smoke control system, equipment requirements,
        and smoke control sequencing requirements proposed for the {_esc(tenant)} space
        at {_esc(proj.project_address)} in {_esc(proj.project_city)}, {_esc(proj.project_state)}.</p>

        <p>This SCRA details the approach taken for the {_esc(tenant)} space, which spans
        from {_esc(scope)}. The smoke control systems discussed herein are the stair
        pressurization system(s) and the floor depressurization systems.</p>

        <p>The following aspects of the smoke control design are established:</p>
        <ul>
            <li>The overall smoke control strategy (pressurized stairs and floor depressurization
            for the high-rise office spaces)</li>
            <li>The design performance criteria (pressure differentials, door opening forces,
            tenability objectives, and duration of operation)</li>
            <li>The acceptance testing and special inspection approach required by
            {_esc(cfg.code_references.get('smoke_control', 'LABC 909'))}</li>
        </ul>

        {"<p>The changes described in this document:</p><ol>" + mods_html + "</ol>" if mods_html else ""}
    </div>
    <div class="page-break"></div>
    """


# ---------------------------------------------------------------------------
# Table of Contents
# ---------------------------------------------------------------------------
def _render_toc() -> str:
    sections = [
        ("1.", "Introduction"),
        ("1.1", "Project Background"),
        ("2.", "Overview of Smoke Control Systems"),
        ("2.1", "Passive Smoke Control"),
        ("2.2", "Active Smoke Control"),
        ("3.", "Passive Subzones"),
        ("4.", "Smoke Zones and Approaches"),
        ("5.", "System Activation and Sequence of Operations"),
        ("5.1", "Smoke Control Initiating Devices"),
        ("5.2", "Sequence of Operation"),
        ("6.", "Smoke Control Equipment"),
        ("7.", "Special Inspection and Commissioning"),
        ("8.", "Limitations"),
        ("A", "Appendix A — Rationality"),
        ("B", "Appendix B — Smoke Control Calculation Results"),
        ("C", "Appendix C — Smoke Zones"),
        ("D", "Appendix D — CONTAM Results"),
        ("E", "Appendix E — CONTAM Screenshots"),
        ("F", "Appendix F — Smoke Control Commissioning"),
    ]
    items = ""
    for num, title in sections:
        cls = "toc-l2" if "." in num and not num.startswith("A") else ""
        if len(num) == 1 and num.isalpha():
            cls = ""
        items += f'<li class="{cls}"><strong>{num}</strong> {_esc(title)}</li>\n'
    return f"""
    <div class="section toc">
        <h2>Table of Contents</h2>
        <ul>{items}</ul>
    </div>
    <div class="page-break"></div>
    """


# ---------------------------------------------------------------------------
# Section 1: Introduction
# ---------------------------------------------------------------------------
def _render_section_1(cfg: SCRAConfig) -> str:
    bldg = cfg.building
    proj = cfg.project
    tenant = bldg.tenant_name or "the tenant"
    code_ref = cfg.code_references.get("smoke_control", "Section 909")
    high_rise_ref = cfg.code_references.get("high_rise", "Section 403")

    scope = bldg.scope_description or f"Level {bldg.scope_bottom_level} to Level {bldg.scope_top_level}"

    return f"""
    <div class="section">
        <h2>1. Introduction</h2>
        <p>This report provides details of the smoke control rational analysis (SCRA) as
        required by {_esc(high_rise_ref)} and {_esc(code_ref)} for the {_esc(tenant)} space
        in the {_esc(bldg.building_name)} at {_esc(proj.project_address)} in
        {_esc(proj.project_city)}, {_esc(proj.project_state)}.</p>

        <h3>1.1 Project Background</h3>
        <p>The {_esc(bldg.building_name)} ({_esc(bldg.building_abbreviation)}) building
        consists of a {bldg.total_stories}-story {_esc(bldg.building_type)}
        {"with " + str(bldg.above_grade_parking) + " levels of above-grade parking, " if bldg.above_grade_parking else ""}
        {str(bldg.subterranean_levels) + " levels of subterranean parking" if bldg.subterranean_levels else ""}.</p>

        <p>The {_esc(tenant)} space is located on {_esc(scope)}.</p>

        {"<p>The base building was designed with an original SCRA prepared by " +
         _esc(bldg.base_scra_author) + ", dated " + _esc(bldg.base_scra_date) +
         (", with revisions through " + _esc(bldg.base_scra_revision) if bldg.base_scra_revision else "") +
         ".</p>" if bldg.base_scra_author else ""}
    </div>
    """


# ---------------------------------------------------------------------------
# Section 2: Overview of Smoke Control Systems
# ---------------------------------------------------------------------------
def _render_section_2(cfg: SCRAConfig) -> str:
    min_dp = cfg.min_dp_inwg
    max_force = cfg.max_door_force_lbf
    max_dp_exit = cfg.max_dp_exit_door_inwg
    max_dp_stair = cfg.max_dp_stair_door_inwg

    stair_list = ", ".join(s.label for s in cfg.stairs if s.is_smokeproof)
    scope = cfg.building.scope_description or f"Levels {cfg.building.scope_bottom_level} through {cfg.building.scope_top_level}"

    return f"""
    <div class="section">
        <h2>2. Overview of Smoke Control Systems</h2>
        <p>The project is required to have smoke control in accordance with
        {_esc(cfg.code_references.get('high_rise', 'LABC 403'))} because the building
        is a high rise. The goal of the smoke control system is to maintain a tenable
        environment for the evacuation and relocation of occupants in the event of a fire.</p>

        <h3>2.1 Passive Smoke Control</h3>
        <p>The design team will implement passive smoke control to control smoke spread
        between smoke zones.</p>

        <h4>2.1.1 Smoke Barriers</h4>
        <p>Smoke barriers will principally be implemented between smoke zones (horizontal
        and vertical). When used, smoke barriers must be constructed and sealed to limit
        leakage areas exclusive of protected openings.</p>

        <table>
            <thead><tr>
                <th>Smoke Barrier Construction</th>
                <th>Maximum A/A<sub>w</sub> or A/A<sub>F</sub></th>
            </tr></thead>
            <tbody>
                <tr><td class="left">Walls (interior only)</td><td>0.00100</td></tr>
                <tr><td class="left">Interior exit stairway and ramps, and exit passageway</td><td>0.00035</td></tr>
                <tr><td class="left">Enclosed exit access stairways and ramps, and all other shafts</td><td>0.00150</td></tr>
                <tr><td class="left">Floors and roofs</td><td>0.00050</td></tr>
            </tbody>
        </table>
        <p class="note">Where: A = Total leakage area (sq ft), A<sub>F</sub> = Unit floor area (sq ft),
        A<sub>w</sub> = Unit wall area (sq ft)</p>

        <h4>2.1.2 Smoke Partitions</h4>
        <p>Smoke partitions may be used within smoke zones where it is desired to control
        enclosure leakage for the purposes of door fan testing or for any other reason
        consistent with the intent of the rational analysis.</p>

        <h4>2.1.3 Fire Partitions</h4>
        <p>Fire partitions may be used in the office in lieu of smoke partitions to
        compartment a smoke zone into discrete areas when it is desirable to limit
        smoke movement. One-hour fire partitions are being used at all elevator lobbies,
        excluding fire service access elevator (FSAE) lobbies.</p>

        <h3>2.2 Active Smoke Control</h3>
        <p>Active smoke control is implemented via mechanical pressurization and
        depressurization to achieve required pressure differences across fire barriers.
        Open office spaces on {_esc(scope)} will be depressurized to achieve required
        pressure differentials across horizontal smoke barriers.</p>

        <p>The primary active smoke control systems are as follows:</p>
        <ul>
            <li>{_esc(stair_list)} will be designed using pressurization systems per
            {_esc(cfg.code_references.get('smokeproof', 'LABC 909.20'))}.</li>
            <li>All open office spaces on {_esc(scope)} are designed using a
            depressurization system.</li>
        </ul>

        <h4>2.2.1 Minimum Pressure Difference</h4>
        <p>In accordance with {_esc(cfg.code_references.get('min_dp', 'LABC 909.6.1'))},
        the minimum pressure difference across a smoke barrier shall be {min_dp:.2f} in.
        water gage in fully sprinklered buildings.</p>

        <h4>2.2.2 Maximum Pressure Difference</h4>
        <p>In accordance with {_esc(cfg.code_references.get('door_force_egress', 'LABC 1010.1.3'))},
        the force for pushing or pulling open interior swinging egress doors, other than
        fire doors, may not exceed 5 lbs (22 N). The door is required to swing to a
        full-open position when subjected to a 15 lb (67 N) force.</p>

        <p>The maximum pressure differential at exit doors is approximately {max_dp_exit:.2f} in.
        water gage. Per {_esc(cfg.code_references.get('max_force', 'CBC 909.20.6.2'))},
        the pressure difference across doors serving pressurized stair enclosures shall not
        exceed the {max_force:.0f} lbf maximum force to begin opening the door, corresponding
        to approximately {max_dp_stair:.2f} in. water gage.</p>

        <p>ADOs (Automatic Door Operators) will be installed on all doors that have a
        measured door opening force in excess of 15 lbf. Final ADO requirements will be
        determined upon completion of smoke control system commissioning.</p>
    </div>
    """


# ---------------------------------------------------------------------------
# Section 3: Passive Subzones
# ---------------------------------------------------------------------------
def _render_section_3(cfg: SCRAConfig) -> str:
    subzones_html = ""
    for i, ps in enumerate(cfg.passive_subzones, 1):
        subzones_html += f"""
        <h4>3.2.{i} {_esc(ps.subzone_type)}</h4>
        <p>{_esc(ps.description)}</p>
        <table class="info-table">
            <tr><td class="label">Separation</td><td>{_esc(ps.separation_type)}</td></tr>
            <tr><td class="label">Levels</td><td>{_esc(ps.levels)}</td></tr>
            <tr><td class="label">ATO Status</td><td>{_esc(ps.ato_status.upper())}</td></tr>
        </table>
        {"<p><em>Rationale: " + _esc(ps.rationale) + "</em></p>" if ps.rationale else ""}
        """

    return f"""
    <div class="section">
        <h2>3. Passive Subzones</h2>
        <h3>3.1 Passive Subzone Discussion</h3>
        <p>The proposed use of passive subzones on the high-rise office floors is consistent
        with the intent and technical requirements of {_esc(cfg.code_references.get('smoke_control', 'CBC Section 909'))},
        NFPA 92, and accepted smoke control engineering practice. Neither the code nor
        NFPA 92 requires every enclosed space within a smoke control floor to be mechanically
        pressurized or depressurized; the pressure differential criterion is applied across
        smoke control zone boundaries.</p>

        <h3>3.2 Air Transfer Openings</h3>
        {subzones_html}
    </div>
    """


# ---------------------------------------------------------------------------
# Section 4: Smoke Zones
# ---------------------------------------------------------------------------
def _render_section_4(cfg: SCRAConfig) -> str:
    rows = ""
    for sz in cfg.smoke_zones:
        approach_items = "<br>".join(f"&bull; {_esc(a)}" for a in sz.approach_items)
        rows += f"""
        <tr>
            <td class="left"><strong>{_esc(sz.zone_id)}</strong></td>
            <td class="left">{_esc(sz.levels)}</td>
            <td class="left" style="font-size:8pt;">{approach_items}</td>
        </tr>
        """

    return f"""
    <div class="section">
        <h2>4. Smoke Zones and Approaches</h2>
        <table>
            <thead><tr>
                <th>Smoke Zone ID</th><th>Level(s)</th><th>Approach</th>
            </tr></thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
    """


# ---------------------------------------------------------------------------
# Section 5: System Activation & Sequence
# ---------------------------------------------------------------------------
def _render_section_5(cfg: SCRAConfig) -> str:
    # Initiating devices
    devices_html = ""
    for i, dev in enumerate(cfg.initiating_devices, 1):
        devices_html += f"""
        <li><strong>{_esc(dev.device_type.replace('_', ' ').title())}</strong>
        ({_esc(dev.location)}): {_esc(dev.action)}</li>
        """

    # Sequence of operations
    seq_html = ""
    for step in cfg.sequence_steps:
        sub = ""
        if step.sub_steps:
            sub_items = "".join(f"<li>{_esc(s)}</li>" for s in step.sub_steps)
            sub = f"<ol style='list-style-type:lower-alpha;'>{sub_items}</ol>"
        seq_html += f"<li>{_esc(step.description)}{sub}</li>\n"

    return f"""
    <div class="section">
        <h2>5. System Activation and Sequence of Operations</h2>

        <h3>5.1 Smoke Control Initiating Devices</h3>
        <ol>{devices_html}</ol>

        <h3>5.2 Sequence of Operation</h3>
        <p>The smoke control system will be automatically activated by an appropriately
        zoned automatic sprinkler system, smoke detectors, and manual controls accessible
        to the fire department.</p>
        <ol>{seq_html}</ol>

        <h3>5.3 Activation of Subsequent Devices</h3>
        <p>Upon receipt of subsequent automatic signals from an initiating device from
        any smoke zone, no change to the automatic system configuration will occur. Only
        a single active smoke zone is intended to automatically activate.</p>

        <h3>5.4 Manual Control</h3>
        <p>Manual controls will allow for independent or simultaneous operation of any or
        all smokeproof enclosures and any single smoke zone. Manual activation will result
        in the same sequence of operations as automatic activation.</p>
    </div>
    """


# ---------------------------------------------------------------------------
# Section 6: Equipment
# ---------------------------------------------------------------------------
def _render_section_6(cfg: SCRAConfig) -> str:
    return f"""
    <div class="section">
        <h2>6. Smoke Control Equipment</h2>

        <h3>6.1 Control Systems</h3>
        <ul>
            <li>Control systems shall include provisions for verification: positive confirmation
            of actuation, testing, manual override, presence of power downstream of all disconnects,
            and a preprogrammed weekly test sequence.</li>
            <li>Control systems shall be equipped with a control unit complying with UL 864 and
            listed as smoke control equipment.</li>
        </ul>

        <h3>6.2 Control Air and Differential Pressure Verification Tubing</h3>
        <p>Control air and differential pressure verification tubing will be provided at
        variable speed drive fans used to pressurize smokeproof enclosures per
        {_esc(cfg.code_references.get('smoke_control', 'LABC 909'))}.13.</p>

        <h3>6.3 Combination Fire Smoke Dampers</h3>
        <ul>
            <li>Automatic dampers shall be listed and conform to approved standards.</li>
            <li>Each damper shall be independently controlled by a separate actuator and
            provided with an individual limit or proximity switch.</li>
            <li>Smoke damper leakage ratings shall be no less than Class II.</li>
        </ul>

        <h3>6.4 Doors</h3>
        <ul>
            <li>Door assemblies in fire-resistive assemblies will comply with
            {_esc(cfg.code_references.get('smoke_control', 'LABC'))} 716 and NFPA 80.</li>
            <li>Doors serving pressurized stairs will meet UL 1784 requirements; air leakage
            rate shall not exceed 3.0 cu ft per minute per square foot at 0.10 in. water.</li>
            <li>Fixed door sweeps will be provided in lieu of adjustable door sweeps at all
            doors across which a pressure gradient is being measured.</li>
        </ul>

        <h3>6.5 Ducts</h3>
        <p>Ducts used as part of the stair pressurization will meet the requirements of
        {_esc(cfg.code_references.get('smoke_control', 'LABC 909'))}. Positively pressurized
        ducts that pass through multiple smoke zones are required to be leak tested to
        1.5 times the maximum design pressure. Measured leakage may not exceed 5% of design flow.</p>

        <h3>6.6 Power Systems</h3>
        <p>The smoke control system will be supplied with two sources of power per
        {_esc(cfg.code_references.get('power', 'LABC 909.11'))}. Transfer to full standby
        power shall be automatic and within 60 seconds of failure of the primary power.</p>

        <h3>6.7 Detection and Wiring</h3>
        <p>All wiring, regardless of voltage, shall be fully enclosed within continuous
        raceways per {_esc(cfg.code_references.get('detection', 'LABC 909.12'))}.</p>

        <h3>6.8 Firefighter's Smoke Control Panel</h3>
        <p>A single firefighter's smoke control panel will be provided per
        {_esc(cfg.code_references.get('fscp', 'LABC 909.16'))}.</p>
        <ul>
            <li>Fans, dampers, and other equipment in OFF/CLOSED status — RED</li>
            <li>Fans, dampers, and other equipment in ON/OPEN status — GREEN</li>
            <li>Fans, dampers, and other equipment in FAULT status — YELLOW/AMBER</li>
        </ul>

        <h3>6.9 System Response Time</h3>
        <p>Per {_esc(cfg.code_references.get('response_time', 'LABC 909.17'))}, the smoke
        control system will activate within the required time frame. A preprogrammed weekly
        test sequence shall report abnormal conditions.</p>
    </div>
    """


# ---------------------------------------------------------------------------
# Section 7: Commissioning
# ---------------------------------------------------------------------------
def _render_section_7(cfg: SCRAConfig) -> str:
    return f"""
    <div class="section">
        <h2>7. Special Inspection and Commissioning</h2>
        <p>Smoke control commissioning and special inspection requirements are detailed
        in Appendix F. The commissioning process includes component verification, functional
        testing, pressure and door force verification, and final inspection with the
        authority having jurisdiction.</p>
    </div>
    """


# ---------------------------------------------------------------------------
# Section 8: Limitations
# ---------------------------------------------------------------------------
def _render_section_8(cfg: SCRAConfig) -> str:
    return f"""
    <div class="section">
        <h2>8. Limitations</h2>
        <p>This report has been prepared for the specific application to this project and
        is based on conditions identified herein. The conclusions and recommendations are
        based on the information provided and the stated design conditions. Changes to
        building configuration, occupancy, or construction may require reevaluation of
        the smoke control system design.</p>
        <p>All fan sizes, duct sizes, and damper requirements are subject to final
        engineering design by the mechanical engineer of record. Final ADO requirements
        will be determined upon completion of smoke control system commissioning.</p>
    </div>
    <div class="page-break"></div>
    """


# ---------------------------------------------------------------------------
# Appendix A: Rationality
# ---------------------------------------------------------------------------
def _render_appendix_a(cfg: SCRAConfig, results: SCRAResults) -> str:
    climate = cfg.climate
    leakage_rows = ""
    for lc in cfg.leakage_table:
        leakage_rows += f"""
        <tr>
            <td class="left">{_esc(lc.component)}</td>
            <td>{_esc(lc.leakage_area)}</td>
            <td>{lc.flow_exponent:.2f}</td>
        </tr>
        """

    return f"""
    <div class="appendix-title">Appendix A &mdash; Rationality</div>

    <div class="section">
        <h3>A.1 Stack Effect</h3>
        <p>Temperature differentials between the building interior and the outdoor
        environment create buoyancy-driven airflow in vertical shafts, stairwells,
        and hoistways. This stack effect is the primary driver of pressure distribution
        across the building height and is accounted for in the analytical model.</p>

        <h4>Climate Data</h4>
        <table class="info-table">
            <tr><td class="label">Weather Station</td><td>{_esc(climate.weather_station)}</td></tr>
            <tr><td class="label">Winter Design Dry-Bulb (1%)</td>
                <td>{climate.winter_design_db:.1f}&deg;F ({climate.winter_design_db_C:.1f}&deg;C)</td></tr>
            <tr><td class="label">Summer Design Dry-Bulb (1%)</td>
                <td>{climate.summer_design_db:.1f}&deg;F ({climate.summer_design_db_C:.1f}&deg;C)</td></tr>
            <tr><td class="label">Indoor Design Temperature</td>
                <td>{climate.indoor_design_temp:.1f}&deg;F ({climate.indoor_design_temp_C:.1f}&deg;C)</td></tr>
        </table>

        <h3>A.2 Modeling Inputs</h3>
        <p>Building geometry is per the project drawings. Smoke zones include stairwells,
        vestibules, elevators, corridors, and open offices (explicitly modeled); utility
        rooms are treated with equivalent area/volume/leakage as passive subzones.</p>

        <h4>Table A-1: Building Component Leakage Data</h4>
        <table>
            <thead><tr>
                <th>Building Component</th>
                <th>Leakage Area</th>
                <th>Flow Exponent (n)</th>
            </tr></thead>
            <tbody>{leakage_rows}</tbody>
        </table>

        <h3>A.3 Temperature Effect of Fire</h3>
        <p>Design assumption: sprinkler-controlled fire with room temperatures &le;100&deg;F.
        For sprinklered buildings, buoyancy pressures from fire are approximately
        0.01&ndash;0.02 in. w.g., well within the operating margin of the pressurization
        system.</p>

        <h3>A.4 Design Fire Characterization</h3>
        <p>Per NFPA 92, fire growth is assumed halted at sprinkler activation. Heat release
        rate is &lt;2,000 BTU/s for typical ceiling heights (10&ndash;20 ft).</p>

        <h3>A.5 Wind Effect</h3>
        <p>Wind pressures are evaluated using the pressure coefficient method. Windward
        C<sub>p</sub> = +0.70, leeward = &minus;0.45, side = &minus;0.60.</p>
    </div>
    <div class="page-break"></div>
    """


# ---------------------------------------------------------------------------
# Appendix B: Calculation Results (reuses estimation report trace)
# ---------------------------------------------------------------------------
def _render_appendix_b(results: SCRAResults) -> str:
    est = results.estimation_results
    if not est:
        return '<div class="appendix-title">Appendix B &mdash; Smoke Control Calculation Results</div><p>No estimation results available.</p>'

    # Build Section B trace from estimation traces
    trace_html = _build_ashrae_trace(est.calculation_traces)
    n_traces = len(est.calculation_traces)

    # Build Section C floor-by-floor tables
    floor_tables = ""
    criteria_max_force = 133.0  # N
    for sr in est.stair_results:
        header = """<tr>
            <th>Floor</th><th>Height (m)</th>
            <th>&Delta;P<sub>stack</sub><br>(Pa / in.&nbsp;w.g.)</th>
            <th>&Delta;P<sub>wind</sub><br>(Pa / in.&nbsp;w.g.)</th>
            <th>&Delta;P<sub>net</sub><br>(Pa / in.&nbsp;w.g.)</th>
            <th>Q<sub>leak</sub> (CFM)</th>
            <th>Q<sub>open</sub> (CFM)</th>
            <th>F<sub>total</sub><br>(N / lbf)</th><th>Status</th>
        </tr>"""
        rows = ""
        for fr in sr.floor_results:
            cls = _status_cls(fr.status)
            force_cls = ' class="fail"' if fr.f_total > criteria_max_force else ''
            q_open = f"{cms_to_cfm(fr.q_flow_open):.0f}" if fr.q_flow_open > 0 else "&mdash;"
            rows += f"""<tr>
                <td class="left" style="font-weight:600;">{_esc(fr.floor_label)}</td>
                <td>{fr.height:.1f}</td>
                <td>{fr.dp_stack:.2f}<br><span class="imperial">{pa_to_inwg(fr.dp_stack):.4f}</span></td>
                <td>{fr.dp_wind:.2f}<br><span class="imperial">{pa_to_inwg(fr.dp_wind):.4f}</span></td>
                <td class="{cls}">{fr.dp_net:.2f}<br><span class="imperial">{pa_to_inwg(fr.dp_net):.4f}</span></td>
                <td>{cms_to_cfm(fr.q_leak_closed):.0f}</td>
                <td>{q_open}</td>
                <td{force_cls}>{fr.f_total:.1f}<br><span class="imperial">{n_to_lbf(fr.f_total):.1f}</span></td>
                <td class="{cls}">{fr.status}</td>
            </tr>"""

        floor_tables += f"""
        <h3>Section C &mdash; {_esc(sr.label)} Floor-by-Floor</h3>
        <table>
            <thead>{header}</thead>
            <tbody>{rows}</tbody>
        </table>
        <div class="summary-line">
            Critical floor (min &Delta;P): <strong>{_esc(sr.critical_floor_min_dp)}</strong>
            &nbsp;|&nbsp;
            Critical floor (max force): <strong>{_esc(sr.critical_floor_max_force)}</strong>
        </div>
        <div class="page-break"></div>
        """

    # Section D: System Summary
    summary_rows = ""
    for sr in est.stair_results:
        summary_rows += f"""
        <tr><td class="left">{_esc(sr.label)} Supply (all closed)</td><td>{_fmt_flow(sr.q_supply_closed)}</td></tr>
        <tr><td class="left">{_esc(sr.label)} Supply (doors open)</td><td>{_fmt_flow(sr.q_supply_open)}</td></tr>
        <tr><td class="left"><strong>{_esc(sr.label)} Design Supply</strong></td>
            <td><strong>{_fmt_flow(sr.q_supply_design)}</strong></td></tr>
        """

    er = est.exhaust_result
    summary_rows += f"""
    <tr><td colspan="2" style="border-top:2px solid #1a3a6b;"></td></tr>
    <tr class="pass"><td class="left"><strong>Fire Floor Exhaust (ambient)</strong></td>
        <td><strong>{_fmt_flow(er.q_exhaust_total)}</strong></td></tr>
    """

    return f"""
    <div class="appendix-title">Appendix B &mdash; Smoke Control Calculation Results</div>

    <div class="section">
        <h3>Section A &mdash; Input Summary</h3>
        <p>See Section A of the main report for complete input parameters.</p>
    </div>

    <div class="section">
        <h3>Section B &mdash; Calculation Trace ({n_traces} steps)</h3>
        <p class="note">Equations follow the ASHRAE Handbook of Smoke Control Engineering convention.</p>
        {trace_html}
    </div>
    <div class="page-break"></div>

    {floor_tables}

    <div class="section">
        <h3>Section D &mdash; System Summary</h3>
        <table class="info-table">{summary_rows}</table>
    </div>
    <div class="page-break"></div>
    """


# ---------------------------------------------------------------------------
# Appendix C: Smoke Zones (placeholder for diagrams)
# ---------------------------------------------------------------------------
def _render_appendix_c(cfg: SCRAConfig) -> str:
    zone_list = ""
    for sz in cfg.smoke_zones:
        zone_list += f"<li><strong>{_esc(sz.zone_id)}</strong>: {_esc(sz.levels)}</li>\n"

    return f"""
    <div class="appendix-title">Appendix C &mdash; Smoke Zones</div>
    <div class="section">
        <p>Smoke zone diagrams for each level within the scope of work are provided by the
        project architect. The following smoke zones are defined:</p>
        <ul>{zone_list}</ul>
        <p class="note">Refer to project architectural drawings for detailed smoke zone
        boundary plans at each level.</p>
    </div>
    <div class="page-break"></div>
    """


# ---------------------------------------------------------------------------
# Appendix D: CONTAM Results
# ---------------------------------------------------------------------------
def _render_appendix_d(results: SCRAResults) -> str:
    if not results.contam_results:
        return f"""
        <div class="appendix-title">Appendix D &mdash; CONTAM Results</div>
        <div class="section">
            <p>CONTAM network simulation results will be provided upon completion of the
            CONTAM model analysis. The simulation will verify:</p>
            <ul>
                <li>Minimum pressure differentials (&ge;0.05 in. H<sub>2</sub>O) between
                fire floor and adjacent floors</li>
                <li>Stairwell-to-vestibule and vestibule-to-floor pressure differentials</li>
                <li>Door opening forces at all stairwell doors</li>
            </ul>
            <p>Results will be presented for multiple fire floor scenarios across the scope
            of work levels.</p>
        </div>
        <div class="page-break"></div>
        """

    # Render CONTAM result tables
    rows = ""
    for cr in results.contam_results:
        stair_vest = " / ".join(f"{k}: {v:.3f}" for k, v in cr.stair_vestibule_dps.items())
        vest_floor = " / ".join(f"{k}: {v:.3f}" for k, v in cr.vestibule_floor_dps.items())
        rows += f"""
        <tr>
            <td>{_esc(cr.fire_floor_label)}</td>
            <td>{cr.exhaust_rate_cfm:.0f}</td>
            <td>{cr.dp_floor_above:.3f}</td>
            <td>{cr.dp_floor_below:.3f}</td>
            <td class="left" style="font-size:7pt;">{stair_vest}</td>
            <td class="left" style="font-size:7pt;">{vest_floor}</td>
        </tr>
        """

    return f"""
    <div class="appendix-title">Appendix D &mdash; CONTAM Results</div>
    <div class="section">
        <table>
            <thead><tr>
                <th>Fire Floor</th><th>Exhaust (CFM)</th>
                <th>&Delta;P Above<br>(in. H<sub>2</sub>O)</th>
                <th>&Delta;P Below<br>(in. H<sub>2</sub>O)</th>
                <th>Stair &rarr; Vestibule (in. H<sub>2</sub>O)</th>
                <th>Vestibule &rarr; Floor (in. H<sub>2</sub>O)</th>
            </tr></thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
    <div class="page-break"></div>
    """


# ---------------------------------------------------------------------------
# Appendix E: CONTAM Screenshots (placeholder)
# ---------------------------------------------------------------------------
def _render_appendix_e(cfg: SCRAConfig) -> str:
    return f"""
    <div class="appendix-title">Appendix E &mdash; CONTAM Screenshots</div>
    <div class="section">
        <p>CONTAM model network diagrams for each level are generated from the CONTAM
        project file. The model shows:</p>
        <ul>
            <li>Stairwell enclosures and pressurization supply points</li>
            <li>Elevator shafts and hoistways</li>
            <li>Floor zones with depressurization exhaust points</li>
            <li>Air transfer paths and leakage connections</li>
            <li>Smoke zone boundaries</li>
        </ul>
        <p class="note">CONTAM model file: {_esc(cfg.prj_file_path.split('/')[-1] if cfg.prj_file_path else 'N/A')}</p>
    </div>
    <div class="page-break"></div>
    """


# ---------------------------------------------------------------------------
# Appendix F: Commissioning
# ---------------------------------------------------------------------------
def _render_appendix_f(cfg: SCRAConfig) -> str:
    stair_list = ", ".join(s.label for s in cfg.stairs)

    return f"""
    <div class="appendix-title">Appendix F &mdash; Smoke Control Commissioning</div>

    <div class="section">
        <h3>1. Smoke/Fire Dampers</h3>
        <ul>
            <li>Inspect and label all smoke/fire dampers</li>
            <li>Fault test power and position reporting to smoke control panel</li>
            <li>Verify proper reporting of status</li>
            <li>Test response time</li>
            <li>Functional test from smoke control panel</li>
            <li>Verify listing, record model and manufacturer</li>
            <li>Confirm location matches plans</li>
        </ul>

        <h3>2. Smoke Control Ducts, Fans, Control Equipment</h3>
        <ul>
            <li>Verify duct detector locations</li>
            <li>Inspect supply/exhaust fans: confirm monitoring downstream of disconnect,
            motor service factor, non-combustible restraints, belt quantity and tension</li>
            <li>Record smoke zone and unit IDs for each fan</li>
            <li>Review inlet/outlet locations for fire exposure protection</li>
            <li>Witness duct leakage testing to 1.5&times; maximum design pressure</li>
        </ul>

        <h3>3. Waterflows, Detectors, Manual Pull Stations</h3>
        <ul>
            <li>Verify stair pressurization system activation for {_esc(stair_list)}</li>
            <li>Confirm fans turn on/off per design sequence</li>
            <li>Verify reporting to Fire Alarm Control Panel</li>
            <li>Confirm fire alarm evacuation activation</li>
            <li>Confirm elevator recall and magnetic door holder release</li>
        </ul>

        <h3>4. Functional Testing of Smoke Control Panel</h3>
        <ul>
            <li>Verify all fan/damper status and control priority</li>
            <li>Confirm response time requirements</li>
            <li>Test firefighter's smoke control panel controls</li>
        </ul>

        <h3>5. Smoke Curtains and Automatic Closing Doors</h3>
        <ul>
            <li>Verify functional sequence in designated smoke zones</li>
            <li>Witness door fan testing for maximum leakage</li>
        </ul>

        <h3>6. Pressurized Stairwells and Firefighter's Control Panel</h3>
        <ul>
            <li>Verify pressure difference: building &rarr; vestibule, vestibule &rarr; stair</li>
            <li>Verify door opening force at each stair door</li>
            <li>Confirm door labels</li>
            <li>Verify status for all fans/dampers on smoke control panel</li>
            <li>Confirm control priority (ON-OFF/OPEN-CLOSE at highest priority)</li>
        </ul>

        <h3>7. Smokeproof Enclosure Verification</h3>
        <table class="info-table">
            <tr><td class="label">Min &Delta;P vestibule-to-stair</td>
                <td>{cfg.min_dp_vestibule_inwg:.2f} in. w.g.</td></tr>
            <tr><td class="label">Min &Delta;P vestibule-to-fire-floor</td>
                <td>{cfg.min_dp_vestibule_inwg:.2f} in. w.g.</td></tr>
            <tr><td class="label">Min &Delta;P stair-to-floor (no vestibule)</td>
                <td>{cfg.min_dp_no_vestibule_inwg:.2f} in. w.g.</td></tr>
            <tr><td class="label">Max door opening force</td>
                <td>{cfg.max_door_force_lbf:.0f} lbf ({cfg.max_door_force_lbf * 4.448:.0f} N)</td></tr>
        </table>

        <h3>8. Periodic Retesting</h3>
        <p>Retesting is required every 6 months after occupancy by a qualified inspection
        agency. Results shall be submitted to the fire department and building department.</p>
    </div>
    """


# ---------------------------------------------------------------------------
# ADO Summary Table
# ---------------------------------------------------------------------------
def _render_ado_table(results: SCRAResults) -> str:
    if not results.ado_list:
        return ""

    rows = ""
    for ado in results.ado_list:
        rows += f"""
        <tr>
            <td class="left">{_esc(ado.stair_label)}</td>
            <td class="left">{_esc(ado.floor_label)}</td>
            <td>{ado.dp_inwg:.4f}</td>
            <td>{ado.force_lbf:.1f}</td>
            <td class="left">{_esc(ado.reason)}</td>
        </tr>
        """

    return f"""
    <div class="section">
        <h3>Doors Requiring Automatic Door Operators (ADOs)</h3>
        <table class="ado-table">
            <thead><tr>
                <th>Stair</th><th>Floor</th>
                <th>&Delta;P (in. w.g.)</th><th>Force (lbf)</th><th>Reason</th>
            </tr></thead>
            <tbody>{rows}</tbody>
        </table>
        <p class="note">Final ADO requirements will be determined upon completion of
        smoke control system commissioning, subject to specific as-built conditions.</p>
    </div>
    """


# ---------------------------------------------------------------------------
# Main Report Generator
# ---------------------------------------------------------------------------
def generate_scra_report(results: SCRAResults) -> str:
    """Generate the complete SCRA HTML report."""
    cfg = results.config
    now = datetime.datetime.now().strftime("%B %d, %Y")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Smoke Control Rational Analysis &mdash; {_esc(cfg.project.project_name)}</title>
    <style>{_CSS}</style>
</head>
<body>
    <button class="print-btn no-print" onclick="window.print()">Print / Save PDF</button>

    {_render_cover(cfg)}
    {_render_executive_summary(cfg, results)}
    {_render_toc()}
    {_render_section_1(cfg)}
    {_render_section_2(cfg)}
    {_render_section_3(cfg)}
    {_render_section_4(cfg)}
    <div class="page-break"></div>
    {_render_section_5(cfg)}
    <div class="page-break"></div>
    {_render_section_6(cfg)}
    <div class="page-break"></div>
    {_render_section_7(cfg)}
    {_render_section_8(cfg)}
    {_render_appendix_a(cfg, results)}
    {_render_appendix_b(results)}
    {_render_ado_table(results)}
    {_render_appendix_c(cfg)}
    {_render_appendix_d(results)}
    {_render_appendix_e(cfg)}
    {_render_appendix_f(cfg)}

    <div style="margin-top:20px;padding-top:8px;border-top:1px solid #ddd;
         font-size:7.5pt;color:#aaa;text-align:center;">
        Smoke Control Rational Analysis &mdash; {_esc(cfg.project.prepared_by_name)}
        &mdash; Generated {_esc(now)}
    </div>
</body>
</html>"""
    return html
