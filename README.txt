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


FIRST-TIME INSTALL (Windows)
-----------------------------
1. Extract this zip to any folder on your computer
2. Double-click "launch.bat"
   - On first run, it will create a virtual environment and install dependencies
   - This may take 1-2 minutes the first time
3. Your browser will open automatically to http://localhost:5000
4. To stop: close the command prompt window or press Ctrl+C

Note: The tool runs entirely on your local machine (localhost). It does not
require any network access or firewall permissions. You can safely dismiss
or ignore any Windows Firewall prompts that may appear — the application
will work correctly without granting network access.


FIRST-TIME INSTALL (Mac/Linux)
-------------------------------
1. Extract the zip to any folder
2. Open a terminal in that folder
3. Run: chmod +x launch.sh && ./launch.sh
4. Your browser will open automatically


UPDATING AN EXISTING INSTALLATION
-----------------------------------
If you already have the tool installed and want to update to a new version:

  Option A — Replace files and re-launch (Recommended):
    1. Download the new version zip
    2. Extract and overwrite the existing files EXCEPT the "venv" folder
       (Copy all files except "venv" into your existing installation folder)
    3. Double-click "launch.bat" (or run ./launch.sh on Mac/Linux)
       - It will detect the existing virtual environment
       - It will automatically install any new/updated dependencies
       - No need to recreate the virtual environment

  Option B — Use the update script:
    1. Replace the code files as in Option A
    2. Double-click "update.bat" (or run ./update.sh on Mac/Linux)
       - This only updates dependencies without launching the app
    3. Then run "launch.bat" to start

  What NOT to do:
    - Do NOT delete the "venv" folder unless you want a full reinstall
    - Do NOT re-run the Python installer; the virtual environment persists
    - Existing project data (project.json, tab3_config.json) will be preserved
      because they are stored in your project folder, not the app folder


USING GIT / GITHUB FOR VERSION CONTROL
----------------------------------------
To track changes with Git and GitHub:

  1. Create a GitHub Account
     - Go to https://github.com and sign up for a free account

  2. Install Git
     - Download from: https://git-scm.com/downloads
     - During install, accept defaults (or choose your preferred editor)

  3. Create a Repository on GitHub
     - Click "New repository" on GitHub
     - Name it (e.g., "contam-pressure-tool")
     - Choose Private or Public
     - Do NOT initialize with README (you already have one)

  4. Initialize and Push Your Code
     Open a command prompt in the contam-pressure-tool folder and run:

       git init
       git add .
       git commit -m "Initial commit"
       git branch -M main
       git remote add origin https://github.com/YOUR_USERNAME/contam-pressure-tool.git
       git push -u origin main

  5. After Making Changes
     To save updates to GitHub:

       git add .
       git commit -m "Describe what you changed"
       git push

  6. Create a .gitignore file (Recommended)
     Create a file named ".gitignore" in the root folder with:

       venv/
       __pycache__/
       *.pyc
       config.json
       analysis/

     This prevents the virtual environment and temporary files from being
     tracked in version control.


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
      * Check/uncheck "Pressurized Stair" to enable/disable each stair
      * Use "Apply to All" to set a single SCFM value across all floors
      * Use "Apply Alternating" to set values at regular intervals
        (e.g., every other floor, every 3rd floor, etc.)
      * Use "Import from Excel" to load SCFM values from a .xlsx or .csv file
    - Corridor zones: tracked for dP measurement (no exhaust by default)
    - Floor zone depressurization: exhaust flow rates (SCFM) per level
    - Roof stair depressurization
    - Airflow path element assignments (S2V, V2C, EXT)

    Configuration Management:
    - "Save Config" saves all Tab 3 input values to the project folder
    - "Load Config" restores previously saved values
    - "Update PRJ File" writes current settings to a new PRJ file

  Tab 4 - Scenario Matrix
    Define temperature/wind scenarios (4 standard scenarios pre-populated)

  Tab 5 - Run Analysis
    Use "Dry Run" to generate modified PRJ files without running CONTAM
    Use "Start Analysis" to run all scenarios x fire floors

  Tab 6 - Results & Reporting
    View summary, per-fire-floor detail, or worst-case analysis
    Export to CSV or generate an HTML report for printing


CONTAM MODEL BUILDING NOTES
=================================================================================
When building your CONTAM model, follow these naming conventions for best
compatibility with the auto-populate and analysis features:

Zone Naming:
  - Stairs: Use zone names matching stair labels (e.g., "Stair1", "Stair2")
  - Corridor Depressurization: Use a distinct zone name like "EXH.Corridor"
    for the corridor zone being depressurized and measured.
  - Floor Depressurization: Use a distinct zone name like "EXH.Floor"
    for the floor zone being depressurized and measured.

Flow Element Naming:
  - Stair-to-Vestibule: "Door-{StairLabel}-S2V" (e.g., "Door-Stair1-S2V")
  - Vestibule-to-Corridor: "Door-{StairLabel}-V2C" (e.g., "Door-Stair1-V2C")
  - Stair-to-Exterior: "Door-{StairLabel}-EXT" (e.g., "Door-Stair1-EXT")
  - For stairs without vestibules: "Door-{StairLabel}-S2C" is also recognized
  - Floor Leakage (measured dP): Use "FLR.LK" for dP from floor above to below

AHS (Air Handling Systems):
  - AHS #1 should be the SUPPLY system (used for stair pressurization)
  - AHS #2 should be the RETURN system (used for corridor/floor depressurization)
  - Auto-populate will default to these assignments.

Auto-Populate by Zone Name:
  - Sets zone selections across all levels for matching zone names
  - Also auto-sets AHS (Supply for stairs, Return for corridor/floor)
  - Attempts to set icon Col/Row by finding the zone icon position in the PRJ
    and placing the supply/return icon in an adjacent unoccupied cell
  - If icon placement cannot find a free cell, it defaults to the zone icon position


EXCEL IMPORT FORMAT FOR SCFM VALUES
-------------------------------------
The tool can generate pre-formatted Excel templates and import SCFM values.

  Generating Templates:
    1. Parse your PRJ file (Tab 2) and set up stairs/corridors (Tab 3)
    2. Click "Generate SCFM Templates" in the Tab 3 toolbar
    3. One .xlsx file is created per entity in your project's scfm_templates/ folder:
         • Stair_1-SCFM-Template.xlsx
         • Stair_2-SCFM-Template.xlsx
         • Corridor_1-SCFM-Template.xlsx
         • Floor_Zone_1-SCFM-Template.xlsx
         etc.
    4. Each file is pre-populated with your model's level names
    5. Open in Excel, fill in the SCFM values, and save

  Importing Values:
    1. Click "Import from Excel" on any stair, corridor, or floor zone panel
    2. The file browser opens — it defaults to the scfm_templates/ folder
    3. Select the appropriate .xlsx file and click "Select"
    4. Values are loaded into the SCFM column automatically

  Custom Excel Format (if not using generated templates):
    Column A: Level name or number (for reference only)
    Column B+: SCFM values

    Example:
      Level    | SCFM
      Level 1  | 600
      Level 2  | 600
      Level 3  | 0
      Level 4  | 600
      ...

    - Supports .xlsx, .xls, and .csv formats
    - First row is treated as a header
    - If multiple data columns exist, you will be prompted to choose which one
    - Values are applied top-to-bottom matching the model's level order


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
  (non-pressurized stairs are excluded automatically)
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
  update.bat           Windows updater (updates deps only)
  update.sh            Mac/Linux updater
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
- Firewall prompt: Click "Cancel" or "Block" — the app works on localhost
  only and does not need network access
- Dependencies fail to install: Run update.bat to retry dependency installation

================================================================================
CONTAM MODEL REQUIREMENTS & BUILDING NOTES
================================================================================

Zone Naming Conventions:
  For the auto-populate feature to work correctly, your CONTAM model should use
  consistent zone names across levels. Recommended conventions:

  - Stair zones:    Stair1, Stair2, Stair3, etc.
  - Vestibule zones: Stair1_V, Stair2_V, Stair3_V, etc.
  - Floor depressurization zones: Use a DISTINCT zone name for the floor zone
    being depressurized, e.g., "EXH.Floor" or "Floor_EXH". This zone must exist
    on every level where floor depressurization is configured.
  - Corridor depressurization zones: Use a distinct name like "EXH.Corridor"
    or "Corridor_EXH".
  - Leakage path element: Use "FLR.LK" for floor-above/floor-below leakage
    path elements (used to measure dP between floors).

Auto-Populate Feature Notes:
  The "Auto-Populate by Zone Name" button:
  - Finds zones matching the given name across all levels
  - Auto-assigns the zone ID for each level
  - Auto-assigns AHS (AHS#1 Supply for stairs, AHS#2 Return for corridors/floors)
  - Auto-places the supply/return icon to the LEFT of the zone icon, checking
    for collisions with existing icons
  - NOTE: Col/Row placement requires the PRJ file path to be set in Tab 2 first

  If auto-populate cannot find a matching zone name, no zone will be assigned
  and those levels will be SKIPPED during analysis. You can manually select
  zones from the dropdown for each level.

AHS Systems:
  The tool automatically creates AHS systems in the modified PRJ files:
  - AHS #1: SUPPLY — used for stair pressurization
  - AHS #2: RETURN — used for corridor and floor depressurization
  You do NOT need to create AHS systems in your base CONTAM model.

Flow Element Naming Conventions (for auto-population of Airflow Paths):
  The tool auto-detects path elements using these naming patterns:
  - Stair-to-Vestibule (S2V): Door-{StairName}-S2V
  - Vestibule-to-Corridor (V2C): Door-{StairName}-V2C  
  - Stair-to-Exterior (EXT): Door-{StairName}-EXT
  - Stair-to-Corridor direct (S2C): Door-{StairName}-S2C
    (S2C is used as fallback for S2V when no vestibule exists)

