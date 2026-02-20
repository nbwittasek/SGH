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
