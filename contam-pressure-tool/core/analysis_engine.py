"""Main analysis loop for CONTAM stairwell pressurization analysis.

Orchestrates the full workflow:
1. Load base model
2. For each scenario x fire floor combination:
   a. Modify PRJ with pressurization/depressurization
   b. Run CONTAM solver
   c. Extract pressure differentials
3. Compile results
"""

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from .contam_runner import run_contam
from .prj_parser import (
    ParsedModel,
    find_paths_by_element_name,
    parse_prj_file,
)
from .prj_writer import build_modified_prj
from .units import pa_to_inwc
from .xlog_parser import extract_pressure_diffs

logger = logging.getLogger(__name__)


@dataclass
class ScenarioConfig:
    name: str
    base_model_path: str
    temp_f: float
    wind_mph: float
    wind_dir: float


@dataclass
class StairConfig:
    label: str
    levels: List[dict]  # Each: {level_num, zone_id, flow_rate, ahs_id, supply_zone, icon_type, icon_col, icon_row}
    paths: dict  # {s2v: str, v2c: str, ext: str, s2v2: str?, v2c2: str?}


@dataclass
class CorridorConfig:
    label: str
    levels: List[dict]  # Each: {level_num, zone_id, flow_rate, ahs_id, exhaust_zone, icon_type, icon_col, icon_row}
    path_name: str  # e.g., "FLR.LK.Measured"


@dataclass
class RoofConfig:
    stair_label: str
    zone_id: int
    level_num: int
    flow_rate: float
    ahs_id: int
    exhaust_zone: int
    icon_type: int = 129
    icon_col: int = 1
    icon_row: int = 1


@dataclass
class AnalysisConfig:
    project_name: str
    project_folder: str
    contam_exe: str
    scenarios: List[ScenarioConfig]
    stairs: List[StairConfig]
    corridors: List[CorridorConfig]
    roof_configs: List[RoofConfig]
    acceptance_criteria: dict = field(default_factory=lambda: {
        "min_dp_inwc": 0.05,
        "max_dp_inwc": 0.45,
    })


@dataclass
class AnalysisResult:
    scenario_name: str
    base_model: str
    fire_floor_levels: List[int]
    stair_labels: List[str]
    # Results arrays indexed [path_level, fire_floor_idx]
    stair_dp: Dict[str, np.ndarray] = field(default_factory=dict)  # S2V per stair
    vest_dp: Dict[str, np.ndarray] = field(default_factory=dict)   # V2C per stair
    ext_dp: Dict[str, np.ndarray] = field(default_factory=dict)    # S2EXT per stair
    stair_dp2: Dict[str, np.ndarray] = field(default_factory=dict)  # S2V2 (secondary)
    vest_dp2: Dict[str, np.ndarray] = field(default_factory=dict)   # V2C2 (secondary)
    corridor_dp_below: np.ndarray = field(default_factory=lambda: np.array([]))
    corridor_dp_above: np.ndarray = field(default_factory=lambda: np.array([]))
    output_table: Optional[pd.DataFrame] = None


class AnalysisEngine:
    """Orchestrates the full CONTAM analysis."""

    def __init__(self, config: AnalysisConfig):
        self.config = config
        self._cancelled = False
        self._progress_callbacks: List[Callable] = []
        self.results: List[AnalysisResult] = []

    def cancel(self) -> None:
        self._cancelled = True

    def on_progress(self, callback: Callable) -> None:
        self._progress_callbacks.append(callback)

    def _emit_progress(self, message: str, current: int = 0, total: int = 0) -> None:
        for cb in self._progress_callbacks:
            cb({"message": message, "current": current, "total": total})

    def get_fire_floor_levels(self) -> List[int]:
        """Get the list of fire floor level numbers from corridor configs."""
        levels = []
        for corr in self.config.corridors:
            for le in corr.levels:
                if le.get("flow_rate", 0) > 0 and le.get("zone_id", 0) != 0:
                    if le["level_num"] not in levels:
                        levels.append(le["level_num"])
        return sorted(levels)

    def count_total_runs(self) -> int:
        """Count total CONTAM runs needed."""
        fire_floors = self.get_fire_floor_levels()
        return len(self.config.scenarios) * len(fire_floors)

    def validate(self) -> List[str]:
        """Run pre-flight validation. Returns list of error messages."""
        errors = []

        # Check CONTAM exe
        if not Path(self.config.contam_exe).exists():
            errors.append(
                f"CONTAM executable not found: {self.config.contam_exe}"
            )

        # Check base model files
        for scenario in self.config.scenarios:
            if not Path(scenario.base_model_path).exists():
                errors.append(
                    f"Base model not found for scenario '{scenario.name}': "
                    f"{scenario.base_model_path}"
                )

        # Check project folder
        pf = Path(self.config.project_folder)
        if not pf.exists():
            try:
                pf.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                errors.append(f"Cannot create project folder: {e}")

        # Check stair configs have non-zero rates
        for stair in self.config.stairs:
            has_nonzero = any(
                le.get("flow_rate", 0) > 0 for le in stair.levels
            )
            if not has_nonzero:
                errors.append(
                    f"Warning: Stair '{stair.label}' has all zero flow rates."
                )

        # Check fire floors exist
        fire_floors = self.get_fire_floor_levels()
        if not fire_floors:
            errors.append(
                "No fire floor levels found. Ensure corridor configs "
                "have non-zero flow rates."
            )

        return errors

    def dry_run(self) -> List[str]:
        """Generate modified PRJ files without running CONTAM.

        Returns list of generated file paths.
        """
        generated = []
        fire_floors = self.get_fire_floor_levels()
        output_dir = Path(self.config.project_folder) / "dry_run"
        output_dir.mkdir(parents=True, exist_ok=True)

        for scenario in self.config.scenarios:
            if not Path(scenario.base_model_path).exists():
                continue

            model = parse_prj_file(scenario.base_model_path)

            for ff_level in fire_floors:
                if self._cancelled:
                    break

                modified = build_modified_prj(
                    base_lines=model.raw_lines,
                    temp_f=scenario.temp_f,
                    wind_mph=scenario.wind_mph,
                    wind_dir=scenario.wind_dir,
                    stair_configs=[
                        {"label": s.label, "levels": s.levels}
                        for s in self.config.stairs
                    ],
                    corridor_configs=[
                        {"label": c.label, "levels": c.levels}
                        for c in self.config.corridors
                    ],
                    roof_configs=[
                        {
                            "zone_id": r.zone_id,
                            "level_num": r.level_num,
                            "flow_rate": r.flow_rate,
                            "ahs_id": r.ahs_id,
                            "exhaust_zone": r.exhaust_zone,
                            "icon_type": r.icon_type,
                            "icon_col": r.icon_col,
                            "icon_row": r.icon_row,
                        }
                        for r in self.config.roof_configs
                    ],
                    fire_floor_level_num=ff_level,
                    ahs_systems=model.ahs_systems,
                )

                # Find level name for filename
                level_name = f"Level{ff_level}"
                for lvl in model.levels:
                    if lvl.index == ff_level:
                        level_name = lvl.name
                        break

                filename = f"{scenario.name}_FF-{level_name}.prj"
                filepath = output_dir / filename
                with open(filepath, "w", encoding="utf-8") as f:
                    f.writelines(modified)
                generated.append(str(filepath))

        return generated

    async def run_analysis(self) -> List[AnalysisResult]:
        """Run the full analysis. Use this as an async generator via run_analysis_stream."""
        self._cancelled = False
        self.results = []
        fire_floors = self.get_fire_floor_levels()
        total_runs = self.count_total_runs()
        current_run = 0
        output_dir = Path(self.config.project_folder) / "analysis"
        output_dir.mkdir(parents=True, exist_ok=True)

        for scenario in self.config.scenarios:
            if self._cancelled:
                break

            if not Path(scenario.base_model_path).exists():
                self._emit_progress(
                    f"Skipping {scenario.name}: base model not found",
                    current_run, total_runs,
                )
                continue

            model = parse_prj_file(scenario.base_model_path)

            # Find path indices for each stair's flow elements
            stair_path_indices = {}
            for stair in self.config.stairs:
                paths_info = {}
                for path_key in ["s2v", "v2c", "ext", "s2v2", "v2c2"]:
                    elem_name = stair.paths.get(path_key)
                    if not elem_name:
                        continue
                    matching = find_paths_by_element_name(model, elem_name)
                    paths_info[path_key] = {
                        p.level_num: p.id for p in matching
                    }
                stair_path_indices[stair.label] = paths_info

            # Find corridor path indices
            corridor_path_indices = {}
            for corr in self.config.corridors:
                matching = find_paths_by_element_name(model, corr.path_name)
                corridor_path_indices[corr.label] = {
                    p.level_num: p.id for p in matching
                }

            # Initialize result
            num_path_levels = len(model.levels)
            num_fire_floors = len(fire_floors)

            result = AnalysisResult(
                scenario_name=scenario.name,
                base_model=scenario.base_model_path,
                fire_floor_levels=fire_floors,
                stair_labels=[s.label for s in self.config.stairs],
            )

            for stair in self.config.stairs:
                result.stair_dp[stair.label] = np.zeros((num_path_levels, num_fire_floors))
                result.vest_dp[stair.label] = np.zeros((num_path_levels, num_fire_floors))
                result.ext_dp[stair.label] = np.zeros((num_path_levels, num_fire_floors))
                if stair.paths.get("s2v2"):
                    result.stair_dp2[stair.label] = np.zeros((num_path_levels, num_fire_floors))
                if stair.paths.get("v2c2"):
                    result.vest_dp2[stair.label] = np.zeros((num_path_levels, num_fire_floors))

            result.corridor_dp_below = np.zeros(num_fire_floors)
            result.corridor_dp_above = np.zeros(num_fire_floors)

            # Run for each fire floor
            for ff_idx, ff_level in enumerate(fire_floors):
                if self._cancelled:
                    break

                current_run += 1

                # Find level name
                level_name = f"Level{ff_level}"
                for lvl in model.levels:
                    if lvl.index == ff_level:
                        level_name = lvl.name
                        break

                self._emit_progress(
                    f"Running: {scenario.name} — Fire Floor: {level_name} "
                    f"({current_run} of {total_runs})",
                    current_run, total_runs,
                )

                # Build modified PRJ
                modified = build_modified_prj(
                    base_lines=model.raw_lines,
                    temp_f=scenario.temp_f,
                    wind_mph=scenario.wind_mph,
                    wind_dir=scenario.wind_dir,
                    stair_configs=[
                        {"label": s.label, "levels": s.levels}
                        for s in self.config.stairs
                    ],
                    corridor_configs=[
                        {"label": c.label, "levels": c.levels}
                        for c in self.config.corridors
                    ],
                    roof_configs=[
                        {
                            "zone_id": r.zone_id,
                            "level_num": r.level_num,
                            "flow_rate": r.flow_rate,
                            "ahs_id": r.ahs_id,
                            "exhaust_zone": r.exhaust_zone,
                            "icon_type": r.icon_type,
                            "icon_col": r.icon_col,
                            "icon_row": r.icon_row,
                        }
                        for r in self.config.roof_configs
                    ],
                    fire_floor_level_num=ff_level,
                    ahs_systems=model.ahs_systems,
                )

                # Save modified PRJ
                filename = f"{scenario.name}_FF-{level_name}.prj"
                prj_path = output_dir / filename
                with open(prj_path, "w", encoding="utf-8") as f:
                    f.writelines(modified)

                # Run CONTAM
                run_result = run_contam(
                    self.config.contam_exe,
                    str(prj_path),
                )

                if not run_result["success"]:
                    logger.warning(
                        "CONTAM failed for %s FF-%s: %s",
                        scenario.name, level_name, run_result["error"],
                    )
                    self._emit_progress(
                        f"Warning: CONTAM failed for {scenario.name} "
                        f"FF-{level_name}: {run_result['error']}",
                        current_run, total_runs,
                    )
                    continue

                # Parse xlog results
                xlog_path = run_result["xlog_path"]
                try:
                    # Extract corridor pressure diffs
                    for corr in self.config.corridors:
                        corr_paths = corridor_path_indices.get(corr.label, {})
                        # Floor below the fire floor
                        below_level = ff_level - 1
                        if below_level in corr_paths:
                            dp = extract_pressure_diffs(
                                xlog_path, [corr_paths[below_level]]
                            )
                            result.corridor_dp_below[ff_idx] = dp[0]
                        # Floor above the fire floor
                        above_level = ff_level + 1
                        if above_level in corr_paths:
                            dp = extract_pressure_diffs(
                                xlog_path, [corr_paths[above_level]]
                            )
                            result.corridor_dp_above[ff_idx] = dp[0]

                    # Extract stair pressure diffs
                    for stair in self.config.stairs:
                        sp = stair_path_indices.get(stair.label, {})
                        for path_key, result_array in [
                            ("s2v", result.stair_dp),
                            ("v2c", result.vest_dp),
                            ("ext", result.ext_dp),
                        ]:
                            level_paths = sp.get(path_key, {})
                            for lvl_idx, lvl in enumerate(model.levels):
                                if lvl.index in level_paths:
                                    dp = extract_pressure_diffs(
                                        xlog_path,
                                        [level_paths[lvl.index]],
                                    )
                                    result_array[stair.label][lvl_idx, ff_idx] = dp[0]

                        # Secondary paths
                        for path_key, result_array in [
                            ("s2v2", result.stair_dp2),
                            ("v2c2", result.vest_dp2),
                        ]:
                            if stair.label not in result_array:
                                continue
                            level_paths = sp.get(path_key, {})
                            for lvl_idx, lvl in enumerate(model.levels):
                                if lvl.index in level_paths:
                                    dp = extract_pressure_diffs(
                                        xlog_path,
                                        [level_paths[lvl.index]],
                                    )
                                    result_array[stair.label][lvl_idx, ff_idx] = dp[0]

                except Exception as e:
                    logger.warning(
                        "Failed to parse results for %s FF-%s: %s",
                        scenario.name, level_name, e,
                    )

                # Allow event loop to process
                await asyncio.sleep(0)

            # Compile results: find max dP across fire floors, convert to in.w.c.
            result.output_table = self._compile_results(result, model)
            self.results.append(result)

            # Export CSV
            self._export_csv(result, scenario, output_dir)

        self._emit_progress("Analysis complete", total_runs, total_runs)
        return self.results

    def _compile_results(
        self, result: AnalysisResult, model: ParsedModel
    ) -> pd.DataFrame:
        """Compile results into a summary DataFrame."""
        levels = [lvl.name for lvl in model.levels]
        num_levels = len(levels)
        stairs = result.stair_labels

        columns = ["Level"]
        columns.extend(["dP_Corridor_Below", "dP_Corridor_Above"])
        for s in stairs:
            columns.append(f"{s}_S2V")
        for s in stairs:
            columns.append(f"{s}_V2C")
        for s in stairs:
            columns.append(f"{s}_EXT")

        rows = []
        for lvl_idx in range(num_levels):
            row = [levels[lvl_idx]]

            # Corridor dP: max across fire floors for this level
            # (corridor data is per fire-floor, not per path-level)
            if lvl_idx < len(result.corridor_dp_below):
                row.append(pa_to_inwc(float(np.max(np.abs(result.corridor_dp_below)))))
                row.append(pa_to_inwc(float(np.max(np.abs(result.corridor_dp_above)))))
            else:
                row.extend([0.0, 0.0])

            # Stair S2V: max across fire floors for this path level
            for s in stairs:
                if s in result.stair_dp and lvl_idx < result.stair_dp[s].shape[0]:
                    max_dp = float(np.max(np.abs(result.stair_dp[s][lvl_idx, :])))
                    row.append(pa_to_inwc(max_dp))
                else:
                    row.append(0.0)

            # Stair V2C
            for s in stairs:
                if s in result.vest_dp and lvl_idx < result.vest_dp[s].shape[0]:
                    max_dp = float(np.max(np.abs(result.vest_dp[s][lvl_idx, :])))
                    row.append(pa_to_inwc(max_dp))
                else:
                    row.append(0.0)

            # Stair EXT
            for s in stairs:
                if s in result.ext_dp and lvl_idx < result.ext_dp[s].shape[0]:
                    max_dp = float(np.max(np.abs(result.ext_dp[s][lvl_idx, :])))
                    row.append(pa_to_inwc(max_dp))
                else:
                    row.append(0.0)

            rows.append(row)

        return pd.DataFrame(rows, columns=columns)

    def _export_csv(
        self,
        result: AnalysisResult,
        scenario: ScenarioConfig,
        output_dir: Path,
    ) -> str:
        """Export results to CSV. Returns the file path."""
        if result.output_table is None:
            return ""

        base_name = Path(scenario.base_model_path).stem
        filename = f"Contam_Results_Summary_{base_name}_{scenario.name}.csv"
        filepath = output_dir / filename

        df = result.output_table
        df.to_csv(filepath, index=False, float_format="%.4f")

        # Append units footer
        with open(filepath, "a", encoding="utf-8") as f:
            f.write("Units: in. H2O\n")

        logger.info("Exported results to %s", filepath)
        return str(filepath)

    def get_results_summary(self) -> List[dict]:
        """Get a summary of all results for the GUI."""
        summaries = []
        for result in self.results:
            if result.output_table is None:
                continue
            df = result.output_table
            summary = {
                "scenario": result.scenario_name,
                "levels": df["Level"].tolist(),
                "columns": df.columns.tolist(),
                "data": df.values.tolist(),
                "stair_labels": result.stair_labels,
            }
            summaries.append(summary)
        return summaries

    def get_detailed_results(self, scenario_name: str) -> Optional[dict]:
        """Get per-fire-floor detailed results for a scenario.

        Returns a dict with:
            fire_floor_levels: list of fire floor level numbers
            fire_floor_names: list of fire floor level names
            levels: list of level names (rows)
            stair_labels: list of stair labels
            tables: dict mapping fire_floor_name -> {columns, data}
                Each table shows dP values for that specific fire floor.
            worst_case: dict mapping level_name -> {column -> {value, fire_floor}}
                Shows which fire floor produces the worst dP at each level.
        """
        result = None
        model = None
        for r in self.results:
            if r.scenario_name == scenario_name:
                result = r
                break
        if result is None or result.output_table is None:
            return None

        # Re-parse model for level names
        for scenario in self.config.scenarios:
            if scenario.name == scenario_name:
                model = parse_prj_file(scenario.base_model_path)
                break
        if model is None:
            return None

        levels = [lvl.name for lvl in model.levels]
        fire_floors = result.fire_floor_levels
        fire_floor_names = []
        for ff in fire_floors:
            name = f"Level{ff}"
            for lvl in model.levels:
                if lvl.index == ff:
                    name = lvl.name
                    break
            fire_floor_names.append(name)

        stairs = result.stair_labels

        # Build per-fire-floor tables
        tables = {}
        for ff_idx, ff_name in enumerate(fire_floor_names):
            columns = ["Level"]
            columns.extend(["dP_Corridor_Below", "dP_Corridor_Above"])
            for s in stairs:
                columns.append(f"{s}_S2V")
            for s in stairs:
                columns.append(f"{s}_V2C")
            for s in stairs:
                columns.append(f"{s}_EXT")

            rows = []
            for lvl_idx in range(len(levels)):
                row = [levels[lvl_idx]]

                # Corridor dP for this fire floor
                if ff_idx < len(result.corridor_dp_below):
                    row.append(pa_to_inwc(float(abs(result.corridor_dp_below[ff_idx]))))
                    row.append(pa_to_inwc(float(abs(result.corridor_dp_above[ff_idx]))))
                else:
                    row.extend([0.0, 0.0])

                for s in stairs:
                    if s in result.stair_dp and lvl_idx < result.stair_dp[s].shape[0]:
                        row.append(pa_to_inwc(float(abs(result.stair_dp[s][lvl_idx, ff_idx]))))
                    else:
                        row.append(0.0)
                for s in stairs:
                    if s in result.vest_dp and lvl_idx < result.vest_dp[s].shape[0]:
                        row.append(pa_to_inwc(float(abs(result.vest_dp[s][lvl_idx, ff_idx]))))
                    else:
                        row.append(0.0)
                for s in stairs:
                    if s in result.ext_dp and lvl_idx < result.ext_dp[s].shape[0]:
                        row.append(pa_to_inwc(float(abs(result.ext_dp[s][lvl_idx, ff_idx]))))
                    else:
                        row.append(0.0)

                rows.append(row)
            tables[ff_name] = {"columns": columns, "data": rows}

        # Build worst-case analysis: for each level + column, which fire floor is worst
        worst_case = {}
        columns = ["dP_Corridor_Below", "dP_Corridor_Above"]
        for s in stairs:
            columns.append(f"{s}_S2V")
        for s in stairs:
            columns.append(f"{s}_V2C")
        for s in stairs:
            columns.append(f"{s}_EXT")

        for lvl_idx, lvl_name in enumerate(levels):
            worst_case[lvl_name] = {}
            for col in columns:
                worst_val = 0.0
                worst_ff = ""
                for ff_idx, ff_name in enumerate(fire_floor_names):
                    table_data = tables[ff_name]["data"]
                    col_idx = tables[ff_name]["columns"].index(col)
                    val = table_data[lvl_idx][col_idx]
                    if isinstance(val, (int, float)) and abs(val) > abs(worst_val):
                        worst_val = val
                        worst_ff = ff_name
                worst_case[lvl_name][col] = {
                    "value": round(worst_val, 4),
                    "fire_floor": worst_ff,
                }

        # Pass/fail summary per level
        min_dp = self.config.acceptance_criteria.get("min_dp_inwc", 0.05)
        max_dp = self.config.acceptance_criteria.get("max_dp_inwc", 0.45)
        level_summary = {}
        for lvl_idx, lvl_name in enumerate(levels):
            pass_count = 0
            fail_count = 0
            total_checks = 0
            for ff_idx, ff_name in enumerate(fire_floor_names):
                table_data = tables[ff_name]["data"]
                for ci in range(1, len(tables[ff_name]["columns"])):
                    val = table_data[lvl_idx][ci]
                    if isinstance(val, (int, float)) and val != 0:
                        total_checks += 1
                        if min_dp <= abs(val) <= max_dp:
                            pass_count += 1
                        else:
                            fail_count += 1
            level_summary[lvl_name] = {
                "pass": pass_count,
                "fail": fail_count,
                "total": total_checks,
                "status": "pass" if fail_count == 0 and total_checks > 0 else ("fail" if fail_count > 0 else "no_data"),
            }

        return {
            "scenario": scenario_name,
            "fire_floor_levels": fire_floors,
            "fire_floor_names": fire_floor_names,
            "levels": levels,
            "stair_labels": stairs,
            "tables": tables,
            "worst_case": worst_case,
            "level_summary": level_summary,
        }
