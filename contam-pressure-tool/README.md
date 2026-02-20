# Stair Pressurization & Floor Depressurization Tool

A web-based engineering tool for stairwell pressurization and fire-floor
depressurization analysis, built on ASHRAE HSCE, NFPA 92, and IBC 909
methodologies.

## Features

- **Estimation Tool** — Analytical calculation of stair supply air and
  fire-floor exhaust using 26 ASHRAE HSCE equations (EQ-01 through EQ-26).
  Includes full equation trace, floor-by-floor results, door-force checks,
  and sensitivity analysis.
- **CONTAM Analysis** — Import `.prj` models from NIST CONTAM, configure
  scenarios (temperature, wind), and run multi-fire-floor batch analyses
  with automated result extraction.
- **Reporting** — Print-ready HTML reports with dual SI/Imperial units,
  formatted equation methodology, and plan-checker-friendly calculation
  traces.

## Quick Start

### 1. Install Python dependencies

Requires **Python 3.10+**.

```bash
pip install -r requirements.txt
```

This installs FastAPI, Uvicorn, NumPy, Pandas, Jinja2, and
python-multipart.

### 2. Run the application

```bash
python app.py
```

The server starts on **http://localhost:5000** and automatically opens
your default browser.

To use a different port:

```bash
PORT=8080 python app.py
```

To suppress the auto-open browser:

```bash
NO_BROWSER=1 python app.py
```

### 3. Choose a workflow

Once the browser opens you will see two tabs:

| Tab | Purpose |
|-----|---------|
| **CONTAM Analysis** | Upload a `.prj` file, configure stair/corridor assignments and weather scenarios, then run CONTAM batch simulations. |
| **Estimation Tool** | Enter building geometry, conditions, and leakage data to get analytical stair-supply and exhaust estimates without CONTAM. |

## Calculation Methodology

This section documents the step-by-step procedure used to determine the
**minimum stair pressurization supply air** and the **minimum fire-floor
exhaust (depressurization)** rates. All equations reference the ASHRAE
*Handbook of Smoke Control Engineering* (HSCE). The tool traces every
substitution so a plan checker can verify each value.

### Design Criteria (Code-Driven Inputs)

| Parameter | Symbol | Typical Value | Source |
|-----------|--------|---------------|--------|
| Min stairwell-to-corridor pressure (all doors closed) | ΔP_min | 12.5 Pa (0.05 in. w.g.) | IBC 909.20.5.1 |
| Max stairwell-to-corridor pressure (all doors closed) | ΔP_max | 87 Pa (0.35 in. w.g.) | NFPA 92 §4.4.2.1 |
| Min door opening velocity (sprinklered) | V_min | 1.0 m/s (200 fpm) | IBC 909.20.5.2 |
| Min door opening velocity (non-sprinklered) | V_min | 1.7 m/s (335 fpm) | NFPA 92 §4.4.2.3 |
| Max door-opening force | F_max | 133 N (30 lbf) | IBC 1010.1.3 |
| Fire-floor exhaust pressure differential | ΔP_exhaust | 25 Pa (0.10 in. w.g.) | IBC 909.20.6 |

### Step 1 — Air Densities (EQ-01)

Compute air density at each temperature using the ideal gas law:

```
ρ = P_atm / (R_air × T)        [EQ-01]
```

where R_air = 287.058 J/(kg·K). Densities are computed for:

| Condition | Symbol | Temperature |
|-----------|--------|-------------|
| Outdoor | ρ_o | T_outdoor (winter or summer design) |
| Indoor | ρ_i | T_indoor (typically 22 °C / 72 °F) |
| Stairwell | ρ_s | T_stair (assumed = T_outdoor or T_indoor) |
| Fire floor | ρ_f | T_fire (typically 300 °C / 572 °F) |

### Step 2 — Leakage Areas

**Door crack leakage (EQ-02):**

```
A_Ld = g_d × (2×w_d + 2×h_d − w_threshold)        [EQ-02]
```

where g_d = door gap (m), w_d = door width, h_d = door height. Default
leakage areas per ASHRAE HSCE Table 6.4:

| Component | Tight | Average | Loose |
|-----------|-------|---------|-------|
| Stair door | 0.01 m² | 0.02 m² | 0.04 m² |
| Elevator door | 0.02 m² | 0.06 m² | 0.11 m² |
| Exterior wall | 0.5×10⁻⁴ m²/m² | 1.7×10⁻⁴ m²/m² | 5.0×10⁻⁴ m²/m² |
| Floor/ceiling | 0.2×10⁻⁴ m²/m² | 0.8×10⁻⁴ m²/m² | 2.5×10⁻⁴ m²/m² |

**Parallel paths (EQ-05):** A_eff = A₁ + A₂ + ... + Aₙ

**Series paths (EQ-06):** 1/A_eff² = 1/A₁² + 1/A₂² + ... + 1/Aₙ²

### Step 3 — Stack Effect at Each Floor (EQ-07)

The temperature-driven pressure difference between the stairwell and the
adjacent floor at height h:

```
ΔP_stack(h) = 3460 × (1/T_o − 1/T_s) × (h − h_NPP)        [EQ-07]
```

where h_NPP is the neutral pressure plane height (the height where stack-
effect pressure difference is zero). The NPP is found iteratively via
mass-balance (EQ-08) — the height where total mass inflow = total mass
outflow across all floors.

Stack effect is largest at the top and bottom floors and zero at the NPP.
In winter (cold outside, warm stair), stack effect opposes pressurization
at upper floors and assists at lower floors.

### Step 4 — Wind Pressure (EQ-09)

```
ΔP_wind = 0.5 × C_p × ρ_o × V_w²        [EQ-09]
```

Wind pressure coefficients for a rectangular building:

| Face | C_p |
|------|-----|
| Windward | +0.70 |
| Leeward | −0.45 |
| Side walls | −0.60 |

### Step 5 — Net Pressure at Each Floor (EQ-15)

The net stairwell-to-floor pressure differential at each floor:

```
ΔP_net = ΔP_mech + ΔP_stack + ΔP_wind − ΔP_exhaust        [EQ-15]
```

where ΔP_mech is the mechanical pressurization target (≥ ΔP_min) and
ΔP_exhaust applies only on the fire floor. **This is the equation that
determines whether each floor meets or fails the minimum/maximum pressure
criteria.**

### Step 6 — Leakage Flow Through Closed Doors (EQ-03)

```
Q = C_d × A × √(2 × ΔP / ρ)        [EQ-03]
```

C_d = 0.65 (orifice discharge coefficient). Computed for every floor
where ΔP_net > 0. The sum across all floors gives the total leakage the
supply fan must overcome.

### Step 7 — Open-Door Flow Requirement (EQ-11, EQ-12)

At the fire floor (and potentially adjacent floors), doors are assumed
open. The minimum flow through each open door:

```
Q_open = V_min × w_d × h_d        [EQ-12]
```

This ensures smoke does not migrate through the open doorway into the
stairwell.

### Step 8 — Door-Opening Force Check (EQ-10b)

```
F_total = F_closer + (ΔP × w_d × h_d / 2) × w_d / (w_d − d)        [EQ-10b]
```

where d = handle-to-latch distance (typically 75 mm). **If F_total > 133 N
(30 lbf), the floor fails.** The maximum allowable ΔP from the force
constraint:

```
ΔP_max = 2 × (F_max − F_closer) × (w_d − d) / (w_d² × h_d)
```

### Step 9 — Total Stair Supply Air (EQ-13, EQ-14)

**All doors closed (EQ-13):**

```
Q_supply_closed = Σ Q_leak_doors + Σ Q_leak_walls        [EQ-13]
```

**Design doors open (EQ-14):**

```
Q_supply_open = Σ Q_leak_closed_floors + Q_open_doors + Σ Q_leak_walls        [EQ-14]
```

**Governing supply = max(Q_closed, Q_open)**

This is the **minimum stair pressurization supply air rate** — the primary
output for fan sizing.

### Step 10 — Fire-Floor Exhaust (Depressurization)

The exhaust system must remove all air leaking into the fire floor plus
thermal expansion. The components:

**Stair leakage into fire floor (EQ-19):**

```
Q_stair = C_d × A_Ld × n_d × √(2 × (ΔP_mech + ΔP_exhaust) / ρ_s)        [EQ-19]
```

**Elevator shaft leakage (EQ-20):**

```
Q_elev = C_d × A_Le × n_elev × √(2 × ΔP_elev / ρ_i)        [EQ-20]
```

**Exterior wall leakage (EQ-21):**

```
Q_ext = C_d × (A_Lw × P_bldg × h_f) × √(2 × (ΔP_exhaust + ΔP_wind) / ρ_o)        [EQ-21]
```

Summed across all four building faces.

**Vertical leakage from floors above and below (EQ-22):**

```
Q_vert = C_d × (A_Lf × A_floor) × √(2 × ΔP_exhaust / ρ_i)        [EQ-22]
```

Applied for the floor above and below the fire floor (×2).

**Fire plume entrainment (EQ-24):**

```
Q_fire = H_dot / (ρ_i × c_p × (T_fire − T_indoor))        [EQ-24]
```

**Thermal expansion (EQ-23):**

```
Q_expansion = Q_fire × (T_fire / T_indoor − 1)        [EQ-23]
```

**Total exhaust at fire temperature (EQ-25):**

```
Q_exhaust = Q_stair + Q_elev + Q_ext + Q_vert + Q_expansion        [EQ-25]
```

**Corrected to standard conditions (EQ-26):**

```
Q_std = Q_exhaust × (T_fire / T_standard)        [EQ-26]
```

This is the **minimum fire-floor exhaust rate** — the primary output for
exhaust fan sizing.

### Step 11 — Iterative Convergence

Steps 3–10 are solved iteratively because the NPP, stack pressures, and
flow rates are mutually dependent. The procedure repeats until supply and
exhaust totals converge within 0.5%.

### Step 12 — Sensitivity Analysis

The tool automatically varies the following parameters to identify the
governing case:

| Parameter | Variations |
|-----------|-----------|
| Exterior wall leakage | Tight, Loose |
| Door leakage area | −50%, +50% |
| Outdoor temperature | Winter, Summer |
| Number of open doors | 0, 1, 2, 3 |
| Fire-floor temperature | 200 °C, 400 °C, 600 °C |
| Wind speed | 0%, 50% of design |
| Elevator shaft | Vented vs. unvented |

Each variation re-runs the full calculation and reports the percentage
change in supply and exhaust rates and whether all constraints are still
met.

---

## Project Structure

```
contam-pressure-tool/
├── app.py                  # FastAPI server & API endpoints
├── requirements.txt        # Python dependencies
├── core/
│   ├── estimation_engine.py   # ASHRAE HSCE equations (EQ-01–EQ-26)
│   ├── estimation_models.py   # Dataclasses for estimation I/O
│   ├── estimation_report.py   # HTML report generator (estimation)
│   ├── analysis_engine.py     # CONTAM batch analysis engine
│   ├── prj_parser.py          # CONTAM .prj file parser
│   ├── prj_writer.py          # CONTAM .prj file writer
│   ├── contam_runner.py       # CONTAM executable wrapper
│   ├── xlog_parser.py         # CONTAM results parser
│   ├── report_generator.py    # HTML report generator (CONTAM)
│   ├── model_report.py        # PRJ model inspection report
│   └── units.py               # Unit conversion helpers
├── static/
│   ├── css/                   # Stylesheets
│   └── js/                    # Frontend JavaScript
├── templates/                 # Jinja2 HTML templates
├── test_estimation.py         # Unit tests (estimation engine)
└── test_e2e.py                # End-to-end tests
```

## Running Tests

```bash
python -m pytest test_estimation.py test_e2e.py -v
```

## Estimation Report Sections

The estimation report output includes:

1. **Section A** — Input Summary (building, conditions, criteria)
2. **Calculation Methodology** — All 26 ASHRAE HSCE equations as formatted
   reference
3. **Section B** — Calculation Trace with numeric substitutions
4. **Section C** — Floor-by-floor pressure, leakage, and force results
5. **Section D** — System summary (supply air, exhaust, design values)
6. **Section E** — Sensitivity analysis (leakage, temperature, wind, doors)

## Standards Reference

- ASHRAE *Handbook of Smoke Control Engineering* (HSCE)
- NFPA 92 — *Standard for Smoke Control Systems*
- IBC Section 909 — *Smoke Control Systems*
