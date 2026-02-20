"""HTML report generator for the Stair Pressurization Estimation Tool.

Produces a self-contained HTML report matching Sections 8.1–8.5 of the spec.
Includes dual SI/Imperial units and full equation trace for plan checker review.
"""

import datetime
import html as html_module
from typing import List

from .estimation_engine import cms_to_cfm, n_to_lbf, pa_to_inwg
from .estimation_models import (
    CalculationTrace,
    EstimationResult,
    ExhaustResult,
    FloorResult,
    SensitivityCase,
    StairResult,
)


def _esc(text) -> str:
    return html_module.escape(str(text)) if text else ""


def _fmt_flow(q_cms: float) -> str:
    """Format flow as 'm^3/s (CFM)'."""
    return f"{q_cms:.4f} m&sup3;/s ({cms_to_cfm(q_cms):.0f} CFM)"


def _fmt_dp(p_pa: float) -> str:
    """Format pressure as 'X.XX Pa (Y.YYYY in. w.g.)'."""
    return f"{p_pa:.2f} Pa ({pa_to_inwg(p_pa):.4f} in.&nbsp;w.g.)"


def _fmt_force(f_n: float) -> str:
    """Format force as 'X.X N (Y.Y lbf)'."""
    return f"{f_n:.1f} N ({n_to_lbf(f_n):.1f} lbf)"


def _status_cls(status: str) -> str:
    if status == "PASS":
        return "pass"
    return "fail"


def generate_estimation_report(result: EstimationResult) -> str:
    """Generate the full HTML report per Section 8."""

    cfg = result.config
    now = datetime.datetime.now().strftime("%B %d, %Y  %I:%M %p")
    bldg = cfg.building
    cond = cfg.conditions
    criteria = cfg.criteria

    # --- Section A: Input Summary ---
    input_rows = f"""
    <tr><td class="label">Floors above grade (N)</td><td>{bldg.n_floors_above}</td></tr>
    <tr><td class="label">Floors below grade (N_b)</td><td>{bldg.n_floors_below}</td></tr>
    <tr><td class="label">Floor-to-floor height (h_f)</td><td>{bldg.floor_height} m</td></tr>
    <tr><td class="label">Building perimeter (P_bldg)</td><td>{bldg.building_perimeter} m</td></tr>
    <tr><td class="label">Floor area (A_floor)</td><td>{bldg.floor_area} m&sup2;</td></tr>
    <tr><td class="label">Wall construction</td><td>{_esc(bldg.wall_construction)}</td></tr>
    <tr><td class="label">Outdoor winter temp (T_o,w)</td><td>{cond.T_outdoor_winter}&deg;C</td></tr>
    <tr><td class="label">Outdoor summer temp (T_o,s)</td><td>{cond.T_outdoor_summer}&deg;C</td></tr>
    <tr><td class="label">Indoor temp (T_i)</td><td>{cond.T_indoor}&deg;C</td></tr>
    <tr><td class="label">Fire floor temp (T_f)</td><td>{cond.T_fire}&deg;C</td></tr>
    <tr><td class="label">Wind speed (V_w)</td><td>{cond.wind_speed} m/s</td></tr>
    <tr><td class="label">Wind direction</td><td>{cond.wind_direction}&deg;</td></tr>
    <tr><td class="label">Atmospheric pressure</td><td>{cond.P_atm:.0f} Pa</td></tr>
    <tr><td class="label">Open doors (n_open)</td><td>{cond.n_open_doors}</td></tr>
    <tr><td class="label">Sprinklered</td><td>{"Yes" if cond.is_sprinklered else "No"}</td></tr>
    <tr><td class="label">Design fire HRR</td><td>{cond.design_fire_hrr:.0f} kW</td></tr>
    <tr><td class="label">Fire floor</td><td>{cfg.fire_floor}</td></tr>
    <tr><td class="label">Stairwell temp assumption</td><td>{_esc(cfg.stairwell_temp_assumption)}</td></tr>
    """

    # Stairwell inputs
    stair_input_rows = ""
    for st in cfg.stairwells:
        stair_input_rows += f"""
        <tr>
            <td>{_esc(st.label)}</td>
            <td>{st.cross_section_area} m&sup2;</td>
            <td>{st.door_width} &times; {st.door_height} m</td>
            <td>{st.door_gap_mm} mm</td>
            <td>{st.doors_per_floor}</td>
            <td>{st.serves_bottom}&ndash;{st.serves_top}</td>
            <td>{st.n_exterior_walls}</td>
        </tr>"""

    # Leakage inputs
    leak = cfg.leakage
    leakage_rows = f"""
    <tr><td>Exterior wall</td><td>{_esc(leak.exterior_wall)}</td></tr>
    <tr><td>Interior wall</td><td>{_esc(leak.interior_wall)}</td></tr>
    <tr><td>Floor/ceiling</td><td>{_esc(leak.floor_ceiling)}</td></tr>
    <tr><td>Stair door</td><td>{_esc(leak.stair_door)}</td></tr>
    <tr><td>Elevator door</td><td>{_esc(leak.elevator_door)}</td></tr>
    """

    # Elevator inputs
    elev = cfg.elevators
    elev_rows = f"""
    <tr><td class="label">Number of shafts</td><td>{elev.n_shafts}</td></tr>
    <tr><td class="label">Shaft area</td><td>{elev.shaft_area} m&sup2;</td></tr>
    <tr><td class="label">Door type</td><td>{_esc(elev.door_type)}</td></tr>
    <tr><td class="label">Vent area</td><td>{elev.vent_area} m&sup2;</td></tr>
    """

    # --- Section C: Floor-by-Floor Summary per stair (with dual units) ---
    floor_tables_html = ""
    for sr in result.stair_results:
        header = """<tr>
            <th>Floor</th><th>Height (m)</th>
            <th>&Delta;P_stack<br>(Pa / in.&nbsp;w.g.)</th>
            <th>&Delta;P_wind<br>(Pa / in.&nbsp;w.g.)</th>
            <th>&Delta;P_net<br>(Pa / in.&nbsp;w.g.)</th>
            <th>Q_leak (CFM)</th>
            <th>Q_open (CFM)</th>
            <th>F_total<br>(N / lbf)</th><th>Status</th>
        </tr>"""
        rows = ""
        for fr in sr.floor_results:
            cls = _status_cls(fr.status)
            reasons = "; ".join(fr.failure_reasons) if fr.failure_reasons else ""
            title_attr = f' title="{_esc(reasons)}"' if reasons else ""
            force_cls = ' class="fail"' if fr.f_total > criteria.max_door_force else ''
            q_open_str = f"{cms_to_cfm(fr.q_flow_open):.0f}" if fr.q_flow_open > 0 else "&mdash;"
            rows += f"""<tr>
                <td class="level-cell">{_esc(fr.floor_label)}</td>
                <td>{fr.height:.1f}</td>
                <td>{fr.dp_stack:.2f}<br><span class="imperial">{pa_to_inwg(fr.dp_stack):.4f}</span></td>
                <td>{fr.dp_wind:.2f}<br><span class="imperial">{pa_to_inwg(fr.dp_wind):.4f}</span></td>
                <td class="{cls}">{fr.dp_net:.2f}<br><span class="imperial">{pa_to_inwg(fr.dp_net):.4f}</span></td>
                <td>{cms_to_cfm(fr.q_leak_closed):.0f}</td>
                <td>{q_open_str}</td>
                <td{force_cls}>{fr.f_total:.1f}<br><span class="imperial">{n_to_lbf(fr.f_total):.1f}</span></td>
                <td class="{cls}"{title_attr}>{fr.status}</td>
            </tr>"""

        floor_tables_html += f"""
        <div class="section">
            <h2>Section C &mdash; {_esc(sr.label)} Floor-by-Floor</h2>
            <table class="results-table">
                <thead>{header}</thead>
                <tbody>{rows}</tbody>
            </table>
            <div class="summary-line" style="margin-top:6px;">
                Critical floor (min &Delta;P): <strong>{_esc(sr.critical_floor_min_dp)}</strong>
                &nbsp;|&nbsp;
                Critical floor (max force): <strong>{_esc(sr.critical_floor_max_force)}</strong>
            </div>
        </div>
        <div class="page-break"></div>"""

    # --- Section D: System Summary (with dual units) ---
    system_rows = ""
    for sr in result.stair_results:
        system_rows += f"""
        <tr><td>{_esc(sr.label)} Supply (all closed)</td><td>{_fmt_flow(sr.q_supply_closed)}</td></tr>
        <tr><td>{_esc(sr.label)} Supply (doors open)</td><td>{_fmt_flow(sr.q_supply_open)}</td></tr>
        <tr><td><strong>{_esc(sr.label)} Design Supply</strong></td><td><strong>{_fmt_flow(sr.q_supply_design)}</strong></td></tr>
        """

    er = result.exhaust_result
    system_rows += f"""
    <tr><td colspan="2" style="border-top:2px solid #2e3a4e;"></td></tr>
    <tr><td>Fire Floor Exhaust (at fire temp)</td><td>{_fmt_flow(er.q_exhaust_total)}</td></tr>
    <tr><td><strong>Fire Floor Exhaust (std 20&deg;C)</strong></td><td><strong>{_fmt_flow(er.q_exhaust_std)}</strong></td></tr>
    <tr><td colspan="2" style="border-top:1px solid #ddd;"></td></tr>
    <tr><td>Exhaust &mdash; stair leakage (EQ-19)</td><td>{_fmt_flow(er.q_leak_stairs)}</td></tr>
    <tr><td>Exhaust &mdash; elevator leakage (EQ-20)</td><td>{_fmt_flow(er.q_leak_elevators)}</td></tr>
    <tr><td>Exhaust &mdash; exterior wall leakage (EQ-21)</td><td>{_fmt_flow(er.q_leak_exterior)}</td></tr>
    <tr><td>Exhaust &mdash; vertical leakage (EQ-22)</td><td>{_fmt_flow(er.q_leak_vertical)}</td></tr>
    <tr><td>Exhaust &mdash; thermal expansion (EQ-23)</td><td>{_fmt_flow(er.q_expansion)}</td></tr>
    <tr><td colspan="2" style="border-top:1px solid #ddd;"></td></tr>
    <tr><td>Design criteria &mdash; Min &Delta;P (closed)</td><td>{_fmt_dp(criteria.min_dp_closed)}</td></tr>
    <tr><td>Design criteria &mdash; Max &Delta;P (closed)</td><td>{_fmt_dp(criteria.max_dp_closed)}</td></tr>
    <tr><td>Design criteria &mdash; Max door force</td><td>{_fmt_force(criteria.max_door_force)}</td></tr>
    <tr><td>Design criteria &mdash; Floor exhaust &Delta;P</td><td>{_fmt_dp(criteria.floor_exhaust_dp)}</td></tr>
    <tr><td colspan="2" style="border-top:1px solid #ddd;"></td></tr>
    <tr><td>Neutral Pressure Plane (NPP)</td><td>{result.npp_height:.2f} m above grade</td></tr>
    <tr><td><strong>All Constraints Met</strong></td>
        <td class="{'pass' if result.all_constraints_met else 'fail'}">
            <strong>{"YES" if result.all_constraints_met else "NO"}</strong>
        </td></tr>
    """

    # --- Section E: Sensitivity ---
    sens_header = """<tr>
        <th>Parameter</th><th>Value</th>
        <th>Supply (CFM)</th><th>Supply Change</th>
        <th>Exhaust (CFM)</th><th>Exhaust Change</th>
        <th>Critical Floor</th><th>Violated?</th>
    </tr>"""
    sens_rows = ""
    for sc in result.sensitivity_cases:
        violated_cls = "fail" if sc.constraints_violated else "pass"
        sens_rows += f"""<tr>
            <td>{_esc(sc.parameter)}</td>
            <td>{_esc(sc.value_description)}</td>
            <td>{cms_to_cfm(sc.stair_supply_total):.0f}</td>
            <td>{sc.stair_supply_change_pct:+.1f}%</td>
            <td>{cms_to_cfm(sc.exhaust_total):.0f}</td>
            <td>{sc.exhaust_change_pct:+.1f}%</td>
            <td>{_esc(sc.critical_floor)}</td>
            <td class="{violated_cls}">{"YES" if sc.constraints_violated else "No"}</td>
        </tr>"""

    # --- Section B: Full Calculation Trace (ALL equations in succession) ---
    trace_html = ""
    for i, tr in enumerate(result.calculation_traces):
        inputs_str = ", ".join(f"{k} = {v}" for k, v in tr.inputs.items())
        trace_html += f"""
        <div class="trace-block">
            <div class="trace-eq">{i+1}. {_esc(tr.equation_id)}: {_esc(tr.description)}</div>
            <div class="trace-formula">Formula: {_esc(tr.formula)}</div>
            <div class="trace-inputs">Inputs: {_esc(inputs_str)}</div>
            <div class="trace-sub">Substitution: {_esc(tr.substitution)}</div>
            <div class="trace-result">Result: <strong>{_esc(tr.result)}</strong></div>
        </div>"""

    # Warnings
    warnings_html = ""
    if result.warnings:
        items = "".join(f"<li>{_esc(w)}</li>" for w in result.warnings)
        warnings_html = f"""
        <div class="section">
            <h2>Warnings</h2>
            <ul class="warn-list">{items}</ul>
        </div>"""

    n_traces = len(result.calculation_traces)

    # --- Equation Methodology Reference (all 26 equations, KaTeX-rendered) ---
    methodology_html = r"""
    <div class="section">
        <h2>Calculation Methodology &mdash; ASHRAE HSCE Equations (EQ-01 through EQ-26)</h2>
        <p class="meth-intro">
            The following equations form the complete analytical framework used in
            this estimation.  They are presented here in evaluation order as a
            quick-reference before the numerical Calculation Trace that follows.
            All variables use SI units; Imperial equivalents are shown in the trace.
        </p>

        <div class="meth-group">
            <h3 class="meth-group-title">Air Properties</h3>
            <div class="meth-eq">
                <span class="meth-id">EQ-01</span>
                <span class="meth-name">Air density (ideal gas)</span>
                <div class="meth-formula">$$\rho = \frac{P_{\mathrm{atm}}}{R_{\mathrm{air}} \cdot T}$$</div>
                <div class="meth-where">where \(R_{\mathrm{air}} = 287.058\;\text{J/(kg·K)}\), \(T\) in Kelvin</div>
            </div>
        </div>

        <div class="meth-group">
            <h3 class="meth-group-title">Leakage Areas</h3>
            <div class="meth-eq">
                <span class="meth-id">EQ-02</span>
                <span class="meth-name">Door crack leakage area</span>
                <div class="meth-formula">$$A_{Ld} = g_d \cdot \bigl(2\,w_d + 2\,h_d - w_{\mathrm{threshold}}\bigr)$$</div>
                <div class="meth-where">where \(g_d\) = door gap width (m)</div>
            </div>
            <div class="meth-eq">
                <span class="meth-id">EQ-05</span>
                <span class="meth-name">Parallel leakage areas</span>
                <div class="meth-formula">$$A_{\mathrm{eff}} = A_1 + A_2 + \cdots + A_n$$</div>
            </div>
            <div class="meth-eq">
                <span class="meth-id">EQ-06</span>
                <span class="meth-name">Series leakage areas</span>
                <div class="meth-formula">$$\frac{1}{A_{\mathrm{eff}}^{\,2}} = \frac{1}{A_1^{\,2}} + \frac{1}{A_2^{\,2}} + \cdots + \frac{1}{A_n^{\,2}}$$</div>
            </div>
        </div>

        <div class="meth-group">
            <h3 class="meth-group-title">Orifice Flow</h3>
            <div class="meth-eq">
                <span class="meth-id">EQ-03</span>
                <span class="meth-name">Volumetric orifice flow</span>
                <div class="meth-formula">$$Q = C_d \cdot A \sqrt{\frac{2\,|\Delta P|}{\rho}}$$</div>
            </div>
            <div class="meth-eq">
                <span class="meth-id">EQ-04</span>
                <span class="meth-name">Mass flow through orifice</span>
                <div class="meth-formula">$$\dot{m} = C_d \cdot A \sqrt{2\,\rho\,|\Delta P|}$$</div>
            </div>
        </div>

        <div class="meth-group">
            <h3 class="meth-group-title">Pressure Differentials</h3>
            <div class="meth-eq">
                <span class="meth-id">EQ-07</span>
                <span class="meth-name">Stack-effect pressure</span>
                <div class="meth-formula">$$\Delta P_s(h) = 3460 \left(\frac{1}{T_o} - \frac{1}{T_s}\right)\left(h - h_{\mathrm{NPP}}\right)$$</div>
                <div class="meth-where">Positive = stairwell at higher pressure than adjacent floor</div>
            </div>
            <div class="meth-eq">
                <span class="meth-id">EQ-08</span>
                <span class="meth-name">Neutral Pressure Plane (NPP)</span>
                <div class="meth-formula">$$\sum \dot{m}_{\mathrm{in}} = \sum \dot{m}_{\mathrm{out}} \quad\text{(solved iteratively by bisection)}$$</div>
                <div class="meth-where">\(h_{\mathrm{NPP}}\) is the height where net mass flow through the envelope equals zero</div>
            </div>
            <div class="meth-eq">
                <span class="meth-id">EQ-09</span>
                <span class="meth-name">Wind-induced pressure</span>
                <div class="meth-formula">$$\Delta P_w = \tfrac{1}{2}\,C_p\,\rho_o\,V_w^{\,2}$$</div>
                <div class="meth-where">\(C_p\): windward = +0.70, leeward = &minus;0.45, side = &minus;0.60</div>
            </div>
            <div class="meth-eq">
                <span class="meth-id">EQ-15</span>
                <span class="meth-name">Net floor pressure differential</span>
                <div class="meth-formula">$$\Delta P_{\mathrm{net}} = \Delta P_{\mathrm{mech}} + \Delta P_{\mathrm{stack}} + \Delta P_{\mathrm{wind}} - \Delta P_{\mathrm{exhaust}}$$</div>
            </div>
        </div>

        <div class="meth-group">
            <h3 class="meth-group-title">Door Forces</h3>
            <div class="meth-eq">
                <span class="meth-id">EQ-10a</span>
                <span class="meth-name">Pressure force on door</span>
                <div class="meth-formula">$$F_p = \frac{\Delta P \cdot w_d \cdot h_d}{2}$$</div>
            </div>
            <div class="meth-eq">
                <span class="meth-id">EQ-10b</span>
                <span class="meth-name">Total door-opening force</span>
                <div class="meth-formula">$$F_{\mathrm{total}} = F_{\mathrm{closer}} + \frac{\Delta P \cdot w_d \cdot h_d}{2} \cdot \frac{w_d}{w_d - d}$$</div>
                <div class="meth-where">where \(d\) = handle-to-latch distance; must not exceed code max (133.4 N / 30 lbf)</div>
            </div>
            <div class="meth-eq">
                <span class="meth-id">EQ-10b&prime;</span>
                <span class="meth-name">Max allowable pressure from door force (rearranged)</span>
                <div class="meth-formula">$$\Delta P_{\max} = \frac{2\,(F_{\max} - F_{\mathrm{closer}})\,(w_d - d)}{w_d^{\,2} \cdot h_d}$$</div>
            </div>
        </div>

        <div class="meth-group">
            <h3 class="meth-group-title">Doorway &amp; Open-Door Flow</h3>
            <div class="meth-eq">
                <span class="meth-id">EQ-11</span>
                <span class="meth-name">Average doorway velocity</span>
                <div class="meth-formula">$$V_{\mathrm{door}} = \frac{Q_{\mathrm{door}}}{w_d \cdot h_d}$$</div>
            </div>
            <div class="meth-eq">
                <span class="meth-id">EQ-12</span>
                <span class="meth-name">Required open-door flow</span>
                <div class="meth-formula">$$Q_{\mathrm{open}} = V_{\min} \cdot w_d \cdot h_d$$</div>
                <div class="meth-where">\(V_{\min}\) = 1.0 m/s (sprinklered) or 1.7 m/s (non-sprinklered)</div>
            </div>
        </div>

        <div class="meth-group">
            <h3 class="meth-group-title">Stairwell Supply Air</h3>
            <div class="meth-eq">
                <span class="meth-id">EQ-13</span>
                <span class="meth-name">Total supply &mdash; all doors closed</span>
                <div class="meth-formula">$$Q_{\mathrm{supply,closed}} = \sum Q_{\mathrm{leak,doors}} + \sum Q_{\mathrm{leak,walls}}$$</div>
            </div>
            <div class="meth-eq">
                <span class="meth-id">EQ-14</span>
                <span class="meth-name">Total supply &mdash; design doors open</span>
                <div class="meth-formula">$$Q_{\mathrm{supply,open}} = \sum Q_{\mathrm{closed\;floors}} + n_{\mathrm{open}} \cdot Q_{\mathrm{open}} + \sum Q_{\mathrm{walls}}$$</div>
            </div>
            <div class="meth-eq">
                <span class="meth-id">DESIGN</span>
                <span class="meth-name">Governing supply air rate</span>
                <div class="meth-formula">$$\boxed{Q_{\mathrm{design}} = \max\!\left(Q_{\mathrm{supply,closed}},\; Q_{\mathrm{supply,open}}\right)}$$</div>
            </div>
        </div>

        <div class="meth-group">
            <h3 class="meth-group-title">Fire Floor Exhaust (Depressurization)</h3>
            <div class="meth-eq">
                <span class="meth-id">EQ-19</span>
                <span class="meth-name">Stairwell leakage into fire floor</span>
                <div class="meth-formula">$$Q_{\mathrm{stair}} = C_d \cdot A_{Ld} \cdot n_d \cdot \sqrt{\frac{2\,(\Delta P_{\mathrm{mech}} + \Delta P_{\mathrm{exhaust}})}{\rho_s}}$$</div>
            </div>
            <div class="meth-eq">
                <span class="meth-id">EQ-20</span>
                <span class="meth-name">Elevator shaft leakage into fire floor</span>
                <div class="meth-formula">$$Q_{\mathrm{elev}} = C_d \cdot A_{Le} \cdot n_{\mathrm{elev}} \cdot \sqrt{\frac{2\,\Delta P_{\mathrm{elev}}}{\rho_i}}$$</div>
            </div>
            <div class="meth-eq">
                <span class="meth-id">EQ-21</span>
                <span class="meth-name">Exterior wall leakage into fire floor</span>
                <div class="meth-formula">$$Q_{\mathrm{ext}} = C_d \cdot (A_{Lw} \cdot P_{\mathrm{face}} \cdot h_f) \cdot \sqrt{\frac{2\,(\Delta P_{\mathrm{exh}} + \Delta P_{\mathrm{wind}})}{\rho_o}}$$</div>
                <div class="meth-where">Summed over all building faces</div>
            </div>
            <div class="meth-eq">
                <span class="meth-id">EQ-22</span>
                <span class="meth-name">Vertical leakage (floor above + below)</span>
                <div class="meth-formula">$$Q_{\mathrm{vert}} = 2\,C_d \cdot (A_{Lf} \cdot A_{\mathrm{floor}}) \cdot \sqrt{\frac{2\,\Delta P_{\mathrm{exhaust}}}{\rho_i}}$$</div>
            </div>
        </div>

        <div class="meth-group">
            <h3 class="meth-group-title">Fire &amp; Thermal Effects</h3>
            <div class="meth-eq">
                <span class="meth-id">EQ-24</span>
                <span class="meth-name">Fire plume air entrainment</span>
                <div class="meth-formula">$$Q_{\mathrm{fire}} = \frac{\dot{H}}{\rho_i \cdot c_p \cdot (T_f - T_i)}$$</div>
                <div class="meth-where">\(\dot{H}\) = design fire HRR (W); \(c_p = 1005\;\text{J/(kg·K)}\)</div>
            </div>
            <div class="meth-eq">
                <span class="meth-id">EQ-23</span>
                <span class="meth-name">Thermal expansion volume</span>
                <div class="meth-formula">$$Q_{\mathrm{expansion}} = Q_{\mathrm{fire}} \cdot \left(\frac{T_f}{T_i} - 1\right)$$</div>
            </div>
        </div>

        <div class="meth-group">
            <h3 class="meth-group-title">Exhaust Totals</h3>
            <div class="meth-eq">
                <span class="meth-id">EQ-25</span>
                <span class="meth-name">Total fire floor exhaust (at fire temperature)</span>
                <div class="meth-formula">$$\boxed{Q_{\mathrm{exhaust}} = Q_{\mathrm{stair}} + Q_{\mathrm{elev}} + Q_{\mathrm{ext}} + Q_{\mathrm{vert}} + Q_{\mathrm{expansion}}}$$</div>
            </div>
            <div class="meth-eq">
                <span class="meth-id">EQ-26</span>
                <span class="meth-name">Exhaust at standard conditions (20&deg;C)</span>
                <div class="meth-formula">$$Q_{\mathrm{std}} = Q_{\mathrm{exhaust}} \cdot \frac{T_f}{T_{\mathrm{std}}}$$</div>
                <div class="meth-where">\(T_{\mathrm{std}} = 293.15\;\text{K}\) (20&deg;C)</div>
            </div>
        </div>
    </div>

    <div class="page-break"></div>
    """

    # --- Assemble full report ---
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Stair Pressurization Estimation Report</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css"
          integrity="sha384-nB0miv6/jRmo5UMMR1wu3Gz6NLsoTkbqJghGIsx//Rlm+ZU03BU6SQNC66uf4l5+"
          crossorigin="anonymous">
    <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"
            integrity="sha384-7zkQWkzuo3B5mTepMUcHkMB5jZaolc2xDwL6VFqjFALcbeS9Ber/kqKIFmsm1A7E"
            crossorigin="anonymous"></script>
    <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"
            integrity="sha384-43gviWU0YVjaDtb/GhzOouOXtZMP/7XUzwPTstBeZFe/+rCMvRjwKoYnB1vl0sa4"
            crossorigin="anonymous"
            onload="renderMathInElement(document.body,{{delimiters:[{{left:'$$',right:'$$',display:true}},{{left:'\\\\(',right:'\\\\)',display:false}}],throwOnError:false}});"></script>
    <style>
        @page {{ size: landscape; margin: 0.5in; }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: "Segoe UI", Arial, Helvetica, sans-serif;
            font-size: 9pt; color: #2c3e50; line-height: 1.4; background: #fff;
            padding: 20px;
        }}
        .report-header {{
            border-bottom: 3px solid #2e86de; padding-bottom: 12px; margin-bottom: 20px;
            display: flex; justify-content: space-between; align-items: flex-end;
        }}
        .report-header h1 {{ font-size: 16pt; color: #1a2332; }}
        .report-header .subtitle {{ font-size: 10pt; color: #7f8c9b; }}
        .report-header .meta {{ text-align: right; font-size: 8pt; color: #7f8c9b; }}
        .section {{ margin-bottom: 18px; }}
        .section h2 {{
            font-size: 11pt; color: #2e86de;
            border-bottom: 1px solid #dde2e8; padding-bottom: 4px; margin-bottom: 8px;
        }}
        table {{ width: 100%; border-collapse: collapse; font-size: 8pt; }}
        th {{
            background: #2e3a4e; color: #fff; padding: 4px 6px;
            text-align: center; font-weight: 600; white-space: nowrap;
        }}
        td {{ padding: 3px 6px; border-bottom: 1px solid #ecf0f4; text-align: center; }}
        .level-cell {{ text-align: left; font-weight: 600; background: #f8f9fa; white-space: nowrap; }}
        .imperial {{ font-size: 7pt; color: #7f8c9b; display: block; }}
        .info-table {{ width: auto; }}
        .info-table td {{ text-align: left; padding: 2px 12px 2px 0; border: none; }}
        .info-table .label {{ font-weight: 600; color: #7f8c9b; min-width: 200px; }}
        .config-table th {{ font-size: 8pt; }}
        .config-table td {{ text-align: left; }}
        .results-table td.pass {{ background: rgba(39,174,96,0.12); color: #1e8449; font-weight: 600; }}
        .results-table td.fail {{ background: rgba(231,76,60,0.12); color: #c0392b; font-weight: 700; }}
        .summary-line {{ font-size: 9pt; }}
        .criteria-box {{
            display: inline-block; background: #f0f4f8; border: 1px solid #dde2e8;
            border-radius: 4px; padding: 6px 14px; font-size: 8pt; margin-bottom: 12px;
        }}
        .criteria-box strong {{ color: #2e86de; }}
        .two-col {{ display: flex; gap: 20px; }}
        .two-col > div {{ flex: 1; }}
        .page-break {{ page-break-after: always; }}
        .trace-block {{
            background: #f8f9fa; border: 1px solid #e0e0e0; border-radius: 4px;
            padding: 6px 10px; margin-bottom: 6px; font-size: 8pt;
            font-family: "Consolas", "Courier New", monospace; line-height: 1.5;
        }}
        .trace-eq {{ font-weight: 700; color: #2e86de; margin-bottom: 2px; font-size: 8.5pt; }}
        .trace-formula {{ color: #555; }}
        .trace-inputs {{ color: #666; }}
        .trace-sub {{ color: #444; }}
        .trace-result {{ color: #1a2332; }}
        .warn-list {{ padding-left: 20px; }}
        .warn-list li {{ color: #d68910; margin-bottom: 4px; }}
        /* Methodology section */
        .meth-intro {{
            font-size: 8.5pt; color: #555; margin-bottom: 14px; line-height: 1.5;
        }}
        .meth-group {{
            margin-bottom: 14px;
        }}
        .meth-group-title {{
            font-size: 9pt; color: #1a2332; border-left: 3px solid #2e86de;
            padding-left: 8px; margin-bottom: 6px;
        }}
        .meth-eq {{
            background: #f8f9fa; border: 1px solid #e8ecf0; border-radius: 4px;
            padding: 6px 12px; margin: 0 0 5px 16px;
            display: flex; align-items: flex-start; gap: 10px;
        }}
        .meth-id {{
            flex-shrink: 0;
            font-family: "Consolas", "Courier New", monospace;
            font-weight: 700; color: #2e86de; font-size: 8pt;
            text-align: center; min-width: 52px;
            background: #e8f0fe; border-radius: 3px; padding: 3px 6px;
            margin-top: 2px;
        }}
        .meth-name {{
            font-size: 8pt; color: #555; font-style: italic;
        }}
        .meth-formula {{
            padding: 2px 0; color: #1a2332;
        }}
        .meth-formula .katex-display {{
            margin: 4px 0 2px;
        }}
        .meth-where {{
            font-size: 7.5pt; color: #7f8c9b;
        }}
        .print-btn {{
            position: fixed; top: 10px; right: 10px; background: #2e86de; color: #fff;
            border: none; padding: 8px 20px; border-radius: 4px; cursor: pointer;
            font-size: 10pt; font-weight: 600; z-index: 1000;
        }}
        .print-btn:hover {{ background: #1b6fbf; }}
        @media print {{ .no-print {{ display: none; }} body {{ font-size: 8pt; }} }}
    </style>
</head>
<body>
    <button class="print-btn no-print" onclick="window.print()">Print / Save PDF</button>

    <div class="report-header">
        <div>
            <h1>Stair Pressurization &amp; Floor Depressurization</h1>
            <div class="subtitle">Estimation Report &mdash; ASHRAE HSCE / NFPA 92 / IBC 909</div>
        </div>
        <div class="meta">
            <div>Generated: {now}</div>
            <div>SGH (Simpson Gumpertz &amp; Heger)</div>
        </div>
    </div>

    {warnings_html}

    <div class="section">
        <h2>Section A &mdash; Input Summary</h2>
        <div class="criteria-box">
            Min &Delta;P (closed): <strong>{_fmt_dp(criteria.min_dp_closed)}</strong> &nbsp;|&nbsp;
            Max &Delta;P (closed): <strong>{_fmt_dp(criteria.max_dp_closed)}</strong> &nbsp;|&nbsp;
            Max door force: <strong>{_fmt_force(criteria.max_door_force)}</strong> &nbsp;|&nbsp;
            Floor exhaust &Delta;P: <strong>{_fmt_dp(criteria.floor_exhaust_dp)}</strong>
        </div>

        <div class="two-col">
            <div>
                <h3 style="font-size:9pt;color:#555;margin-bottom:4px;">Building &amp; Conditions</h3>
                <table class="info-table">{input_rows}</table>
            </div>
            <div>
                <h3 style="font-size:9pt;color:#555;margin-bottom:4px;">Elevator Shafts</h3>
                <table class="info-table">{elev_rows}</table>
                <h3 style="font-size:9pt;color:#555;margin:8px 0 4px;">Leakage Tightness</h3>
                <table class="config-table">
                    <thead><tr><th>Component</th><th>Rating</th></tr></thead>
                    <tbody>{leakage_rows}</tbody>
                </table>
            </div>
        </div>

        <h3 style="font-size:9pt;color:#555;margin:10px 0 4px;">Stairwell Geometry</h3>
        <table class="config-table">
            <thead><tr>
                <th>Stair</th><th>Area</th><th>Door (W&times;H)</th>
                <th>Gap</th><th>Doors/Floor</th><th>Serves</th><th>Ext Walls</th>
            </tr></thead>
            <tbody>{stair_input_rows}</tbody>
        </table>
    </div>

    <div class="page-break"></div>

    {methodology_html}

    <div class="section">
        <h2>Section B &mdash; Calculation Trace ({n_traces} steps)</h2>
        <p style="font-size:8pt;color:#7f8c9b;margin-bottom:10px;">
            All equations evaluated in sequence.  Each step shows the formula,
            numeric substitution, and result so a plan checker can verify every value.
        </p>
        {trace_html}
    </div>

    <div class="page-break"></div>

    {floor_tables_html}

    <div class="section">
        <h2>Section D &mdash; System Summary</h2>
        <table class="info-table">{system_rows}</table>
    </div>

    <div class="page-break"></div>

    <div class="section">
        <h2>Section E &mdash; Sensitivity Analysis</h2>
        <table class="results-table">
            <thead>{sens_header}</thead>
            <tbody>{sens_rows}</tbody>
        </table>
    </div>

    <div style="margin-top:20px;padding-top:8px;border-top:1px solid #dde2e8;font-size:7pt;color:#bdc3c7;text-align:center;">
        Stair Pressurization &amp; Floor Depressurization Estimation Tool &mdash; SGH
        &mdash; Methodology: ASHRAE HSCE, NFPA 92, IBC 909
    </div>
</body>
</html>"""
    return html
