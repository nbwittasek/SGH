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
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.analysis_engine import (
    AnalysisConfig,
    AnalysisEngine,
    CorridorConfig,
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
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
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
        "acceptance_criteria": {"min_dp_inwc": 0.05, "max_dp_inwc": 0.45},
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
            "acceptance_criteria": {"min_dp_inwc": 0.05, "max_dp_inwc": 0.45},
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
    # Filter out warnings for dry run
    critical_errors = [e for e in errors if not e.startswith("Warning")]
    if critical_errors:
        raise HTTPException(400, f"Validation failed: {'; '.join(critical_errors)}")

    files = engine.dry_run()
    return {"status": "ok", "generated_files": files, "count": len(files)}


@app.post("/api/analysis/start")
async def start_analysis(request: Request):
    global analysis_engine, analysis_log, analysis_running
    if analysis_running:
        raise HTTPException(409, "Analysis already running")

    body = await request.json()
    config = _build_analysis_config(body)
    analysis_engine = AnalysisEngine(config)
    analysis_log = []
    analysis_running = True

    def on_progress(info):
        analysis_log.append(info["message"])

    analysis_engine.on_progress(on_progress)

    # Run in background task
    asyncio.get_event_loop().create_task(_run_analysis_task())

    return {
        "status": "started",
        "total_runs": analysis_engine.count_total_runs(),
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


@app.get("/api/results/summary")
async def get_results_summary():
    if not analysis_engine:
        raise HTTPException(404, "No results available")
    return analysis_engine.get_results_summary()


@app.get("/api/results/{scenario}/detailed")
async def get_detailed_results(scenario: str):
    """Get per-fire-floor detailed results for a scenario."""
    if not analysis_engine or not analysis_engine.results:
        raise HTTPException(404, "No results available")
    detailed = analysis_engine.get_detailed_results(scenario)
    if detailed is None:
        raise HTTPException(404, f"Detailed results for '{scenario}' not found")
    return detailed


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
    filepath = folder / "Summary_All_Scenarios.csv"
    combined.to_csv(filepath, index=False, float_format="%.4f")

    return FileResponse(filepath, filename="Summary_All_Scenarios.csv")


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

    return AnalysisConfig(
        project_name=body.get("project_name", ""),
        project_folder=body.get("project_folder", ""),
        contam_exe=body.get("contam_exe", ""),
        scenarios=scenarios,
        stairs=stairs,
        corridors=corridors,
        roof_configs=roof_configs,
        acceptance_criteria=body.get("acceptance_criteria", {
            "min_dp_inwc": 0.05,
            "max_dp_inwc": 0.45,
        }),
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    port = int(os.environ.get("PORT", 5000))
    logger.info("Starting CONTAM Pressurization Tool on port %d", port)

    # Open browser after short delay
    if not os.environ.get("NO_BROWSER"):
        import threading
        def open_browser():
            import time
            time.sleep(1.5)
            webbrowser.open(f"http://localhost:{port}")
        threading.Thread(target=open_browser, daemon=True).start()

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
