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

    # --- Equation Methodology Reference (narrative structure, KaTeX-rendered) ---
    min_dp = criteria.min_dp_closed
    max_dp = criteria.max_dp_closed
    min_dp_inwg = pa_to_inwg(min_dp)
    max_dp_inwg = pa_to_inwg(max_dp)
    exh_dp = criteria.floor_exhaust_dp
    exh_dp_inwg = pa_to_inwg(exh_dp)
    max_force = criteria.max_door_force
    max_force_lbf = n_to_lbf(max_force)
    min_vel = criteria.min_door_velocity

    methodology_html = rf"""
    <div class="section">
        <h2>Calculation Methodology &mdash; ASHRAE HSCE</h2>
        <p class="meth-intro">
            This section presents the analytical procedure used to determine the minimum stair
            pressurization supply air and fire-floor exhaust rates. The methodology follows the
            algebraic equation method from ASHRAE <em>Handbook of Smoke Control Engineering</em>
            (HSCE), with design criteria from NFPA&nbsp;92 and IBC&nbsp;Section&nbsp;909.
            Equation numbers (EQ-01 through EQ-26) correspond to those in the Calculation Trace.
        </p>

        <h3 class="meth-section-title">1. Design Objective</h3>
        <p class="meth-prose">
            The goal of stair pressurization is to maintain a positive pressure differential
            between each pressurized stairwell and the adjacent building floor, preventing
            smoke migration into the stairwell during a fire. Simultaneously, the system must
            not over-pressurize the stairwell to the point where occupants cannot open egress
            doors. These competing requirements define the design window:
        </p>
        <table class="info-table" style="margin:8px 0 8px 16px;font-size:8pt;">
            <tr><td class="label">Min stairwell-to-corridor &Delta;P</td>
                <td>{min_dp:.1f} Pa ({min_dp_inwg:.2f} in.&nbsp;w.g.) &mdash; IBC 909.20.5.1</td></tr>
            <tr><td class="label">Max stairwell-to-corridor &Delta;P</td>
                <td>{max_dp:.1f} Pa ({max_dp_inwg:.2f} in.&nbsp;w.g.) &mdash; NFPA 92 &sect;4.4.2.1</td></tr>
            <tr><td class="label">Min open-door air velocity</td>
                <td>{min_vel} m/s &mdash; IBC 909.20.5.2</td></tr>
            <tr><td class="label">Max door-opening force</td>
                <td>{max_force:.0f} N ({max_force_lbf:.0f} lbf) &mdash; IBC 1010.1.3</td></tr>
            <tr><td class="label">Fire-floor exhaust &Delta;P</td>
                <td>{exh_dp:.1f} Pa ({exh_dp_inwg:.2f} in.&nbsp;w.g.) &mdash; IBC 909.20.6</td></tr>
        </table>

        <h3 class="meth-section-title">2. Air Properties</h3>
        <p class="meth-prose">
            All flow and pressure calculations depend on air density, which varies between the
            fire floor, the building interior, the outdoor environment, and the stairwell shaft.
            Density is determined from the ideal gas law:
        </p>
        <div class="meth-eq-block">
            <span class="meth-eq-label">EQ-01</span>
            <div class="meth-eq-formula">$$\rho = \frac{{P_{{\mathrm{{atm}}}}}}{{R_{{\mathrm{{air}}}} \cdot T}}$$</div>
            <div class="meth-eq-where">
                where \(R_{{\mathrm{{air}}}} = 287.058\;\text{{J/(kg&middot;K)}}\) and \(T\) is in Kelvin.
                Evaluated for outdoor (\(\rho_o\)), indoor (\(\rho_i\)), stairwell (\(\rho_s\)),
                and fire-floor (\(\rho_f\)) temperatures.
            </div>
        </div>

        <h3 class="meth-section-title">3. Building Leakage Characterization</h3>
        <p class="meth-prose">
            The pressurization fan must supply enough air to overcome all leakage paths while
            maintaining the target pressure differential. For stairwell doors, leakage area
            is computed from door geometry:
        </p>
        <div class="meth-eq-block">
            <span class="meth-eq-label">EQ-02</span>
            <div class="meth-eq-formula">$$A_{{Ld}} = g_d \cdot \bigl(2\,w_d + 2\,h_d - w_{{\mathrm{{threshold}}}}\bigr)$$</div>
            <div class="meth-eq-where">
                where \(g_d\) is the door gap width (m), \(w_d\) is door width, \(h_d\) is door height.
            </div>
        </div>
        <p class="meth-prose">
            For other components, leakage areas are taken from ASHRAE HSCE tabulated values.
            Multiple parallel paths add directly (EQ-05: \(A_{{\mathrm{{eff}}}} = A_1 + A_2 + \cdots\));
            series paths combine as (EQ-06: \(1/A_{{\mathrm{{eff}}}}^2 = 1/A_1^2 + 1/A_2^2 + \cdots\)).
        </p>

        <h3 class="meth-section-title">4. Pressure Distribution Across Building Height</h3>
        <p class="meth-prose">
            The net pressure differential varies with height due to <strong>stack effect</strong>
            (buoyancy) and <strong>wind</strong>. The stack-effect pressure at any height \(h\)
            relative to the neutral pressure plane (NPP) is:
        </p>
        <div class="meth-eq-block">
            <span class="meth-eq-label">EQ-07</span>
            <div class="meth-eq-formula">$$\Delta P_s(h) = 3460 \left(\frac{{1}}{{T_o}} - \frac{{1}}{{T_s}}\right) \left(h - h_{{\mathrm{{NPP}}}}\right)$$</div>
            <div class="meth-eq-where">
                The constant 3460 Pa&middot;K/m derives from \(g \cdot P_{{\mathrm{{atm}}}} / R_{{\mathrm{{air}}}}\).
                The NPP height is found iteratively via mass balance (EQ-08).
            </div>
        </div>
        <p class="meth-prose">
            Wind-induced pressure on each building face is:
        </p>
        <div class="meth-eq-block">
            <span class="meth-eq-label">EQ-09</span>
            <div class="meth-eq-formula">$$\Delta P_w = \tfrac{{1}}{{2}}\,C_p\,\rho_o\,V_w^{{\,2}}$$</div>
            <div class="meth-eq-where">
                \(C_p\): windward = +0.70, leeward = &minus;0.45, side = &minus;0.60.
            </div>
        </div>
        <p class="meth-prose">
            The total pressure difference between the stairwell and each floor combines all effects:
        </p>
        <div class="meth-eq-block">
            <span class="meth-eq-label">EQ-15</span>
            <div class="meth-eq-formula">$$\Delta P_{{\mathrm{{net}}}} = \Delta P_{{\mathrm{{mech}}}} + \Delta P_{{\mathrm{{stack}}}} + \Delta P_{{\mathrm{{wind}}}} - \Delta P_{{\mathrm{{exhaust}}}}$$</div>
            <div class="meth-eq-where">
                \(\Delta P_{{\mathrm{{exhaust}}}}\) applies only on the fire floor.
                Must satisfy \(\Delta P_{{\min}} \le \Delta P_{{\mathrm{{net}}}} \le \Delta P_{{\max}}\) at every floor.
            </div>
        </div>

        <h3 class="meth-section-title">5. Airflow Through Closed and Open Doors</h3>
        <p class="meth-prose">
            Flow through each leakage path is computed using the orifice equation:
        </p>
        <div class="meth-eq-block">
            <span class="meth-eq-label">EQ-03</span>
            <div class="meth-eq-formula">$$Q = C_d \cdot A \sqrt{{\frac{{2\,|\Delta P|}}{{\rho}}}}$$</div>
            <div class="meth-eq-where">
                where \(C_d = 0.65\) for building leakage paths.
            </div>
        </div>
        <p class="meth-prose">
            For open doors, a minimum air velocity prevents smoke migration:
        </p>
        <div class="meth-eq-block">
            <span class="meth-eq-label">EQ-12</span>
            <div class="meth-eq-formula">$$Q_{{\mathrm{{open}}}} = V_{{\min}} \cdot w_d \cdot h_d$$</div>
        </div>

        <h3 class="meth-section-title">6. Door-Opening Force Constraint</h3>
        <p class="meth-prose">
            The door-opening force includes the door closer force amplified by the
            pressure differential acting on the door leaf:
        </p>
        <div class="meth-eq-block">
            <span class="meth-eq-label">EQ-10b</span>
            <div class="meth-eq-formula">$$F_{{\mathrm{{total}}}} = F_{{\mathrm{{closer}}}} + \frac{{\Delta P \cdot w_d \cdot h_d}}{{2}} \cdot \frac{{w_d}}{{w_d - d}}$$</div>
            <div class="meth-eq-where">
                Must satisfy \(F_{{\mathrm{{total}}}} \le\) {max_force:.0f} N ({max_force_lbf:.0f} lbf).
                The rearranged form (EQ-10b&prime;) gives the maximum allowable &Delta;P.
            </div>
        </div>

        <h3 class="meth-section-title">7. Stairwell Supply Air Determination</h3>
        <p class="meth-prose">
            Supply air is computed for two scenarios. All doors closed:
        </p>
        <div class="meth-eq-block">
            <span class="meth-eq-label">EQ-13</span>
            <div class="meth-eq-formula">$$Q_{{\mathrm{{supply,closed}}}} = \sum Q_{{\mathrm{{leak,doors}}}} + \sum Q_{{\mathrm{{leak,walls}}}}$$</div>
        </div>
        <p class="meth-prose">
            Design doors open:
        </p>
        <div class="meth-eq-block">
            <span class="meth-eq-label">EQ-14</span>
            <div class="meth-eq-formula">$$Q_{{\mathrm{{supply,open}}}} = \sum Q_{{\mathrm{{closed\;floors}}}} + n_{{\mathrm{{open}}}} \cdot Q_{{\mathrm{{open}}}} + \sum Q_{{\mathrm{{leak,walls}}}}$$</div>
        </div>
        <p class="meth-prose">
            The design supply air rate is the larger of the two:
        </p>
        <div class="meth-eq-block" style="background:#eef6ff;border-color:#b0d4f1;border-width:2px;">
            <span class="meth-eq-label">DESIGN</span>
            <div class="meth-eq-formula">$$\boxed{{Q_{{\mathrm{{design}}}} = \max\!\left(Q_{{\mathrm{{supply,closed}}}},\; Q_{{\mathrm{{supply,open}}}}\right)}}$$</div>
        </div>

        <h3 class="meth-section-title">8. Fire Floor Exhaust (Depressurization)</h3>
        <p class="meth-prose">
            The exhaust system must remove all airflows entering the fire floor: stairwell
            leakage (EQ-19), elevator shaft leakage (EQ-20), exterior wall leakage (EQ-21),
            vertical leakage from adjacent floors (EQ-22), and thermal expansion (EQ-23/24).
        </p>
        <div class="meth-eq-block">
            <span class="meth-eq-label">EQ-19</span>
            <div class="meth-eq-formula">$$Q_{{\mathrm{{stair}}}} = C_d \cdot A_{{Ld}} \cdot n_d \cdot \sqrt{{\frac{{2\,(\Delta P_{{\mathrm{{mech}}}} + \Delta P_{{\mathrm{{exhaust}}}})}}{{\rho_s}}}}$$</div>
        </div>
        <div class="meth-eq-block">
            <span class="meth-eq-label">EQ-20</span>
            <div class="meth-eq-formula">$$Q_{{\mathrm{{elev}}}} = C_d \cdot A_{{Le}} \cdot n_{{\mathrm{{elev}}}} \cdot \sqrt{{\frac{{2\,\Delta P_{{\mathrm{{elev}}}}}}{{\rho_i}}}}$$</div>
        </div>
        <div class="meth-eq-block">
            <span class="meth-eq-label">EQ-21</span>
            <div class="meth-eq-formula">$$Q_{{\mathrm{{ext}}}} = \sum_{{\text{{faces}}}} C_d \cdot (A_{{Lw}} \cdot P_{{\mathrm{{face}}}} \cdot h_f) \cdot \sqrt{{\frac{{2\,(\Delta P_{{\mathrm{{exhaust}}}} + \Delta P_{{\mathrm{{wind}}}})}}{{\rho_o}}}}$$</div>
        </div>
        <div class="meth-eq-block">
            <span class="meth-eq-label">EQ-22</span>
            <div class="meth-eq-formula">$$Q_{{\mathrm{{vert}}}} = 2\,C_d \cdot (A_{{Lf}} \cdot A_{{\mathrm{{floor}}}}) \cdot \sqrt{{\frac{{2\,\Delta P_{{\mathrm{{exhaust}}}}}}{{\rho_i}}}}$$</div>
        </div>
        <p class="meth-prose">
            Thermal expansion: air entrained by the fire (EQ-24) expands as it heats:
        </p>
        <div class="meth-eq-block">
            <span class="meth-eq-label">EQ-23/24</span>
            <div class="meth-eq-formula">$$Q_{{\mathrm{{expansion}}}} = \frac{{\dot{{H}}}}{{\rho_i \cdot c_p \cdot (T_f - T_i)}} \cdot \left(\frac{{T_f}}{{T_i}} - 1\right)$$</div>
        </div>
        <p class="meth-prose">
            The total exhaust and its standard-conditions equivalent:
        </p>
        <div class="meth-eq-block" style="background:#eef6ff;border-color:#b0d4f1;border-width:2px;">
            <span class="meth-eq-label">EQ-25</span>
            <div class="meth-eq-formula">$$\boxed{{Q_{{\mathrm{{exhaust}}}} = Q_{{\mathrm{{stair}}}} + Q_{{\mathrm{{elev}}}} + Q_{{\mathrm{{ext}}}} + Q_{{\mathrm{{vert}}}} + Q_{{\mathrm{{expansion}}}}}}$$</div>
        </div>
        <div class="meth-eq-block">
            <span class="meth-eq-label">EQ-26</span>
            <div class="meth-eq-formula">$$Q_{{\mathrm{{std}}}} = Q_{{\mathrm{{exhaust}}}} \cdot \frac{{T_f}}{{T_{{\mathrm{{std}}}}}}$$</div>
            <div class="meth-eq-where">\(T_{{\mathrm{{std}}}} = 293.15\;\text{{K}}\) (20&deg;C)</div>
        </div>

        <h3 class="meth-section-title">9. Iterative Solution and Sensitivity Analysis</h3>
        <p class="meth-prose">
            The equations are mutually dependent (NPP depends on flows, which depend on
            pressures, which depend on NPP). The solution iterates until supply and exhaust
            totals converge within 0.5%. A mandatory sensitivity analysis then varies wall
            leakage, door leakage (&plusmn;50%), outdoor temperature, number of open doors,
            fire temperature, wind speed, and elevator shaft configuration to identify the
            governing case.
        </p>
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
        /* Methodology section — narrative style */
        .meth-intro {{
            font-size: 8.5pt; color: #444; margin-bottom: 14px; line-height: 1.6;
            padding: 8px 12px; background: #f0f7ff;
            border-left: 3px solid #2e86de; border-radius: 0 4px 4px 0;
        }}
        .meth-section-title {{
            font-size: 9.5pt; color: #1a2332; font-weight: 700;
            border-bottom: 2px solid #2e86de; padding-bottom: 3px;
            margin: 14px 0 6px;
        }}
        .meth-prose {{
            font-size: 8.5pt; color: #444; line-height: 1.6;
            margin: 6px 0; text-align: justify;
        }}
        .meth-eq-block {{
            background: #f8f9fa; border: 1px solid #e8ecf0; border-radius: 4px;
            padding: 6px 12px; margin: 6px 0;
        }}
        .meth-eq-label {{
            font-family: "Consolas", "Courier New", monospace;
            font-weight: 700; color: #2e86de; font-size: 7.5pt;
            background: #e8f0fe; border-radius: 3px; padding: 2px 6px;
            display: inline-block; margin-bottom: 2px;
        }}
        .meth-eq-formula {{
            color: #1a2332; padding: 2px 0; text-align: center;
        }}
        .meth-eq-formula .katex-display {{
            margin: 4px 0 2px;
        }}
        .meth-eq-where {{
            font-size: 7.5pt; color: #666; line-height: 1.4; margin-top: 2px;
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
