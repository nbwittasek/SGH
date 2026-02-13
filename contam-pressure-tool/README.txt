CONTAM Stairwell Pressurization Analysis Tool
=============================================
SGH (Simpson Gumpertz & Heger)


PREREQUISITES
-------------
1. Python 3.9 or later
   - Download from: https://www.python.org/downloads/
   - IMPORTANT: During installation, check "Add Python to PATH"

2. CONTAM 3.x solver (contamX3.exe)
   - Download from NIST: https://www.nist.gov/el/energy-and-environment-division-73200/nist-multizone-modeling/software/contam
   - Install to the default location (C:\Program Files\NIST\CONTAM\)
   - The tool will auto-detect it, or you can browse to it manually


QUICK START (Windows)
---------------------
1. Extract this zip to any folder on your computer
2. Double-click "launch.bat"
   - On first run, it will create a virtual environment and install dependencies
   - This may take 1-2 minutes the first time
3. Your browser will open automatically to the tool
4. To stop: close the command prompt window or press Ctrl+C


QUICK START (Mac/Linux)
-----------------------
1. Extract the zip to any folder
2. Open a terminal in that folder
3. Run: ./launch.sh
4. Your browser will open automatically


HOW TO USE
----------
The tool follows a 6-tab workflow:

  Tab 1 - Project Setup
    Set project name, folder, and path to contamX3.exe

  Tab 2 - Model Import & Parsing
    Browse to your CONTAM .prj file and click "Parse"
    The tool auto-detects stairs, corridors, floor zones, vestibules,
    AHS systems, and flow path elements

  Tab 3 - Pressurization Config (auto-populated)
    Review and adjust:
    - Stair pressurization: supply flow rates (SCFM) per level
    - Corridor zones: tracked for dP measurement (no exhaust by default)
    - Floor zone depressurization: exhaust flow rates (SCFM) per level
    - Roof stair depressurization
    - Airflow path element assignments (S2V, V2C, EXT)

  Tab 4 - Scenario Matrix
    Define temperature/wind scenarios (4 standard scenarios pre-populated)

  Tab 5 - Run Analysis
    Use "Dry Run" to generate modified PRJ files without running CONTAM
    Use "Start Analysis" to run all scenarios x fire floors

  Tab 6 - Results & Reporting
    View summary, per-fire-floor detail, or worst-case analysis
    Export to CSV or generate an HTML report for printing


ACCEPTANCE CRITERIA
-------------------
Default thresholds (adjustable in Tab 6):
  - Minimum dP:              0.05 in. w.c.
  - Maximum dP (Stairs):     0.17 in. w.c.  (S2V, V2C, EXT paths)
  - Maximum dP (Floors):     0.45 in. w.c.  (floor-to-floor dP)


SIMULATION APPROACH
-------------------
- One CONTAM run per fire floor per scenario
- Stairs: supply (pressurization) on ALL levels in every run
- Fire floor: floor zone exhaust (depressurization) on the fire floor only
- Corridors: NOT exhausted; they depressurize naturally via leakage
  to the exhausted floor zone
- Pressure differentials measured:
  * S2V: Stair to Vestibule
  * V2C: Vestibule to Corridor
  * EXT: Stair to Exterior
  * Floor-to-floor: corridor dP above/below fire floor


FILE STRUCTURE
--------------
contam-pressure-tool/
  launch.bat           Windows launcher (double-click to run)
  launch.sh            Mac/Linux launcher
  app.py               Main application (FastAPI server)
  requirements.txt     Python package dependencies
  README.txt           This file
  core/                Analysis engine and CONTAM file handlers
    analysis_engine.py   Orchestrates analysis runs
    prj_parser.py        Parses CONTAM .prj files
    prj_writer.py        Modifies .prj files for each run
    contam_runner.py     Runs contamX3.exe solver
    xlog_parser.py       Extracts results from .xlog files
    report_generator.py  Generates HTML reports
    units.py             Unit conversions
  static/
    css/style.css        Stylesheet
    js/app.js            Frontend logic
  templates/
    index.html           Main UI template


TROUBLESHOOTING
---------------
- "Python is not installed": Install Python 3.9+ and ensure it is in PATH
- "CONTAM executable not found": Set the path manually in Tab 1
- Port 5000 in use: Set environment variable PORT=5001 before launching
- Browser doesn't open: Navigate to http://localhost:5000 manually
