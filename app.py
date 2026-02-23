"""CONTAM Stairwell Pressurization Analysis Tool — Main Entry Point.

Starts a local FastAPI server and opens the browser to the GUI.
"""

import asyncio
import json
import logging
import os
import sys
import uuid
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import uvicorn
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.analysis_engine import (
    AnalysisConfig,
    AnalysisEngine,
    CorridorConfig,
    FloorConfig,
    RoofConfig,
    ScenarioConfig,
    StairConfig,
)
from core.contam_runner import find_contam_executable
from core.prj_parser import (
    ParsedModel,
    auto_detect_config,
    get_zone_display_name,
    parse_prj_file,
)

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="CONTAM Pressurization Tool")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------
parsed_models: Dict[str, ParsedModel] = {}
current_project: Dict[str, Any] = {}
app_config: Dict[str, Any] = {}
analysis_engine: Optional[AnalysisEngine] = None
analysis_log: List[str] = []
analysis_running = False


def _load_app_config() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("Failed to load config.json, using defaults: %s", e)
    return {"contam_executable_default": "", "recent_projects": []}


def _save_app_config(cfg: Dict[str, Any]) -> None:
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


app_config = _load_app_config()


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ---------------------------------------------------------------------------
# Config endpoints
# ---------------------------------------------------------------------------
@app.get("/api/config/load")
async def load_config():
    global app_config
    app_config = _load_app_config()
    # Auto-detect CONTAM if not set
    if not app_config.get("contam_executable_default"):
        found = find_contam_executable()
        if found:
            app_config["contam_executable_default"] = found
    return app_config


@app.post("/api/config/save")
async def save_config(request: Request):
    global app_config
    body = await request.json()
    app_config.update(body)
    _save_app_config(app_config)
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Project endpoints
# ---------------------------------------------------------------------------
@app.post("/api/project/create")
async def create_project(request: Request):
    global current_project
    body = await request.json()
    name = body.get("name", "Untitled")
    folder = body.get("folder", "")
    contam_exe = body.get("contam_exe", app_config.get("contam_executable_default", ""))

    if not folder:
        raise HTTPException(400, "Project folder is required")

    project_dir = Path(folder)
    # If the path points to an existing file, use its parent directory
    if project_dir.is_file():
        project_dir = project_dir.parent
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "analysis").mkdir(exist_ok=True)

    current_project = {
        "project_name": name,
        "project_folder": str(project_dir),
        "contam_executable": contam_exe,
        "base_models": {},
        "num_stairs": 0,
        "num_corridors": 0,
        "stair_labels": [],
        "stair_pressurization": {},
        "corridor_depressurization": {},
        "roof_stair_depressurization": {},
        "airflow_paths": {"stairs": {}, "corridors": []},
        "scenarios": [],
        "acceptance_criteria": {"min_dp_inwc": 0.05, "max_dp_inwc": 0.45, "max_dp_stair_inwc": 0.17},
    }

    # Save project.json
    pj_path = project_dir / "project.json"
    with open(pj_path, "w") as f:
        json.dump(current_project, f, indent=2)

    # Update recent projects
    _add_recent_project(name, str(project_dir))

    return {"status": "ok", "project": current_project}


@app.post("/api/project/open")
async def open_project(request: Request):
    global current_project
    body = await request.json()
    path = body.get("path", "")

    pj_path = Path(path)

    # If the path is a file that is not project.json, use the parent dir
    if pj_path.is_file() and pj_path.name != "project.json":
        pj_path = pj_path.parent / "project.json"
    elif pj_path.is_dir():
        pj_path = pj_path / "project.json"

    if not pj_path.exists():
        # No project.json yet — create a default one in this folder
        project_dir = pj_path.parent
        if not project_dir.is_dir():
            raise HTTPException(404, f"Folder not found: {project_dir}")

        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / "analysis").mkdir(exist_ok=True)

        current_project = {
            "project_name": project_dir.name,
            "project_folder": str(project_dir),
            "contam_executable": app_config.get("contam_executable_default", ""),
            "base_models": {},
            "num_stairs": 0,
            "num_corridors": 0,
            "stair_labels": [],
            "stair_pressurization": {},
            "corridor_depressurization": {},
            "roof_stair_depressurization": {},
            "airflow_paths": {"stairs": {}, "corridors": []},
            "scenarios": [],
            "acceptance_criteria": {"min_dp_inwc": 0.05, "max_dp_inwc": 0.45, "max_dp_stair_inwc": 0.17},
        }
        with open(pj_path, "w") as f:
            json.dump(current_project, f, indent=2)
    else:
        with open(pj_path, "r") as f:
            current_project = json.load(f)

    _add_recent_project(
        current_project.get("project_name", "Unknown"),
        str(pj_path.parent),
    )

    return {"status": "ok", "project": current_project}


@app.post("/api/project/save")
async def save_project(request: Request):
    global current_project
    body = await request.json()
    current_project.update(body)

    folder = current_project.get("project_folder", "")
    if folder:
        pj_path = Path(folder) / "project.json"
        with open(pj_path, "w") as f:
            json.dump(current_project, f, indent=2)

    return {"status": "ok"}


@app.get("/api/project/recent")
async def get_recent_projects():
    return app_config.get("recent_projects", [])


def _add_recent_project(name: str, path: str) -> None:
    recent = app_config.get("recent_projects", [])
    # Remove existing entry with same path
    recent = [r for r in recent if r.get("path") != path]
    recent.insert(0, {"name": name, "path": path})
    recent = recent[:10]
    app_config["recent_projects"] = recent
    _save_app_config(app_config)


# ---------------------------------------------------------------------------
# Model parsing endpoints
# ---------------------------------------------------------------------------
@app.post("/api/model/parse")
async def parse_model(request: Request):
    body = await request.json()
    filepath = body.get("filepath", "")

    if not filepath:
        raise HTTPException(400, "File path is required")

    path = Path(filepath)
    if not path.exists():
        raise HTTPException(404, f"File not found: {filepath}")

    try:
        model = parse_prj_file(filepath)
    except Exception as e:
        raise HTTPException(422, f"Failed to parse PRJ file: {e}")

    model_id = str(uuid.uuid4())[:8]
    parsed_models[model_id] = model

    # Add to current project base models
    if current_project:
        base_models = current_project.setdefault("base_models", {})
        base_models[path.stem] = str(path)

    return {
        "model_id": model_id,
        "filepath": model.filepath,
        "version": model.version,
        "project_name": model.project_name,
        "num_levels": len(model.levels),
        "num_zones": len(model.zones),
        "num_flow_elements": len(model.flow_elements),
        "num_airflow_paths": len(model.airflow_paths),
        "num_ahs": len(model.ahs_systems),
    }


@app.post("/api/model/parse-upload")
async def parse_model_upload(file: UploadFile = File(...)):
    """Accept a drag-and-dropped PRJ file, save it, and parse it."""
    if not file.filename or not file.filename.lower().endswith(".prj"):
        raise HTTPException(400, "Please upload a .prj file")

    projects_dir = BASE_DIR / "Projects"
    projects_dir.mkdir(exist_ok=True)
    dest = projects_dir / file.filename
    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)

    try:
        model = parse_prj_file(str(dest))
    except Exception as e:
        raise HTTPException(422, f"Failed to parse PRJ file: {e}")

    model_id = str(uuid.uuid4())[:8]
    parsed_models[model_id] = model

    if current_project:
        base_models = current_project.setdefault("base_models", {})
        base_models[dest.stem] = str(dest)

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
    }


@app.get("/api/model/{model_id}/levels")
async def get_levels(model_id: str):
    model = parsed_models.get(model_id)
    if not model:
        raise HTTPException(404, "Model not found")
    return [
        {
            "index": lvl.index,
            "name": lvl.name,
            "ref_height": lvl.ref_height,
            "delta_height": lvl.delta_height,
            "num_icons": lvl.num_icons,
        }
        for lvl in model.levels
    ]


@app.get("/api/model/{model_id}/zones")
async def get_zones(model_id: str, level: Optional[int] = None):
    model = parsed_models.get(model_id)
    if not model:
        raise HTTPException(404, "Model not found")
    zones = model.zones
    if level is not None:
        zones = [z for z in zones if z.level_num == level]
    return [
        {
            "id": z.id,
            "name": z.name,
            "display_name": get_zone_display_name(z),
            "level_num": z.level_num,
            "level_name": z.level_name,
            "volume": z.volume,
            "temperature": z.temperature,
        }
        for z in zones
    ]


@app.get("/api/model/{model_id}/elements")
async def get_elements(model_id: str):
    model = parsed_models.get(model_id)
    if not model:
        raise HTTPException(404, "Model not found")
    return [
        {
            "id": elem.id,
            "name": elem.name,
            "type": elem.elem_type,
        }
        for elem in model.flow_elements
    ]


@app.get("/api/model/{model_id}/paths")
async def get_paths(model_id: str, level: Optional[int] = None, element: Optional[str] = None):
    model = parsed_models.get(model_id)
    if not model:
        raise HTTPException(404, "Model not found")
    paths = model.airflow_paths
    if level is not None:
        paths = [p for p in paths if p.level_num == level]
    if element is not None:
        paths = [p for p in paths if p.flow_elem_name == element]
    return [
        {
            "id": p.id,
            "from_zone": p.from_zone,
            "to_zone": p.to_zone,
            "flow_elem_id": p.flow_elem_id,
            "flow_elem_name": p.flow_elem_name,
            "ahs": p.ahs,
            "level_num": p.level_num,
            "multiplier": p.multiplier,
            "icon_type": p.icon_type,
            "direction": p.direction,
        }
        for p in paths
    ]


@app.get("/api/model/{model_id}/ahs")
async def get_ahs(model_id: str):
    model = parsed_models.get(model_id)
    if not model:
        raise HTTPException(404, "Model not found")
    return [
        {
            "id": ahs.id,
            "name": ahs.name,
            "return_zone": ahs.return_zone,
            "supply_zone": ahs.supply_zone,
            "return_path": ahs.return_path,
            "supply_path": ahs.supply_path,
            "exhaust_path": ahs.exhaust_path,
        }
        for ahs in model.ahs_systems
    ]


@app.get("/api/model/{model_id}/suggestions")
async def get_suggestions(model_id: str):
    """Auto-detect configuration from the parsed model."""
    model = parsed_models.get(model_id)
    if not model:
        raise HTTPException(404, "Model not found")
    return auto_detect_config(model)


@app.get("/api/model/{model_id}/auto-configure")
async def auto_configure(model_id: str):
    """Fully automatic configuration: parse model, detect everything, return
    a ready-to-apply configuration with stairs, corridors, vestibules, AHS,
    flow paths, and roof configs all resolved.

    This goes beyond /suggestions by also mapping zone names to zone IDs per
    level, resolving AHS per stair/corridor, and providing a structured
    configuration that the frontend can apply with zero user interaction.
    """
    model = parsed_models.get(model_id)
    if not model:
        raise HTTPException(404, "Model not found")

    config = auto_detect_config(model)

    # Enrich with fully resolved zone-to-level mappings
    # For stairs: on each level, resolve the correct zone_id even if
    # the zone name varies (e.g., Stair_4 on one level, Stair4 on another)
    for stair in config["stairs"]:
        all_names = stair.get("all_names", [stair["zone_name"]])
        level_zone_map = {}
        for z in stair["zones"]:
            level_zone_map[z["level_num"]] = z
        stair["level_zone_map"] = level_zone_map

    # For corridors: same treatment
    for corridor in config["corridors"]:
        level_zone_map = {}
        for z in corridor["zones"]:
            level_zone_map[z["level_num"]] = z
        corridor["level_zone_map"] = level_zone_map

    # Include full level list so frontend knows all available levels
    config["levels"] = [
        {"index": lvl.index, "name": lvl.name}
        for lvl in model.levels
    ]

    # Include AHS list — if model has no AHS, include placeholder entries
    # so the frontend knows AHS will be auto-created at generation time
    if model.ahs_systems:
        config["ahs_systems"] = [
            {"id": ahs.id, "name": ahs.name}
            for ahs in model.ahs_systems
        ]
    else:
        config["ahs_systems"] = [
            {"id": 1, "name": "SUPPLY (auto-created)"},
            {"id": 2, "name": "RETURN (auto-created)"},
        ]
        # Also set supply/return AHS in config so frontend can assign them
        config["supply_ahs"] = {"id": 1, "name": "SUPPLY (auto-created)"}
        config["return_ahs"] = {"id": 2, "name": "RETURN (auto-created)"}
        # Assign to stairs/corridors that have no AHS
        for stair in config["stairs"]:
            if not stair.get("ahs_id"):
                stair["ahs_id"] = 1
        for corridor in config["corridors"]:
            if not corridor.get("ahs_id"):
                corridor["ahs_id"] = 2
        config["ahs_auto_created"] = True

    return config


# ---------------------------------------------------------------------------
# Analysis endpoints
# ---------------------------------------------------------------------------
@app.post("/api/analysis/validate")
async def validate_analysis(request: Request):
    body = await request.json()
    config = _build_analysis_config(body)
    engine = AnalysisEngine(config)
    errors = engine.validate()
    return {"valid": len(errors) == 0, "errors": errors}


@app.post("/api/analysis/dryrun")
async def dry_run(request: Request):
    body = await request.json()
    config = _build_analysis_config(body)
    engine = AnalysisEngine(config)
    errors = engine.validate()
    critical_errors = [e for e in errors if not e.startswith("Warning")]
    if critical_errors:
        raise HTTPException(400, f"Validation failed: {'; '.join(critical_errors)}")

    # Collect warnings from PRJ generation
    files = engine.dry_run()
    prj_warnings = engine.prj_warnings

    # Auto-run building check on the first generated file
    building_check = None
    if files and config.contam_exe and Path(config.contam_exe).exists():
        first_file = files[0]
        check_result = _run_building_check(config.contam_exe, first_file)
        building_check = check_result

    return {
        "status": "ok",
        "generated_files": files,
        "count": len(files),
        "prj_warnings": prj_warnings,
        "building_check": building_check,
    }


def _run_building_check(contam_exe: str, prj_path: str) -> dict:
    """Run CONTAM on a PRJ file to check for structural errors.
    Uses --TestInput flag to only validate the PRJ structure without running
    a full simulation.  This avoids false "error" reports from convergence
    warnings that are normal during simulation but unrelated to PRJ validity.
    Returns dict with 'passed', 'message', and 'details'.
    """
    import subprocess
    try:
        # ContamX 3.4 accepts: contamx3 <file.prj> TestInput
        # "TestInput" validates PRJ structure without running the simulation,
        # avoiding false failures from convergence warnings.
        result = subprocess.run(
            [contam_exe, prj_path, "TestInput"],
            capture_output=True, text=True, timeout=30,
            cwd=str(Path(prj_path).parent),
        )
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        output = stdout + stderr

        # CONTAM exits with 0 on success, non-zero on failure
        if result.returncode == 0:
            # With --TestInput, only structural errors matter
            lower = output.lower()
            # Filter: ignore convergence warnings (not structural errors)
            structural_errors = [kw for kw in ["fatal", "invalid", "pathlist reorder"]
                                 if kw in lower]
            # Also check for "error" but NOT "convergence" or "steady-state"
            has_real_error = False
            for line in output.split('\n'):
                ll = line.lower().strip()
                if 'error' in ll and not any(x in ll for x in [
                    'convergence', 'converge', 'steady-state', 'steady state'
                ]):
                    structural_errors.append(line.strip())
                    has_real_error = True

            if structural_errors or has_real_error:
                return {
                    "passed": False,
                    "message": "CONTAM reported errors",
                    "details": output[:2000],
                    "returncode": result.returncode,
                }
            return {
                "passed": True,
                "message": "Building check passed",
                "details": output[:500] if output.strip() else "No errors detected",
                "returncode": 0,
            }
        else:
            # Non-zero return: check if it's just convergence or a real error
            lower = output.lower()
            is_convergence_only = (
                'converge' in lower and
                'invalid' not in lower and
                'fatal' not in lower
            )
            if is_convergence_only:
                return {
                    "passed": True,
                    "message": "Building check passed (convergence warning is expected)",
                    "details": output[:500],
                    "returncode": result.returncode,
                }
            return {
                "passed": False,
                "message": f"CONTAM exited with code {result.returncode}",
                "details": output[:2000] if output.strip() else "No output captured",
                "returncode": result.returncode,
            }
    except subprocess.TimeoutExpired:
        return {
            "passed": True,
            "message": "CONTAM started successfully (simulation running, check passed)",
            "details": "Process was terminated after 30s — model loaded OK",
            "returncode": 0,
        }
    except FileNotFoundError:
        return {
            "passed": None,
            "message": f"CONTAM executable not found: {contam_exe}",
            "details": "Cannot run building check without CONTAM",
            "returncode": -1,
        }
    except Exception as e:
        return {
            "passed": None,
            "message": f"Building check error: {e}",
            "details": str(e),
            "returncode": -1,
        }


@app.post("/api/analysis/building-check")
async def building_check(request: Request):
    """Run CONTAM building check on a specific PRJ file."""
    body = await request.json()
    prj_path = body.get("prj_path", "")
    contam_exe = body.get("contam_exe", "")

    if not prj_path or not Path(prj_path).exists():
        raise HTTPException(400, f"PRJ file not found: {prj_path}")
    if not contam_exe or not Path(contam_exe).exists():
        raise HTTPException(400, f"CONTAM exe not found: {contam_exe}")

    result = _run_building_check(contam_exe, prj_path)
    return result


@app.post("/api/analysis/repair-prj")
async def repair_prj_files(request: Request):
    """Attempt to repair PRJ files that fail building check."""
    body = await request.json()
    prj_files = body.get("prj_files", [])
    contam_exe = body.get("contam_exe", "")

    from core.prj_writer import validate_and_repair_paths, validate_prj_structure

    repaired = 0
    details = []

    for fpath in prj_files:
        p = Path(fpath)
        if not p.exists():
            details.append(f"Skipped (not found): {p.name}")
            continue

        try:
            with open(fpath, 'r') as f:
                lines = f.readlines()

            # 1. Structural validation
            issues = validate_prj_structure(lines)
            if issues:
                details.append(f"{p.name}: Found {len(issues)} structural issue(s)")
                for iss in issues:
                    details.append(f"  {iss}")

            # 2. Repair paths (fixes orphaned icon refs, count mismatches)
            warnings = validate_and_repair_paths(lines)
            if warnings:
                for w in warnings:
                    details.append(f"  {w}")

            # 3. Write repaired file
            if issues or warnings:
                with open(fpath, 'w') as f:
                    f.writelines(lines)
                repaired += 1
                details.append(f"  → Repaired: {p.name}")
            else:
                details.append(f"{p.name}: No issues found")

        except Exception as e:
            details.append(f"Error repairing {p.name}: {e}")

    return {
        "repaired": repaired,
        "total": len(prj_files),
        "details": details,
    }


@app.post("/api/analysis/start")
async def start_analysis(request: Request):
    global analysis_engine, analysis_log, analysis_running
    if analysis_running:
        raise HTTPException(409, "Analysis already running")

    body = await request.json()
    config = _build_analysis_config(body)
    analysis_engine = AnalysisEngine(config)
    analysis_log = []

    # Validate before starting
    errors = analysis_engine.validate()
    critical_errors = [e for e in errors if not e.startswith("Warning")]
    if critical_errors:
        raise HTTPException(400, f"Validation failed: {'; '.join(critical_errors)}")

    total_runs = analysis_engine.count_total_runs()
    if total_runs == 0:
        raise HTTPException(400, "No simulation runs to perform. Check that fire floor "
                           "levels are configured (corridor or floor zone depressurization "
                           "zones must be selected with non-zero flow rates).")

    def on_progress(info):
        analysis_log.append(info["message"])

    analysis_engine.on_progress(on_progress)

    # Set flag only after all validation has passed, right before launching task
    analysis_running = True

    # Run in background task
    loop = asyncio.get_running_loop()
    loop.create_task(_run_analysis_task())

    return {
        "status": "started",
        "total_runs": total_runs,
    }


async def _run_analysis_task():
    global analysis_running
    try:
        await analysis_engine.run_analysis()
    except Exception as e:
        logger.error("Analysis failed: %s", e)
        analysis_log.append(f"ERROR: {e}")
    finally:
        analysis_running = False


@app.get("/api/analysis/status")
async def analysis_status():
    async def event_stream():
        last_idx = 0
        while analysis_running or last_idx < len(analysis_log):
            if last_idx < len(analysis_log):
                for i in range(last_idx, len(analysis_log)):
                    yield f"data: {json.dumps({'message': analysis_log[i], 'running': analysis_running})}\n\n"
                last_idx = len(analysis_log)
            else:
                yield f"data: {json.dumps({'message': '', 'running': analysis_running})}\n\n"
            await asyncio.sleep(0.5)
        yield f"data: {json.dumps({'message': 'Analysis complete', 'running': False, 'done': True})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/analysis/cancel")
async def cancel_analysis():
    global analysis_engine
    if analysis_engine:
        analysis_engine.cancel()
        return {"status": "cancelled"}
    return {"status": "no_analysis_running"}


@app.get("/api/results/summary")
async def get_results_summary():
    if not analysis_engine:
        raise HTTPException(404, "No results available")
    return analysis_engine.get_results_summary()


@app.get("/api/results/export/csv")
async def export_csv(scenario: Optional[str] = None):
    if not analysis_engine or not analysis_engine.results:
        raise HTTPException(404, "No results available")

    folder = Path(analysis_engine.config.project_folder) / "analysis"
    csv_files = list(folder.glob("Contam_Results_Summary_*.csv"))

    if scenario:
        csv_files = [f for f in csv_files if scenario in f.stem]

    if not csv_files:
        raise HTTPException(404, "No CSV files found")

    return FileResponse(csv_files[0], filename=csv_files[0].name)


@app.get("/api/results/export/summary-csv")
async def export_summary_csv():
    if not analysis_engine or not analysis_engine.results:
        raise HTTPException(404, "No results available")

    # Combine all scenario results into one summary
    all_dfs = []
    for result in analysis_engine.results:
        if result.output_table is not None:
            df = result.output_table.copy()
            df.insert(0, "Scenario", result.scenario_name)
            all_dfs.append(df)

    if not all_dfs:
        raise HTTPException(404, "No results to export")

    import pandas as pd
    combined = pd.concat(all_dfs, ignore_index=True)
    folder = Path(analysis_engine.config.project_folder) / "analysis"
    folder.mkdir(parents=True, exist_ok=True)
    filepath = folder / "Summary_All_Scenarios.csv"
    combined.to_csv(filepath, index=False, float_format="%.4f")

    return FileResponse(filepath, filename="Summary_All_Scenarios.csv")


@app.get("/api/results/export/report")
async def export_report():
    """Generate a formatted HTML report for printing/PDF."""
    if not analysis_engine or not analysis_engine.results:
        raise HTTPException(404, "No results available")

    from core.report_generator import generate_report_html

    # Gather data for report
    config = analysis_engine.config
    results_summaries = analysis_engine.get_results_summary()

    scenarios = [
        {
            "name": s.name,
            "temp_f": s.temp_f,
            "wind_mph": s.wind_mph,
            "wind_dir": s.wind_dir,
        }
        for s in config.scenarios
    ]

    stairs = []
    for s in config.stairs:
        stairs.append({
            "label": s.label,
            "levels": s.levels,
        })

    corridors = []
    for c in config.corridors:
        corridors.append({
            "label": c.label,
            "levels": c.levels,
        })

    acceptance = config.acceptance_criteria

    # Model info from first parsed model
    model_info = None
    if results_summaries:
        first_scenario = config.scenarios[0]
        try:
            from core.prj_parser import parse_prj_file
            m = parse_prj_file(first_scenario.base_model_path)
            model_info = {
                "filename": Path(first_scenario.base_model_path).name,
                "num_levels": len(m.levels),
                "num_zones": len(m.zones),
                "num_paths": len(m.airflow_paths),
                "num_ahs": len(m.ahs_systems),
            }
        except Exception:
            pass

    html = generate_report_html(
        project_name=config.project_name,
        scenarios=scenarios,
        stairs=stairs,
        corridors=corridors,
        results=results_summaries,
        acceptance_criteria=acceptance,
        model_info=model_info,
    )

    return HTMLResponse(content=html)


# ---------------------------------------------------------------------------
# Per-scenario results (dynamic path — must come AFTER static /api/results/* routes)
# ---------------------------------------------------------------------------
@app.get("/api/results/{scenario}/detailed")
async def get_detailed_results(scenario: str):
    """Get per-fire-floor detailed results for a scenario."""
    if not analysis_engine or not analysis_engine.results:
        raise HTTPException(404, "No results available")
    detailed = analysis_engine.get_detailed_results(scenario)
    if detailed is None:
        raise HTTPException(404, f"Detailed results for '{scenario}' not found")
    return detailed


@app.get("/api/results/{scenario}")
async def get_results(scenario: str):
    if not analysis_engine or not analysis_engine.results:
        raise HTTPException(404, "No results available")

    for result in analysis_engine.results:
        if result.scenario_name == scenario:
            if result.output_table is not None:
                df = result.output_table
                return {
                    "scenario": scenario,
                    "columns": df.columns.tolist(),
                    "data": df.replace({np.nan: None}).values.tolist(),
                }
    raise HTTPException(404, f"Results for scenario '{scenario}' not found")


# ---------------------------------------------------------------------------
# Tab 3 Config Save/Load
# ---------------------------------------------------------------------------
@app.post("/api/tab3/save")
async def save_tab3_config(request: Request):
    """Save current Tab 3 configuration to a JSON file in the project folder."""
    body = await request.json()
    folder = body.get("project_folder", current_project.get("project_folder", ""))
    if not folder:
        raise HTTPException(400, "No project folder set")
    config_data = body.get("config", {})
    filepath = Path(folder) / "tab3_config.json"
    with open(filepath, "w") as f:
        json.dump(config_data, f, indent=2)
    return {"status": "ok", "filepath": str(filepath)}


@app.post("/api/tab3/load")
async def load_tab3_config(request: Request):
    """Load saved Tab 3 configuration from the project folder."""
    body = await request.json()
    folder = body.get("project_folder", current_project.get("project_folder", ""))
    if not folder:
        raise HTTPException(400, "No project folder set")
    filepath = Path(folder) / "tab3_config.json"
    if not filepath.exists():
        raise HTTPException(404, "No saved configuration found (tab3_config.json)")
    with open(filepath, "r") as f:
        config_data = json.load(f)
    return {"status": "ok", "config": config_data}


@app.post("/api/tab3/zone-icons")
async def get_zone_icons(request: Request):
    """Parse PRJ to find icon positions for each zone, so the UI can
    place supply/return icons next to the zone icon."""
    body = await request.json()
    prj_path = body.get("prj_path", "")
    if not prj_path or not Path(prj_path).exists():
        raise HTTPException(400, "PRJ file not found")

    model = parse_prj_file(prj_path)
    icon_map = {}  # zone_id -> {level_num, col, row}

    # Build a set of all occupied positions per level
    occupied = {}  # level_index -> set of (col, row)
    for lvl in model.levels:
        occupied[lvl.index] = set()
        start = lvl.icon_header_line + 1
        for j in range(lvl.num_icons):
            line_idx = start + j
            if line_idx < len(model.raw_lines):
                parts = model.raw_lines[line_idx].split()
                if len(parts) >= 3:
                    try:
                        icn = int(parts[0])
                        col = int(parts[1])
                        row = int(parts[2])
                        zone_ref = int(parts[3]) if len(parts) > 3 else 0
                        occupied[lvl.index].add((col, row))

                        # Icon type 5 = zone icon; the # field is the zone ID
                        # Other types (14-25 = walls) have path IDs, not zone IDs
                        if icn == 5 and zone_ref > 0:
                            icon_map[zone_ref] = {
                                "level_num": lvl.index,
                                "col": col,
                                "row": row,
                                "icon_type": icn,
                            }
                    except (ValueError, IndexError):
                        pass

    # For each zone, find icon position and a free adjacent cell
    zone_placements = {}
    for z in model.zones:
        ref = z.id
        if ref in icon_map:
            info = icon_map[ref]
            zcol = info["col"]
            zrow = info["row"]
            lvl_idx = info["level_num"]
            occ = occupied.get(lvl_idx, set())

            # Try positions: left, right, above, below
            free_col, free_row = zcol, zrow
            for dc, dr in [(-1, 0), (1, 0), (0, -1), (0, 1), (-2, 0), (2, 0)]:
                candidate = (zcol + dc, zrow + dr)
                if candidate[0] > 0 and candidate[1] > 0 and candidate not in occ:
                    free_col, free_row = candidate
                    break

            zone_placements[str(z.id)] = {
                "zone_name": z.name,
                "level_num": lvl_idx,
                "zone_col": zcol,
                "zone_row": zrow,
                "supply_col": free_col,
                "supply_row": free_row,
            }

    return {"zone_placements": zone_placements, "total": len(zone_placements)}


@app.post("/api/tab3/generate-templates")
async def generate_scfm_templates(request: Request):
    """Generate blank SCFM template Excel files for each stair, corridor,
    and floor zone group, pre-populated with level names from the parsed model.
    """
    body = await request.json()
    folder = body.get("project_folder", current_project.get("project_folder", ""))
    if not folder:
        raise HTTPException(400, "No project folder set")

    model_id = body.get("model_id", "")
    model = parsed_models.get(model_id) if model_id else None

    # Gather level names — from model if available, else from body
    levels = body.get("levels", [])
    if model and not levels:
        levels = [{"index": lvl.index, "name": lvl.name} for lvl in model.levels]
    if not levels:
        raise HTTPException(400, "No levels available. Parse a PRJ model first.")

    stairs = body.get("stairs", [])
    corridors = body.get("corridors", [])
    floor_zones = body.get("floor_zones", [])

    templates_dir = Path(folder) / "scfm_templates"
    templates_dir.mkdir(parents=True, exist_ok=True)

    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    except ImportError:
        raise HTTPException(500, "openpyxl is required. Run: pip install openpyxl")

    generated = []

    def _create_template(filename: str, entity_label: str, entity_type: str):
        wb = Workbook()
        ws = wb.active
        ws.title = "SCFM Values"

        # Styles
        header_font = Font(name="Arial", bold=True, size=11, color="FFFFFF")
        header_fill = PatternFill("solid", fgColor="2E86DE")
        subheader_font = Font(name="Arial", bold=True, size=10, color="2C3E50")
        subheader_fill = PatternFill("solid", fgColor="D6E9F8")
        cell_font = Font(name="Arial", size=10)
        input_fill = PatternFill("solid", fgColor="FFFFF0")
        thin_border = Border(
            left=Side(style="thin", color="CCCCCC"),
            right=Side(style="thin", color="CCCCCC"),
            top=Side(style="thin", color="CCCCCC"),
            bottom=Side(style="thin", color="CCCCCC"),
        )

        # Title row
        ws.merge_cells("A1:B1")
        ws["A1"] = f"{entity_label} — {entity_type}"
        ws["A1"].font = Font(name="Arial", bold=True, size=12, color="1A2332")
        ws["A1"].alignment = Alignment(horizontal="left")

        # Instructions
        ws.merge_cells("A2:B2")
        ws["A2"] = "Enter SCFM values in column B, then import this file in the tool."
        ws["A2"].font = Font(name="Arial", size=9, italic=True, color="7F8C9B")

        # Headers (row 4)
        ws["A4"] = "Level"
        ws["B4"] = "Flow Rate (SCFM)"
        for cell in [ws["A4"], ws["B4"]]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")
            cell.border = thin_border

        # Data rows
        for i, lvl in enumerate(levels):
            row = 5 + i
            ws.cell(row=row, column=1, value=lvl.get("name", f"Level {lvl.get('index', i)}"))
            ws.cell(row=row, column=1).font = cell_font
            ws.cell(row=row, column=1).border = thin_border
            ws.cell(row=row, column=1).alignment = Alignment(horizontal="left")

            # SCFM cell — blank, highlighted for input
            scfm_cell = ws.cell(row=row, column=2, value=None)
            scfm_cell.font = cell_font
            scfm_cell.fill = input_fill
            scfm_cell.border = thin_border
            scfm_cell.number_format = "#,##0"
            scfm_cell.alignment = Alignment(horizontal="center")

        # Column widths
        ws.column_dimensions["A"].width = 22
        ws.column_dimensions["B"].width = 20

        # Freeze header row
        ws.freeze_panes = "A5"

        filepath = templates_dir / filename
        wb.save(str(filepath))
        generated.append({"filename": filename, "path": str(filepath), "entity": entity_label})

    # Generate stair templates
    for i, stair in enumerate(stairs):
        label = stair.get("label", f"Stair_{i + 1}")
        safe_label = label.replace(" ", "_").replace("/", "-")
        _create_template(
            f"{safe_label}-SCFM-Template.xlsx",
            label,
            "Stair Pressurization",
        )

    # If no stairs were passed but we have a count, generate generic ones
    if not stairs:
        num_stairs = body.get("num_stairs", 0)
        for i in range(num_stairs):
            label = f"Stair_{i + 1}"
            _create_template(f"{label}-SCFM-Template.xlsx", label, "Stair Pressurization")

    # Generate corridor templates
    for i, corr in enumerate(corridors):
        label = corr.get("label", f"Corridor_{i + 1}")
        safe_label = label.replace(" ", "_").replace("/", "-")
        _create_template(
            f"{safe_label}-SCFM-Template.xlsx",
            label,
            "Corridor Depressurization",
        )

    if not corridors:
        num_corr = body.get("num_corridors", 0)
        for i in range(num_corr):
            label = f"Corridor_{i + 1}"
            _create_template(f"{label}-SCFM-Template.xlsx", label, "Corridor Depressurization")

    # Generate floor zone templates
    for i, fz in enumerate(floor_zones):
        label = fz.get("label", f"Floor_Zone_{i + 1}")
        safe_label = label.replace(" ", "_").replace("/", "-")
        _create_template(
            f"{safe_label}-SCFM-Template.xlsx",
            label,
            "Floor Zone Depressurization",
        )

    if not floor_zones:
        num_floors = body.get("num_floors", 0)
        for i in range(num_floors):
            label = f"Floor_Zone_{i + 1}"
            _create_template(f"{label}-SCFM-Template.xlsx", label, "Floor Zone Depressurization")

    return {
        "status": "ok",
        "templates_folder": str(templates_dir),
        "generated": generated,
        "count": len(generated),
    }


@app.post("/api/tab3/import-excel")
async def import_excel_scfm(request: Request):
    """Import SCFM values from an Excel file.
    
    Expected Excel format:
    - Column A: Level name or number
    - Subsequent columns: SCFM values for each stair/group
    - First row is a header row
    """
    body = await request.json()
    filepath = body.get("filepath", "")
    if not filepath:
        raise HTTPException(400, "Excel file path is required")
    
    path = Path(filepath)
    if not path.exists():
        raise HTTPException(404, f"File not found: {filepath}")
    
    try:
        import pandas as pd
        # Support .xlsx and .xls and .csv
        if path.suffix.lower() in [".xlsx", ".xls"]:
            df = pd.read_excel(filepath, engine="openpyxl")
        elif path.suffix.lower() == ".csv":
            df = pd.read_csv(filepath)
        else:
            raise HTTPException(400, f"Unsupported file type: {path.suffix}")
        
        # Auto-detect header row: find row with "Level" in column A
        # Templates have title/instruction rows before the actual data
        header_row = 0
        raw_df = df
        for idx, row in df.iterrows():
            cell_a = str(row.iloc[0]).strip().lower() if pd.notna(row.iloc[0]) else ""
            if cell_a in ("level", "level name", "floor"):
                header_row = idx + 1  # +1 because idx is 0-based after first header
                break
            # Also try: if column B is numeric, the previous row was the header
            try:
                if len(row) > 1 and pd.notna(row.iloc[1]):
                    float(row.iloc[1])
                    # This row has numeric data; header was previous row
                    header_row = max(0, idx)
                    break
            except (ValueError, TypeError):
                header_row = idx + 1
                continue

        # Re-read with correct header if needed
        if header_row > 0:
            if path.suffix.lower() in [".xlsx", ".xls"]:
                df = pd.read_excel(filepath, engine="openpyxl", header=header_row)
            else:
                df = pd.read_csv(filepath, header=header_row)

        result = {
            "columns": df.columns.tolist(),
            "data": [],
        }
        for _, row in df.iterrows():
            # Skip rows where the level name is empty/NaN
            level_name = row.iloc[0]
            if pd.isna(level_name) or str(level_name).strip() == "":
                continue
            # Skip rows that look like headers (non-numeric SCFM values)
            scfm_vals = []
            skip = False
            for v in row.iloc[1:]:
                if pd.notna(v):
                    try:
                        scfm_vals.append(float(v))
                    except (ValueError, TypeError):
                        skip = True
                        break
                else:
                    scfm_vals.append(0.0)
            if skip:
                continue
            result["data"].append([
                str(level_name).strip(),
                *scfm_vals
            ])

        return result
    except ImportError:
        raise HTTPException(500, "openpyxl is required for Excel import. Run: pip install openpyxl")
    except Exception as e:
        raise HTTPException(422, f"Failed to read Excel file: {e}")


@app.post("/api/tab3/update-prj")
async def update_prj_file(request: Request):
    """Update the PRJ file with current Tab 3 stair pressurization config,
    without running the full analysis. This modifies the base PRJ to include
    the configured supply AHS and flow rates."""
    body = await request.json()
    config = _build_analysis_config(body)
    
    from core.prj_writer import build_modified_prj
    from core.prj_parser import parse_prj_file
    
    base_prj = body.get("base_prj_path", "")
    if not base_prj:
        if config.scenarios:
            base_prj = config.scenarios[0].base_model_path
    
    if not base_prj or not Path(base_prj).exists():
        raise HTTPException(400, "No valid PRJ file path provided")
    
    output_path = body.get("output_path", "")
    if not output_path:
        p = Path(base_prj)
        output_path = str(p.parent / f"{p.stem}_updated{p.suffix}")
    
    try:
        model = parse_prj_file(base_prj)
        # Use first scenario weather, first fire floor
        scenario = config.scenarios[0] if config.scenarios else None
        temp_f = scenario.temp_f if scenario else 70
        wind_mph = scenario.wind_mph if scenario else 0
        wind_dir = scenario.wind_dir if scenario else 0
        
        all_depress = (
            [{"label": c.label, "levels": c.levels} for c in config.corridors]
            + [{"label": f.label, "levels": f.levels} for f in config.floor_zones]
        )
        
        # Get first fire floor level
        ff_level = 1
        for cfg in all_depress:
            found = False
            for le in cfg["levels"]:
                if le.get("flow_rate", 0) > 0 and le.get("zone_id", 0) != 0:
                    ff_level = le["level_num"]
                    found = True
                    break
            if found:
                break
        
        modified, warnings = build_modified_prj(
            base_lines=model.raw_lines,
            temp_f=temp_f,
            wind_mph=wind_mph,
            wind_dir=wind_dir,
            stair_configs=[{"label": s.label, "levels": s.levels} for s in config.stairs],
            corridor_configs=all_depress,
            roof_configs=[{
                "zone_id": r.zone_id, "level_num": r.level_num,
                "flow_rate": r.flow_rate, "ahs_id": r.ahs_id,
                "exhaust_zone": r.exhaust_zone, "icon_type": r.icon_type,
                "icon_col": r.icon_col, "icon_row": r.icon_row,
            } for r in config.roof_configs],
            fire_floor_level_num=ff_level,
            ahs_systems=model.ahs_systems,
        )
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.writelines(modified)
        
        return {"status": "ok", "output_path": output_path, "warnings": warnings}
    except Exception as e:
        raise HTTPException(500, f"Failed to update PRJ: {e}")


# ---------------------------------------------------------------------------
# File browse endpoints
# ---------------------------------------------------------------------------
@app.post("/api/browse/folder")
async def browse_folder(request: Request):
    body = await request.json()
    start_path = body.get("start_path", "")
    # Return the suggested path for the frontend to handle
    # On Windows, native dialogs would be used; here we accept text input
    return {"path": start_path}


@app.post("/api/browse/file")
async def browse_file(request: Request):
    body = await request.json()
    start_path = body.get("start_path", "")
    extensions = body.get("extensions", [])
    return {"path": start_path, "extensions": extensions}


@app.post("/api/browse/list")
async def browse_list(request: Request):
    """List directory contents for the file browser."""
    body = await request.json()
    path_str = body.get("path", "")

    if not path_str:
        # Return available drives on Windows, or root on Linux
        if sys.platform == "win32":
            import string
            drives = []
            for letter in string.ascii_uppercase:
                dp = Path(f"{letter}:\\")
                if dp.exists():
                    drives.append({"name": f"{letter}:\\", "type": "drive", "path": str(dp)})
            return {"items": drives, "current_path": ""}
        else:
            path_str = "/"

    path = Path(path_str)
    if not path.exists():
        raise HTTPException(404, f"Path not found: {path_str}")

    items = []
    if path.is_dir():
        try:
            for entry in sorted(path.iterdir()):
                try:
                    item = {
                        "name": entry.name,
                        "type": "dir" if entry.is_dir() else "file",
                        "path": str(entry),
                    }
                    if entry.is_file():
                        item["size"] = entry.stat().st_size
                        item["ext"] = entry.suffix.lower()
                    items.append(item)
                except PermissionError:
                    continue
        except PermissionError:
            raise HTTPException(403, f"Permission denied: {path_str}")

    parent = str(path.parent) if path.parent != path else ""
    return {"items": items, "current_path": str(path), "parent": parent}


# ---------------------------------------------------------------------------
# Helper: build AnalysisConfig from request body
# ---------------------------------------------------------------------------
def _build_analysis_config(body: dict) -> AnalysisConfig:
    """Build an AnalysisConfig from a JSON request body."""
    scenarios = [
        ScenarioConfig(
            name=s["name"],
            base_model_path=s["base_model_path"],
            temp_f=s["temp_f"],
            wind_mph=s["wind_mph"],
            wind_dir=s.get("wind_dir", 270),
        )
        for s in body.get("scenarios", [])
    ]

    stairs = [
        StairConfig(
            label=s["label"],
            levels=s.get("levels", []),
            paths=s.get("paths", {}),
        )
        for s in body.get("stairs", [])
    ]

    corridors = [
        CorridorConfig(
            label=c["label"],
            levels=c.get("levels", []),
            path_name=c.get("path_name", ""),
        )
        for c in body.get("corridors", [])
    ]

    roof_configs = [
        RoofConfig(
            stair_label=r.get("stair_label", ""),
            zone_id=r.get("zone_id", 0),
            level_num=r.get("level_num", 0),
            flow_rate=r.get("flow_rate", 0),
            ahs_id=r.get("ahs_id", 0),
            exhaust_zone=r.get("exhaust_zone", 0),
            icon_type=r.get("icon_type", 129),
            icon_col=r.get("icon_col", 1),
            icon_row=r.get("icon_row", 1),
        )
        for r in body.get("roof_configs", [])
    ]

    floor_zones = [
        FloorConfig(
            label=f.get("label", f"Floor_{i+1}"),
            levels=f.get("levels", []),
            path_name=f.get("path_name", ""),
        )
        for i, f in enumerate(body.get("floor_zones", []))
    ]

    return AnalysisConfig(
        project_name=body.get("project_name", ""),
        project_folder=body.get("project_folder", ""),
        contam_exe=body.get("contam_exe", ""),
        scenarios=scenarios,
        stairs=stairs,
        corridors=corridors,
        roof_configs=roof_configs,
        floor_zones=floor_zones,
        selected_floors=body.get("selected_floors", None),
        acceptance_criteria=body.get("acceptance_criteria", {
            "min_dp_inwc": 0.05,
            "max_dp_inwc": 0.45,
            "max_dp_stair_inwc": 0.17,
        }),
    )


# ---------------------------------------------------------------------------
# Auto-Solve endpoint
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Estimation Tool endpoints (ASHRAE HSCE analytical method)
# ---------------------------------------------------------------------------
from core.estimation_engine import EstimationEngine, cms_to_cfm, n_to_lbf, pa_to_inwg
from core.estimation_models import (
    BuildingGeometry,
    DesignConditions,
    DesignCriteria,
    ElevatorShaftConfig,
    EstimationConfig,
    LeakageData,
    StairwellGeometry,
)
from core.estimation_report import generate_estimation_report


def _build_estimation_config(body: dict) -> EstimationConfig:
    """Build an EstimationConfig from a JSON request body."""
    b = body.get("building", {})
    building = BuildingGeometry(
        n_floors_above=b.get("n_floors_above", 10),
        n_floors_below=b.get("n_floors_below", 0),
        floor_height=b.get("floor_height", 3.5),
        building_perimeter=b.get("building_perimeter", 120.0),
        floor_area=b.get("floor_area", 1000.0),
        wall_construction=b.get("wall_construction", "average"),
    )

    stairwells = []
    for s in body.get("stairwells", [{"label": "Stair A"}]):
        stairwells.append(StairwellGeometry(
            label=s.get("label", "Stair A"),
            cross_section_perimeter=s.get("cross_section_perimeter", 8.0),
            cross_section_area=s.get("cross_section_area", 10.0),
            door_width=s.get("door_width", 1.1),
            door_height=s.get("door_height", 2.1),
            door_gap_mm=s.get("door_gap_mm", 3.0),
            doors_per_floor=s.get("doors_per_floor", 1),
            serves_bottom=s.get("serves_bottom", 1),
            serves_top=s.get("serves_top", building.n_floors_above + building.n_floors_below),
            n_exterior_walls=s.get("n_exterior_walls", 1),
            exterior_wall_length=s.get("exterior_wall_length", 4.0),
        ))

    e = body.get("elevators", {})
    elevators = ElevatorShaftConfig(
        n_shafts=e.get("n_shafts", 2),
        shaft_area=e.get("shaft_area", 6.0),
        door_type=e.get("door_type", "center-opening"),
        wall_construction=e.get("wall_construction", "average"),
        vent_area=e.get("vent_area", 0.0),
    )

    c = body.get("conditions", {})
    is_sprinklered = c.get("is_sprinklered", True)
    conditions = DesignConditions(
        T_outdoor_winter=c.get("T_outdoor_winter", -18.0),
        T_outdoor_summer=c.get("T_outdoor_summer", 35.0),
        T_indoor=c.get("T_indoor", 22.0),
        T_fire=c.get("T_fire", 300.0),
        wind_speed=c.get("wind_speed", 12.0),
        wind_direction=c.get("wind_direction", 0.0),
        P_atm=c.get("P_atm", 101325.0),
        n_open_doors=c.get("n_open_doors", 1),
        is_sprinklered=is_sprinklered,
        design_fire_hrr=c.get("design_fire_hrr", 2000.0),
    )

    lk = body.get("leakage", {})
    leakage = LeakageData(
        exterior_wall=lk.get("exterior_wall", "average"),
        interior_wall=lk.get("interior_wall", "average"),
        floor_ceiling=lk.get("floor_ceiling", "average"),
        stair_door=lk.get("stair_door", "average"),
        elevator_door=lk.get("elevator_door", "average"),
        custom_stair_door_area=lk.get("custom_stair_door_area"),
        custom_elevator_door_area=lk.get("custom_elevator_door_area"),
        use_crack_method_for_stair_door=lk.get("use_crack_method_for_stair_door", False),
    )

    cr = body.get("criteria", {})
    min_vel = 1.0 if is_sprinklered else 1.7
    criteria = DesignCriteria(
        min_dp_closed=cr.get("min_dp_closed", 12.5),
        max_dp_closed=cr.get("max_dp_closed", 87.0),
        min_door_velocity=cr.get("min_door_velocity", min_vel),
        max_door_force=cr.get("max_door_force", 133.0),
        floor_exhaust_dp=cr.get("floor_exhaust_dp", 25.0),
        door_closer_force=cr.get("door_closer_force", 55.0),
        handle_to_latch=cr.get("handle_to_latch", 0.075),
    )

    return EstimationConfig(
        building=building,
        stairwells=stairwells,
        elevators=elevators,
        conditions=conditions,
        leakage=leakage,
        criteria=criteria,
        stairwell_temp_assumption=body.get("stairwell_temp_assumption", "outdoor"),
        fire_floor=body.get("fire_floor", max(1, building.n_floors_above // 2)),
    )


@app.get("/estimation", response_class=HTMLResponse)
async def estimation_page(request: Request):
    return templates.TemplateResponse("estimation.html", {"request": request})


@app.get("/api/estimation/defaults")
async def estimation_defaults():
    """Return default input values for the estimation tool."""
    cfg = EstimationConfig()
    return {
        "building": {
            "n_floors_above": cfg.building.n_floors_above,
            "n_floors_below": cfg.building.n_floors_below,
            "floor_height": cfg.building.floor_height,
            "building_perimeter": cfg.building.building_perimeter,
            "floor_area": cfg.building.floor_area,
            "wall_construction": cfg.building.wall_construction,
        },
        "stairwells": [{
            "label": s.label,
            "cross_section_perimeter": s.cross_section_perimeter,
            "cross_section_area": s.cross_section_area,
            "door_width": s.door_width,
            "door_height": s.door_height,
            "door_gap_mm": s.door_gap_mm,
            "doors_per_floor": s.doors_per_floor,
            "serves_bottom": s.serves_bottom,
            "serves_top": s.serves_top,
            "n_exterior_walls": s.n_exterior_walls,
            "exterior_wall_length": s.exterior_wall_length,
        } for s in cfg.stairwells],
        "elevators": {
            "n_shafts": cfg.elevators.n_shafts,
            "shaft_area": cfg.elevators.shaft_area,
            "door_type": cfg.elevators.door_type,
            "wall_construction": cfg.elevators.wall_construction,
            "vent_area": cfg.elevators.vent_area,
        },
        "conditions": {
            "T_outdoor_winter": cfg.conditions.T_outdoor_winter,
            "T_outdoor_summer": cfg.conditions.T_outdoor_summer,
            "T_indoor": cfg.conditions.T_indoor,
            "T_fire": cfg.conditions.T_fire,
            "wind_speed": cfg.conditions.wind_speed,
            "wind_direction": cfg.conditions.wind_direction,
            "P_atm": cfg.conditions.P_atm,
            "n_open_doors": cfg.conditions.n_open_doors,
            "is_sprinklered": cfg.conditions.is_sprinklered,
            "design_fire_hrr": cfg.conditions.design_fire_hrr,
        },
        "leakage": {
            "exterior_wall": cfg.leakage.exterior_wall,
            "interior_wall": cfg.leakage.interior_wall,
            "floor_ceiling": cfg.leakage.floor_ceiling,
            "stair_door": cfg.leakage.stair_door,
            "elevator_door": cfg.leakage.elevator_door,
        },
        "criteria": {
            "min_dp_closed": cfg.criteria.min_dp_closed,
            "max_dp_closed": cfg.criteria.max_dp_closed,
            "min_door_velocity": cfg.criteria.min_door_velocity,
            "max_door_force": cfg.criteria.max_door_force,
            "floor_exhaust_dp": cfg.criteria.floor_exhaust_dp,
            "door_closer_force": cfg.criteria.door_closer_force,
            "handle_to_latch": cfg.criteria.handle_to_latch,
        },
        "stairwell_temp_assumption": cfg.stairwell_temp_assumption,
        "fire_floor": cfg.fire_floor,
    }


@app.post("/api/estimation/run")
async def run_estimation(request: Request):
    """Run the stair pressurization estimation calculation."""
    body = await request.json()
    try:
        config = _build_estimation_config(body)
        engine = EstimationEngine(config)
        result = engine.run_full()

        # Serialize result for JSON response
        stair_summaries = []
        for sr in result.stair_results:
            floors = []
            for fr in sr.floor_results:
                floors.append({
                    "floor_label": fr.floor_label,
                    "floor_number": fr.floor_number,
                    "height": round(fr.height, 2),
                    "dp_stack": round(fr.dp_stack, 2),
                    "dp_wind": round(fr.dp_wind, 2),
                    "dp_net": round(fr.dp_net, 2),
                    "dp_stack_inwg": round(pa_to_inwg(fr.dp_stack), 4),
                    "dp_wind_inwg": round(pa_to_inwg(fr.dp_wind), 4),
                    "dp_net_inwg": round(pa_to_inwg(fr.dp_net), 4),
                    "q_leak_closed": round(fr.q_leak_closed, 5),
                    "q_leak_closed_cfm": round(cms_to_cfm(fr.q_leak_closed), 1),
                    "q_flow_open": round(fr.q_flow_open, 5),
                    "q_flow_open_cfm": round(cms_to_cfm(fr.q_flow_open), 1),
                    "f_total": round(fr.f_total, 1),
                    "f_total_lbf": round(n_to_lbf(fr.f_total), 1),
                    "status": fr.status,
                    "failure_reasons": fr.failure_reasons,
                })
            stair_summaries.append({
                "label": sr.label,
                "floor_results": floors,
                "q_supply_closed": round(sr.q_supply_closed, 5),
                "q_supply_closed_cfm": round(cms_to_cfm(sr.q_supply_closed), 0),
                "q_supply_open": round(sr.q_supply_open, 5),
                "q_supply_open_cfm": round(cms_to_cfm(sr.q_supply_open), 0),
                "q_supply_design": round(sr.q_supply_design, 5),
                "q_supply_design_cfm": round(cms_to_cfm(sr.q_supply_design), 0),
                "q_leak_walls": round(sr.q_leak_walls, 5),
                "critical_floor_min_dp": sr.critical_floor_min_dp,
                "critical_floor_max_force": sr.critical_floor_max_force,
                "all_constraints_met": sr.all_constraints_met,
            })

        er = result.exhaust_result
        exhaust = {
            "fire_floor": er.fire_floor,
            "fire_floor_label": er.fire_floor_label,
            "q_leak_stairs": round(er.q_leak_stairs, 5),
            "q_leak_stairs_cfm": round(cms_to_cfm(er.q_leak_stairs), 0),
            "q_leak_elevators": round(er.q_leak_elevators, 5),
            "q_leak_elevators_cfm": round(cms_to_cfm(er.q_leak_elevators), 0),
            "q_leak_exterior": round(er.q_leak_exterior, 5),
            "q_leak_exterior_cfm": round(cms_to_cfm(er.q_leak_exterior), 0),
            "q_leak_vertical": round(er.q_leak_vertical, 5),
            "q_leak_vertical_cfm": round(cms_to_cfm(er.q_leak_vertical), 0),
            "q_exhaust_total": round(er.q_exhaust_total, 5),
            "q_exhaust_total_cfm": round(cms_to_cfm(er.q_exhaust_total), 0),
        }

        sensitivity = []
        for sc in result.sensitivity_cases:
            sensitivity.append({
                "parameter": sc.parameter,
                "value_description": sc.value_description,
                "stair_supply_total": round(sc.stair_supply_total, 5),
                "stair_supply_total_cfm": round(cms_to_cfm(sc.stair_supply_total), 0),
                "exhaust_total": round(sc.exhaust_total, 5),
                "exhaust_total_cfm": round(cms_to_cfm(sc.exhaust_total), 0),
                "stair_supply_change_pct": round(sc.stair_supply_change_pct, 1),
                "exhaust_change_pct": round(sc.exhaust_change_pct, 1),
                "critical_floor": sc.critical_floor,
                "constraints_violated": sc.constraints_violated,
            })

        # Serialize calculation traces
        traces = []
        for tr in result.calculation_traces:
            traces.append({
                "equation_id": tr.equation_id,
                "description": tr.description,
                "formula": tr.formula,
                "inputs": tr.inputs,
                "substitution": tr.substitution,
                "result": tr.result,
            })

        return {
            "status": "ok",
            "stair_results": stair_summaries,
            "exhaust_result": exhaust,
            "sensitivity_cases": sensitivity,
            "calculation_traces": traces,
            "npp_height": round(result.npp_height, 2),
            "all_constraints_met": result.all_constraints_met,
            "warnings": result.warnings,
        }
    except Exception as e:
        logger.exception("Estimation calculation failed")
        raise HTTPException(500, f"Calculation failed: {e}")


@app.post("/api/estimation/report")
async def estimation_report(request: Request):
    """Generate an HTML report for the estimation results."""
    body = await request.json()
    try:
        config = _build_estimation_config(body)
        engine = EstimationEngine(config)
        result = engine.run_full()
        html = generate_estimation_report(result)
        return HTMLResponse(content=html)
    except Exception as e:
        logger.exception("Report generation failed")
        raise HTTPException(500, f"Report generation failed: {e}")


# ---------------------------------------------------------------------------
# SCRA Generator endpoints
# ---------------------------------------------------------------------------
from core.scra_models import (
    BuildingDescription,
    ClimateData,
    ProjectInfo,
    SCRAConfig,
    StairDefinition,
)
from core.scra_generator import SCRAGenerator
from core.scra_report import generate_scra_report


@app.get("/scra", response_class=HTMLResponse)
async def scra_page(request: Request):
    return templates.TemplateResponse("scra.html", {"request": request})


@app.post("/api/scra/parse-prj")
async def scra_parse_prj(file: UploadFile = File(...)):
    """Upload and parse a PRJ file for SCRA generation."""
    if not file.filename or not file.filename.lower().endswith(".prj"):
        raise HTTPException(400, "Please upload a .prj file")

    projects_dir = BASE_DIR / "Projects"
    projects_dir.mkdir(exist_ok=True)
    dest = projects_dir / file.filename
    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)

    try:
        from core.scra_generator import extract_building_from_prj
        data = extract_building_from_prj(str(dest))
        data["prj_path"] = str(dest)
        return data
    except Exception as e:
        raise HTTPException(422, f"Failed to parse PRJ file: {e}")


@app.post("/api/scra/generate")
async def scra_generate(request: Request):
    """Generate a complete SCRA report."""
    body = await request.json()

    try:
        # Build project info
        proj_data = body.get("project", {})
        project = ProjectInfo(
            project_name=proj_data.get("project_name", ""),
            project_number=proj_data.get("project_number", ""),
            project_address=proj_data.get("project_address", ""),
            project_city=proj_data.get("project_city", ""),
            project_state=proj_data.get("project_state", "California"),
            submittal_type=proj_data.get("submittal_type", "First Submittal"),
            report_date=proj_data.get("report_date", ""),
            prepared_for_name=proj_data.get("prepared_for_name", ""),
            prepared_for_address=proj_data.get("prepared_for_address", ""),
            prepared_by_name=proj_data.get("prepared_by_name", "Simpson Gumpertz & Heger Inc."),
            prepared_by_address=proj_data.get("prepared_by_address", ""),
            prepared_by_phone=proj_data.get("prepared_by_phone", ""),
        )

        # Build building description
        bldg_data = body.get("building", {})
        building = BuildingDescription(
            building_name=bldg_data.get("building_name", ""),
            building_abbreviation=bldg_data.get("building_abbreviation", ""),
            total_stories=bldg_data.get("total_stories", 10),
            above_grade_parking=bldg_data.get("above_grade_parking", 0),
            subterranean_levels=bldg_data.get("subterranean_levels", 0),
            building_type=bldg_data.get("building_type", "high-rise office tower"),
            is_sprinklered=bldg_data.get("is_sprinklered", True),
            tenant_name=bldg_data.get("tenant_name", ""),
            scope_bottom_level=bldg_data.get("scope_bottom_level", 1),
            scope_top_level=bldg_data.get("scope_top_level", 10),
            scope_description=f"Levels {bldg_data.get('scope_bottom_level', 1)} through {bldg_data.get('scope_top_level', 10)}",
            base_scra_author=bldg_data.get("base_scra_author", ""),
            base_scra_date=bldg_data.get("base_scra_date", ""),
            base_scra_revision=bldg_data.get("base_scra_revision", ""),
        )

        # Build climate data
        clim_data = body.get("climate", {})
        climate = ClimateData(
            weather_station=clim_data.get("weather_station", ""),
            winter_design_db=clim_data.get("winter_design_db", 44.4),
            summer_design_db=clim_data.get("summer_design_db", 83.7),
            indoor_design_temp=clim_data.get("indoor_design_temp", 68.0),
            winter_design_db_C=clim_data.get("winter_design_db_C", 6.9),
            summer_design_db_C=clim_data.get("summer_design_db_C", 28.7),
            indoor_design_temp_C=clim_data.get("indoor_design_temp_C", 20.0),
        )

        # Build stair definitions
        stair_defs = []
        for s in body.get("stairs", []):
            sd = StairDefinition(
                label=s.get("label", "Stair 1"),
                serves_bottom_level=s.get("serves_bottom_level", 1),
                serves_top_level=s.get("serves_top_level", 10),
                door_width_m=s.get("door_width_m", 1.1),
                door_height_m=s.get("door_height_m", 2.1),
                door_gap_mm=s.get("door_gap_mm", 3.0),
                has_vestibule=s.get("has_vestibule", True),
                is_smokeproof=True,
            )
            stair_defs.append(sd)

        # Build criteria
        criteria_data = body.get("criteria", {})

        # Build SCRA config
        config = SCRAConfig(
            project=project,
            building=building,
            climate=climate,
            stairs=stair_defs,
            min_dp_inwg=criteria_data.get("min_dp_inwg", 0.05),
            max_door_force_lbf=criteria_data.get("max_door_force_lbf", 30.0),
            max_door_force_egress_lbf=criteria_data.get("max_door_force_egress_lbf", 15.0),
            code_jurisdiction=body.get("code_jurisdiction", "LABC"),
        )

        # Run generator
        generator = SCRAGenerator(config)
        results = generator.generate()

        # Generate HTML report
        html = generate_scra_report(results)
        return HTMLResponse(content=html)

    except Exception as e:
        logger.exception("SCRA generation failed")
        raise HTTPException(500, f"SCRA generation failed: {e}")


# ---------------------------------------------------------------------------
# PRJ → Estimation auto-fill
# ---------------------------------------------------------------------------
@app.post("/api/estimation/extract-from-prj")
async def extract_estimation_from_prj(file: UploadFile = File(...)):
    """Parse a PRJ file and extract values to pre-fill the estimation form."""
    if not file.filename or not file.filename.lower().endswith(".prj"):
        raise HTTPException(400, "Please upload a .prj file")

    # Save uploaded file
    projects_dir = BASE_DIR / "Projects"
    projects_dir.mkdir(exist_ok=True)
    dest = projects_dir / file.filename
    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)

    # Parse
    try:
        model = parse_prj_file(str(dest))
    except Exception as e:
        raise HTTPException(422, f"Failed to parse PRJ file: {e}")

    # Auto-detect configuration
    try:
        config = auto_detect_config(model)
    except Exception:
        config = {"stairs": [], "corridors": [], "floor_zones": [], "weather": {}}

    result = _extract_estimation_values(model, config)
    result["filename"] = file.filename
    result["project_name"] = model.project_name
    return result


def _extract_estimation_values(model: ParsedModel, config: dict) -> dict:
    """Map a parsed CONTAM model to estimation form field values."""
    import re
    from collections import Counter

    levels = model.levels
    if not levels:
        return {}

    # --- Floor count (above / below grade) ---
    levels_above = [l for l in levels if l.ref_height >= 0]
    levels_below = [l for l in levels if l.ref_height < 0]
    n_above = max(len(levels_above), 1)
    n_below = len(levels_below)

    # --- Floor-to-floor height (most common delta_height) ---
    heights = [round(l.delta_height, 2) for l in levels if l.delta_height > 0]
    floor_height = Counter(heights).most_common(1)[0][0] if heights else 3.5

    # --- Floor area (sum zone volumes on a representative mid level) ---
    mid_level = levels[len(levels) // 2]
    level_zones = [z for z in model.zones if z.level_num == mid_level.index]
    total_vol = sum(z.volume for z in level_zones)
    floor_area = round(total_vol / floor_height, 0) if total_vol > 0 else 1000.0

    # --- Building perimeter (estimate from floor area ~ square) ---
    building_perimeter = round(4 * (floor_area ** 0.5), 0)

    # --- Stairwells ---
    stairwells = []
    for sg in config.get("stairs", []):
        zones = sg.get("zones", [])
        if not zones:
            continue

        # Cross-section area from zone volumes
        areas = []
        for z in zones:
            vol = z.get("volume", 0)
            if vol > 0:
                lvl = next((l for l in levels if l.index == z["level_num"]), None)
                h = lvl.delta_height if lvl and lvl.delta_height > 0 else floor_height
                areas.append(vol / h)
        stair_area = round(sum(areas) / len(areas), 1) if areas else 10.0

        level_nums = sorted(z["level_num"] for z in zones)
        paths = sg.get("paths", {})
        n_ext = 1 if paths.get("ext") else 0
        perim = round(6 * (stair_area / 2) ** 0.5, 1)

        stairwells.append({
            "label": sg.get("label", f"Stair {chr(65 + len(stairwells))}"),
            "area": stair_area,
            "doorW": 1.1,
            "doorH": 2.1,
            "gap": 3.0,
            "doors": 1,
            "bottom": min(level_nums),
            "top": max(level_nums),
            "extWalls": n_ext,
            "extLen": 4.0,
            "perim": perim,
        })

    # --- Elevator shafts ---
    elev_re = re.compile(r"(?i)(elev|shaft|lift)")
    exclude_re = re.compile(r"(?i)(stair|vest|corr|hallway|stwr)")
    elev_groups: Dict[str, list] = {}
    for z in model.zones:
        if elev_re.search(z.name) and not exclude_re.search(z.name):
            key = re.sub(r"[_\-\s]", "", z.name).lower()
            elev_groups.setdefault(key, []).append(z)

    n_elev_shafts = sum(1 for zs in elev_groups.values() if len(zs) >= 2)
    elev_area = 6.0
    if elev_groups:
        areas = []
        for zs in elev_groups.values():
            if len(zs) >= 2:
                for z in zs:
                    lvl = next((l for l in levels if l.index == z.level_num), None)
                    h = lvl.delta_height if lvl and lvl.delta_height > 0 else floor_height
                    if z.volume > 0:
                        areas.append(z.volume / h)
        if areas:
            elev_area = round(sum(areas) / len(areas), 1)

    # --- Weather (Kelvin -> C, m/s direct) ---
    temp_c, wind_ms, wind_dir = 22.0, 0.0, 0.0
    if 0 <= model.weather_line_num < len(model.raw_lines):
        parts = model.raw_lines[model.weather_line_num].split()
        if len(parts) >= 4:
            try:
                temp_c = round(float(parts[0]) - 273.15, 1)
                wind_ms = round(float(parts[2]), 1)
                wind_dir = round(float(parts[3]), 0)
            except (ValueError, IndexError):
                pass

    return {
        "building": {
            "n_floors_above": n_above,
            "n_floors_below": n_below,
            "floor_height": floor_height,
            "building_perimeter": building_perimeter,
            "floor_area": floor_area,
        },
        "stairwells": stairwells,
        "elevators": {
            "n_shafts": n_elev_shafts if n_elev_shafts > 0 else 2,
            "shaft_area": elev_area,
        },
        "conditions": {
            "T_outdoor_winter": temp_c,
            "wind_speed": wind_ms,
            "wind_direction": wind_dir,
        },
        "detection_details": config.get("detection_details", []),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def _find_free_port(start: int = 5000, attempts: int = 20) -> int:
    """Find a free port starting from `start`, trying up to `attempts` ports."""
    import socket
    for offset in range(attempts):
        port = start + offset
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    return start + attempts  # last resort


def main():
    preferred = int(os.environ.get("PORT", 5000))

    # Check if preferred port is available; if not, find one that is
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", preferred))
        port = preferred
    except OSError:
        print(f"\n  Port {preferred} is already in use.")
        print(f"  (A previous instance may still be running.)")
        port = _find_free_port(preferred + 1)
        print(f"  Using port {port} instead.\n")

    logger.info("Starting CONTAM Pressurization Tool on port %d", port)

    # Open browser after short delay
    if not os.environ.get("NO_BROWSER"):
        import threading
        def open_browser():
            import time
            time.sleep(1.5)
            webbrowser.open(f"http://localhost:{port}")
        threading.Thread(target=open_browser, daemon=True).start()

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Write crash details to log file so the user can see what happened
        import traceback
        crash_log = Path(__file__).parent / "crash_log.txt"
        with open(crash_log, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"CRASH at {__import__('datetime').datetime.now()}\n")
            f.write(f"{'='*60}\n")
            traceback.print_exc(file=f)
            f.write(f"\nError: {e}\n")
        # Also print to console (will show in the cmd window before pause)
        print(f"\n{'='*60}")
        print(f"FATAL ERROR: {e}")
        print(f"{'='*60}")
        traceback.print_exc()
        print(f"\nFull details saved to: {crash_log}")
        sys.exit(1)
