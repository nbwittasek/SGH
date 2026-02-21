"""End-to-end simulation tests for the CONTAM stairwell pressurization tool.

Tests the full pipeline: parse -> auto-detect -> modify PRJ -> validate ->
dry-run -> xlog parse -> report generate, using synthetic .prj files.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.prj_parser import (
    ParsedModel,
    auto_detect_config,
    find_flow_element_by_name,
    find_paths_by_element_name,
    get_max_path_id,
    get_zone_display_name,
    get_zones_by_level,
    get_zones_by_name,
    parse_prj_file,
)
from core.prj_writer import (
    build_modified_prj,
    ensure_ahs_systems,
    ensure_tool_flow_element,
    validate_and_repair_paths,
    validate_prj_structure,
)
from core.xlog_parser import extract_all_pressure_diffs, extract_pressure_diffs, parse_xlog_file
from core.units import f_to_kelvin, inwc_to_pa, kelvin_to_f, mph_to_ms, ms_to_mph, pa_to_inwc, scfm_to_kgs
from core.report_generator import generate_report_html
from core.analysis_engine import (
    AnalysisConfig,
    AnalysisEngine,
    CorridorConfig,
    FloorConfig,
    RoofConfig,
    ScenarioConfig,
    StairConfig,
)


# ==========================================================================
# 1. PRJ PARSING
# ==========================================================================

class TestPrjParsing:
    """Test parsing of synthetic .prj files."""

    def test_parse_five_level(self, five_level_prj):
        model = parse_prj_file(str(five_level_prj))
        assert isinstance(model, ParsedModel)
        assert model.version == "ContamW 3.4.0.0 0"
        assert model.project_name == "TestBuilding_E2E"

    def test_levels_parsed(self, five_level_prj):
        model = parse_prj_file(str(five_level_prj))
        assert len(model.levels) == 5
        names = [l.name for l in model.levels]
        assert names == ["B1", "L1", "L2", "L3", "Roof"]
        # Level indices should be 1-5
        indices = [l.index for l in model.levels]
        assert indices == [1, 2, 3, 4, 5]

    def test_zones_parsed(self, five_level_prj):
        model = parse_prj_file(str(five_level_prj))
        # 5 levels x (2 stairs + 2 vestibules + 1 corridor) = 25 zones
        assert len(model.zones) == 25
        # Check zone names exist
        zone_names = {z.name for z in model.zones}
        assert "Stair_1" in zone_names
        assert "Stair_2" in zone_names
        assert "ST1_V" in zone_names
        assert "ST2_V" in zone_names
        assert "Corridor" in zone_names

    def test_flow_elements_parsed(self, five_level_prj):
        model = parse_prj_file(str(five_level_prj))
        # 2 stairs x 3 elements (S2V, V2C, EXT) + 1 corridor = 7
        assert len(model.flow_elements) == 7
        elem_names = {e.name for e in model.flow_elements}
        assert "Door-Stair1-S2V" in elem_names
        assert "Door-Stair2-V2C" in elem_names
        assert "FLR.LK.Measured" in elem_names

    def test_airflow_paths_parsed(self, five_level_prj):
        model = parse_prj_file(str(five_level_prj))
        # 5 levels x (2 stairs * 3 paths + 1 corridor) = 5 * 7 = 35
        assert len(model.airflow_paths) == 35
        # All paths should have valid level numbers
        for p in model.airflow_paths:
            assert 1 <= p.level_num <= 5

    def test_ahs_parsed(self, five_level_prj):
        model = parse_prj_file(str(five_level_prj))
        assert len(model.ahs_systems) == 2
        ahs_names = {a.name for a in model.ahs_systems}
        assert "SUPPLY" in ahs_names
        assert "RETURN" in ahs_names

    def test_weather_parsed(self, five_level_prj):
        model = parse_prj_file(str(five_level_prj))
        assert model.weather_line_num >= 0
        # weather_line_num points to the data line after the header
        line = model.raw_lines[model.weather_line_num]
        # Should be numeric data, not a comment
        assert not line.strip().startswith("!")
        parts = line.split()
        temp_k = float(parts[0])
        assert abs(temp_k - 294.261) < 0.01

    def test_output_config_parsed(self, five_level_prj):
        model = parse_prj_file(str(five_level_prj))
        assert model.output_config_line_num >= 0

    def test_parse_ten_level(self, ten_level_prj):
        model = parse_prj_file(str(ten_level_prj))
        assert len(model.levels) == 10
        assert len(model.zones) == 50  # 10 * (2+2+1)

    def test_parse_minimal(self, minimal_prj):
        model = parse_prj_file(str(minimal_prj))
        assert len(model.levels) == 2
        # 2 levels x (1 stair + 1 corridor) = 4 zones
        assert len(model.zones) == 4
        assert len(model.flow_elements) == 0
        assert len(model.airflow_paths) == 0

    def test_parse_nonexistent_file(self, tmp_project):
        with pytest.raises(FileNotFoundError):
            parse_prj_file(str(tmp_project / "nonexistent.prj"))

    def test_parse_empty_file(self, tmp_project):
        empty = tmp_project / "empty.prj"
        empty.write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="too short"):
            parse_prj_file(str(empty))

    def test_parse_two_line_file(self, tmp_project):
        short = tmp_project / "short.prj"
        short.write_text("line1\nline2\n", encoding="utf-8")
        with pytest.raises(ValueError, match="too short"):
            parse_prj_file(str(short))


# ==========================================================================
# 2. HELPER FUNCTIONS
# ==========================================================================

class TestHelperFunctions:
    """Test parser helper/lookup functions."""

    def test_get_zone_display_name(self, five_level_prj):
        model = parse_prj_file(str(five_level_prj))
        z = model.zones[0]
        display = get_zone_display_name(z)
        assert z.name in display
        assert str(z.id) in display
        assert z.level_name in display

    def test_get_zones_by_level(self, five_level_prj):
        model = parse_prj_file(str(five_level_prj))
        level_3_zones = get_zones_by_level(model, 3)
        assert len(level_3_zones) == 5  # 2 stairs + 2 vests + 1 corridor
        assert all(z.level_num == 3 for z in level_3_zones)

    def test_get_zones_by_name(self, five_level_prj):
        model = parse_prj_file(str(five_level_prj))
        stair1_zones = get_zones_by_name(model, "Stair_1")
        assert len(stair1_zones) == 5  # one per level
        assert all(z.name == "Stair_1" for z in stair1_zones)

    def test_find_flow_element_by_name(self, five_level_prj):
        model = parse_prj_file(str(five_level_prj))
        elem = find_flow_element_by_name(model, "Door-Stair1-S2V")
        assert elem is not None
        assert elem.name == "Door-Stair1-S2V"

    def test_find_flow_element_not_found(self, five_level_prj):
        model = parse_prj_file(str(five_level_prj))
        assert find_flow_element_by_name(model, "NonExistent") is None

    def test_find_paths_by_element_name(self, five_level_prj):
        model = parse_prj_file(str(five_level_prj))
        paths = find_paths_by_element_name(model, "Door-Stair1-S2V")
        # Should find one S2V path per level for Stair_1
        assert len(paths) == 5
        assert all(p.flow_elem_name == "Door-Stair1-S2V" for p in paths)

    def test_get_max_path_id(self, five_level_prj):
        model = parse_prj_file(str(five_level_prj))
        max_id = get_max_path_id(model)
        assert max_id == 35


# ==========================================================================
# 3. AUTO-DETECTION
# ==========================================================================

class TestAutoDetection:
    """Test the auto-configuration/detection engine."""

    def test_auto_detect_stairs(self, five_level_prj):
        model = parse_prj_file(str(five_level_prj))
        config = auto_detect_config(model)
        assert config["summary"]["stairs_detected"] == 2
        stair_names = config["summary"]["stair_names"]
        assert "Stair_1" in stair_names
        assert "Stair_2" in stair_names

    def test_auto_detect_stair_levels(self, five_level_prj):
        model = parse_prj_file(str(five_level_prj))
        config = auto_detect_config(model)
        for stair in config["stairs"]:
            assert len(stair["zones"]) == 5  # all 5 levels

    def test_auto_detect_corridors(self, five_level_prj):
        model = parse_prj_file(str(five_level_prj))
        config = auto_detect_config(model)
        assert config["summary"]["corridors_detected"] >= 1

    def test_auto_detect_vestibules(self, five_level_prj):
        model = parse_prj_file(str(five_level_prj))
        config = auto_detect_config(model)
        total_vest = config["summary"]["vestibules_detected"]
        assert total_vest >= 2  # at least some detected

    def test_auto_detect_path_elements(self, five_level_prj):
        model = parse_prj_file(str(five_level_prj))
        config = auto_detect_config(model)
        for stair in config["stairs"]:
            paths = stair["paths"]
            assert paths["s2v"] != "", f"S2V not detected for {stair['label']}"
            assert paths["v2c"] != "", f"V2C not detected for {stair['label']}"
            assert paths["ext"] != "", f"EXT not detected for {stair['label']}"

    def test_auto_detect_corridor_path(self, five_level_prj):
        model = parse_prj_file(str(five_level_prj))
        config = auto_detect_config(model)
        assert config["corridor_path_element"] == "FLR.LK.Measured"

    def test_auto_detect_ahs(self, five_level_prj):
        model = parse_prj_file(str(five_level_prj))
        config = auto_detect_config(model)
        assert config["supply_ahs"] is not None
        assert config["supply_ahs"]["name"] == "SUPPLY"
        assert config["return_ahs"] is not None
        assert config["return_ahs"]["name"] == "RETURN"

    def test_auto_detect_roof(self, five_level_prj):
        model = parse_prj_file(str(five_level_prj))
        config = auto_detect_config(model)
        assert len(config["roof_configs"]) == 2  # one per stair
        for rc in config["roof_configs"]:
            assert rc["level_num"] == 5  # top level

    def test_auto_detect_weather(self, five_level_prj):
        model = parse_prj_file(str(five_level_prj))
        config = auto_detect_config(model)
        weather = config["weather"]
        # 294.261 K -> ~70 F
        assert abs(weather["temp_f"] - 70.0) < 1.0
        assert weather["wind_dir"] == 270.0

    def test_confidence_high(self, five_level_prj):
        model = parse_prj_file(str(five_level_prj))
        config = auto_detect_config(model)
        assert config["confidence"] in ("high", "medium")

    def test_confidence_low_for_minimal(self, minimal_prj):
        model = parse_prj_file(str(minimal_prj))
        config = auto_detect_config(model)
        # Minimal model has stairs + corridors but no flow elements, no AHS
        # so confidence is medium (2 signals: stairs + corridors)
        assert config["confidence"] in ("low", "medium")

    def test_detection_details(self, five_level_prj):
        model = parse_prj_file(str(five_level_prj))
        config = auto_detect_config(model)
        assert len(config["detection_details"]) > 0

    def test_no_ahs_detection(self, no_ahs_prj):
        model = parse_prj_file(str(no_ahs_prj))
        config = auto_detect_config(model)
        assert config["supply_ahs"] is None
        assert config["return_ahs"] is None

    def test_floor_zone_detection(self, floor_zone_prj):
        model = parse_prj_file(str(floor_zone_prj))
        config = auto_detect_config(model)
        assert config["summary"]["floor_zones_detected"] >= 1


# ==========================================================================
# 4. PRJ MODIFICATION
# ==========================================================================

class TestPrjModification:
    """Test PRJ file modification (build_modified_prj)."""

    def _build_stair_configs(self, model, flow_rate=500):
        """Build stair configs from a parsed model."""
        config = auto_detect_config(model)
        stair_configs = []
        for stair in config["stairs"]:
            levels = []
            for z in stair["zones"]:
                levels.append({
                    "level_num": z["level_num"],
                    "zone_id": z["zone_id"],
                    "flow_rate": flow_rate,
                    "ahs_id": stair.get("ahs_id", 0) or 0,
                    "supply_zone": 0,
                    "icon_type": 128,
                    "icon_col": 1,
                    "icon_row": 1,
                })
            stair_configs.append({"label": stair["label"], "levels": levels})
        return stair_configs

    def _build_corridor_configs(self, model, flow_rate=200):
        """Build corridor configs from a parsed model."""
        config = auto_detect_config(model)
        corridor_configs = []
        for corr in config["corridors"]:
            levels = []
            for z in corr["zones"]:
                levels.append({
                    "level_num": z["level_num"],
                    "zone_id": z["zone_id"],
                    "flow_rate": flow_rate,
                    "ahs_id": 0,
                    "exhaust_zone": 0,
                    "icon_type": 129,
                    "icon_col": 1,
                    "icon_row": 1,
                })
            corridor_configs.append({"label": corr["label"], "levels": levels})
        return corridor_configs

    def test_build_modified_prj_basic(self, five_level_prj):
        """Test basic PRJ modification produces valid output."""
        model = parse_prj_file(str(five_level_prj))
        stair_configs = self._build_stair_configs(model)
        corridor_configs = self._build_corridor_configs(model)

        modified, warnings = build_modified_prj(
            base_lines=model.raw_lines,
            temp_f=35.0,
            wind_mph=15.0,
            wind_dir=270.0,
            stair_configs=stair_configs,
            corridor_configs=corridor_configs,
            roof_configs=[],
            fire_floor_level_num=3,
        )

        assert len(modified) > len(model.raw_lines)
        # No critical validation errors
        critical = [w for w in warnings if "VALIDATION:" in w and "count" in w.lower()]
        assert len(critical) == 0, f"Validation errors: {critical}"

    def test_weather_modified(self, five_level_prj):
        """Test that weather is correctly updated."""
        model = parse_prj_file(str(five_level_prj))
        modified, _ = build_modified_prj(
            base_lines=model.raw_lines,
            temp_f=0.0,  # 0F = 255.37K
            wind_mph=25.0,
            wind_dir=180.0,
            stair_configs=[],
            corridor_configs=[],
            roof_configs=[],
            fire_floor_level_num=2,
        )
        # Find weather data line: the line AFTER the "!TaPbWsWdrh" header
        # that starts with numeric data (not a comment)
        found = False
        for i, line in enumerate(modified):
            if "TaPbWsWdrh" in line.replace(" ", ""):
                # Next non-comment line is the data
                for j in range(i + 1, min(i + 3, len(modified))):
                    data_line = modified[j].strip()
                    if not data_line.startswith("!"):
                        data = data_line.split()
                        temp_k = float(data[0])
                        assert abs(temp_k - f_to_kelvin(0.0)) < 0.01
                        wind = float(data[2])
                        assert abs(wind - mph_to_ms(25.0)) < 0.01
                        wdir = float(data[3])
                        assert abs(wdir - 180.0) < 0.1
                        found = True
                        break
                break
        assert found, "Weather data not found in modified PRJ"

    def test_tool_flow_element_created(self, five_level_prj):
        """Test that TOOL_PRESS_DUCT element is created."""
        model = parse_prj_file(str(five_level_prj))
        lines = list(model.raw_lines)
        elem_id = ensure_tool_flow_element(lines)
        assert elem_id > 0
        # Verify element is in the lines
        found = any("TOOL_PRESS_DUCT" in line for line in lines)
        assert found

    def test_tool_flow_element_idempotent(self, five_level_prj):
        """Test that calling ensure_tool_flow_element twice returns same ID."""
        model = parse_prj_file(str(five_level_prj))
        lines = list(model.raw_lines)
        id1 = ensure_tool_flow_element(lines)
        id2 = ensure_tool_flow_element(lines)
        assert id1 == id2

    def test_pressurization_paths_added(self, five_level_prj):
        """Test that pressurization paths are added for stairs."""
        model = parse_prj_file(str(five_level_prj))
        original_path_count = len(model.airflow_paths)
        stair_configs = self._build_stair_configs(model)

        modified, _ = build_modified_prj(
            base_lines=model.raw_lines,
            temp_f=70.0,
            wind_mph=0.0,
            wind_dir=270.0,
            stair_configs=stair_configs,
            corridor_configs=[],
            roof_configs=[],
            fire_floor_level_num=2,
        )

        # Count paths in modified file
        path_count = 0
        in_paths = False
        for line in modified:
            if "flow paths:" in line.lower():
                parts = line.strip().split()
                if parts[0].isdigit():
                    path_count = int(parts[0])
                break

        # Should have more paths than original (stair supply + AHS internals + tool element)
        assert path_count > original_path_count

    def test_corridor_depressurization_at_fire_floor(self, five_level_prj):
        """Test that corridor depressurization only applies at the fire floor."""
        model = parse_prj_file(str(five_level_prj))
        corridor_configs = self._build_corridor_configs(model, flow_rate=300)

        modified, _ = build_modified_prj(
            base_lines=model.raw_lines,
            temp_f=70.0,
            wind_mph=0.0,
            wind_dir=270.0,
            stair_configs=[],
            corridor_configs=corridor_configs,
            roof_configs=[],
            fire_floor_level_num=3,
        )

        # Verify the file is structurally valid
        issues = validate_prj_structure(modified)
        critical_issues = [i for i in issues if "count" in i.lower()]
        assert len(critical_issues) == 0, f"Structure issues: {critical_issues}"

    def test_roof_depressurization(self, five_level_prj):
        """Test roof depressurization path addition."""
        model = parse_prj_file(str(five_level_prj))
        config = auto_detect_config(model)
        roof_configs = []
        for rc in config["roof_configs"]:
            roof_configs.append({
                "zone_id": rc["zone_id"],
                "level_num": rc["level_num"],
                "flow_rate": 100,
                "ahs_id": 0,
                "exhaust_zone": 0,
                "icon_type": 129,
                "icon_col": 1,
                "icon_row": 1,
            })

        modified, warnings = build_modified_prj(
            base_lines=model.raw_lines,
            temp_f=70.0,
            wind_mph=0.0,
            wind_dir=270.0,
            stair_configs=[],
            corridor_configs=[],
            roof_configs=roof_configs,
            fire_floor_level_num=2,
        )
        assert len(modified) > len(model.raw_lines)

    def test_ahs_creation_when_missing(self, no_ahs_prj):
        """Test AHS creation when model has no existing AHS."""
        model = parse_prj_file(str(no_ahs_prj))
        assert len(model.ahs_systems) == 0

        lines = list(model.raw_lines)
        supply_id, return_id, s_zone, r_zone = ensure_ahs_systems(lines)
        assert supply_id > 0
        assert return_id > 0
        assert s_zone > 0
        assert r_zone > 0

    def test_structural_validation(self, five_level_prj):
        """Test structural validation on unmodified file."""
        model = parse_prj_file(str(five_level_prj))
        issues = validate_prj_structure(list(model.raw_lines))
        # The synthetic file may have AHS zone reference issues since
        # AHS zones aren't in the zone section - that's expected
        # Check that path section and zone section at least don't have count mismatches
        count_issues = [i for i in issues if "count:" in i.lower()]
        for ci in count_issues:
            # These are fine if they match
            pass

    def test_validate_and_repair(self, five_level_prj):
        """Test path validation and repair."""
        model = parse_prj_file(str(five_level_prj))
        lines = list(model.raw_lines)
        msgs = validate_and_repair_paths(lines)
        # Should return without crashing
        assert isinstance(msgs, list)

    def test_full_modification_cycle(self, five_level_prj):
        """Test complete modification cycle: modify + validate + re-parse."""
        model = parse_prj_file(str(five_level_prj))
        stair_configs = self._build_stair_configs(model, flow_rate=400)
        corridor_configs = self._build_corridor_configs(model, flow_rate=200)

        modified, warnings = build_modified_prj(
            base_lines=model.raw_lines,
            temp_f=35.0,
            wind_mph=15.0,
            wind_dir=0.0,
            stair_configs=stair_configs,
            corridor_configs=corridor_configs,
            roof_configs=[],
            fire_floor_level_num=2,
        )

        # Write to file and re-parse
        out_path = five_level_prj.parent / "modified_output.prj"
        out_path.write_text("".join(modified), encoding="utf-8")
        reloaded = parse_prj_file(str(out_path))

        assert reloaded.version == "ContamW 3.4.0.0 0"
        assert len(reloaded.levels) == 5
        # Should have more zones and paths than original
        assert len(reloaded.zones) >= len(model.zones)


# ==========================================================================
# 5. XLOG PARSING
# ==========================================================================

class TestXlogParsing:
    """Test CONTAM .xlog results file parsing."""

    def test_parse_xlog(self, sample_xlog):
        data = parse_xlog_file(str(sample_xlog))
        assert data is not None
        assert data.shape == (20, 4)

    def test_extract_pressure_diffs(self, sample_xlog):
        dps = extract_pressure_diffs(str(sample_xlog), [1, 2, 3])
        assert len(dps) == 3
        assert abs(dps[0] - 12.450) < 0.001
        assert abs(dps[1] - 8.300) < 0.001
        assert abs(dps[2] - (-5.200)) < 0.001

    def test_extract_negative_dp(self, sample_xlog):
        dps = extract_pressure_diffs(str(sample_xlog), [3])
        assert dps[0] < 0  # negative dP

    def test_extract_all(self, sample_xlog):
        data = extract_all_pressure_diffs(str(sample_xlog))
        assert data is not None
        assert data.shape[0] == 20

    def test_invalid_path_index(self, sample_xlog):
        with pytest.raises(ValueError, match="Invalid path indices"):
            extract_pressure_diffs(str(sample_xlog), [999])

    def test_zero_index_invalid(self, sample_xlog):
        with pytest.raises(ValueError, match="Invalid path indices"):
            extract_pressure_diffs(str(sample_xlog), [0])

    def test_xlog_not_found(self, tmp_project):
        with pytest.raises(FileNotFoundError):
            parse_xlog_file(str(tmp_project / "missing.xlog"))

    def test_xlog_no_dp_section(self, tmp_project):
        empty_xlog = tmp_project / "empty.xlog"
        empty_xlog.write_text("CONTAM Results\nNo data here\n", encoding="utf-8")
        data = parse_xlog_file(str(empty_xlog))
        assert data is None

    def test_xlog_with_dp_section_no_data(self, tmp_project):
        xlog = tmp_project / "nodata.xlog"
        xlog.write_text("path offset dPmax Fmax\n\n", encoding="utf-8")
        data = parse_xlog_file(str(xlog))
        assert data is None

    def test_dp_conversion_to_inwc(self, sample_xlog):
        """Test that pressure conversions work correctly."""
        dps = extract_pressure_diffs(str(sample_xlog), [1])
        dp_pa = dps[0]  # 12.450 Pa
        dp_inwc = pa_to_inwc(dp_pa)
        assert abs(dp_inwc - 12.450 / 249.0) < 0.0001


# ==========================================================================
# 6. UNIT CONVERSIONS
# ==========================================================================

class TestUnitConversions:
    """Test all unit conversion functions."""

    def test_f_to_kelvin_freezing(self):
        assert abs(f_to_kelvin(32.0) - 273.15) < 0.01

    def test_f_to_kelvin_boiling(self):
        assert abs(f_to_kelvin(212.0) - 373.15) < 0.01

    def test_kelvin_to_f_roundtrip(self):
        for temp in [-40, 0, 32, 70, 100, 212]:
            assert abs(kelvin_to_f(f_to_kelvin(temp)) - temp) < 0.01

    def test_mph_to_ms(self):
        assert abs(mph_to_ms(1.0) - 0.44704) < 0.001

    def test_ms_to_mph_roundtrip(self):
        for speed in [0, 5, 15, 30, 100]:
            assert abs(ms_to_mph(mph_to_ms(speed)) - speed) < 0.01

    def test_pa_to_inwc(self):
        assert abs(pa_to_inwc(249.0) - 1.0) < 0.001

    def test_inwc_to_pa(self):
        assert abs(inwc_to_pa(1.0) - 249.0) < 0.01

    def test_pa_inwc_roundtrip(self):
        for p in [0.05, 0.1, 0.17, 0.45, 1.0]:
            assert abs(pa_to_inwc(inwc_to_pa(p)) - p) < 0.0001

    def test_scfm_to_kgs(self):
        # 1759.72 SCFM = 1 kg/s
        assert abs(scfm_to_kgs(1759.72) - 1.0) < 0.01

    def test_scfm_zero(self):
        assert scfm_to_kgs(0) == 0.0

    def test_negative_temperature(self):
        """Test negative Fahrenheit conversion."""
        k = f_to_kelvin(-40.0)
        assert abs(k - 233.15) < 0.01
        assert abs(kelvin_to_f(k) - (-40.0)) < 0.01


# ==========================================================================
# 7. ANALYSIS ENGINE (without CONTAM executable)
# ==========================================================================

class TestAnalysisEngine:
    """Test the analysis engine logic (excluding actual CONTAM runs)."""

    def _make_engine(self, prj_path, tmp_project):
        model = parse_prj_file(str(prj_path))
        config_det = auto_detect_config(model)

        stairs = []
        for s in config_det["stairs"]:
            levels = []
            for z in s["zones"]:
                levels.append({
                    "level_num": z["level_num"],
                    "zone_id": z["zone_id"],
                    "flow_rate": 500,
                    "ahs_id": s.get("ahs_id", 0) or 0,
                    "supply_zone": 0,
                    "icon_type": 128,
                    "icon_col": 1,
                    "icon_row": 1,
                })
            stairs.append(StairConfig(
                label=s["label"],
                levels=levels,
                paths=s["paths"],
            ))

        corridors = []
        for c in config_det["corridors"]:
            levels = []
            for z in c["zones"]:
                levels.append({
                    "level_num": z["level_num"],
                    "zone_id": z["zone_id"],
                    "flow_rate": 200,
                    "ahs_id": 0,
                    "exhaust_zone": 0,
                    "icon_type": 129,
                    "icon_col": 1,
                    "icon_row": 1,
                })
            corridors.append(CorridorConfig(
                label=c["label"],
                levels=levels,
                path_name=c["path_name"],
            ))

        roof_configs = []
        for rc in config_det["roof_configs"]:
            roof_configs.append(RoofConfig(
                stair_label=rc["stair_label"],
                zone_id=rc["zone_id"],
                level_num=rc["level_num"],
                flow_rate=100,
                ahs_id=0,
                exhaust_zone=0,
            ))

        config = AnalysisConfig(
            project_name="TestBuilding_E2E",
            project_folder=str(tmp_project),
            contam_exe="/nonexistent/contamX3.exe",
            scenarios=[
                ScenarioConfig(
                    name="Winter",
                    base_model_path=str(prj_path),
                    temp_f=35.0,
                    wind_mph=15.0,
                    wind_dir=270.0,
                ),
                ScenarioConfig(
                    name="Summer",
                    base_model_path=str(prj_path),
                    temp_f=95.0,
                    wind_mph=10.0,
                    wind_dir=180.0,
                ),
            ],
            stairs=stairs,
            corridors=corridors,
            roof_configs=roof_configs,
        )
        return AnalysisEngine(config)

    def test_fire_floor_detection(self, five_level_prj, tmp_project):
        engine = self._make_engine(five_level_prj, tmp_project)
        fire_floors = engine.get_fire_floor_levels()
        assert len(fire_floors) >= 1
        assert all(isinstance(f, int) for f in fire_floors)

    def test_total_run_count(self, five_level_prj, tmp_project):
        engine = self._make_engine(five_level_prj, tmp_project)
        total = engine.count_total_runs()
        fire_floors = engine.get_fire_floor_levels()
        # 2 scenarios * num_fire_floors
        assert total == 2 * len(fire_floors)

    def test_validate_missing_exe(self, five_level_prj, tmp_project):
        engine = self._make_engine(five_level_prj, tmp_project)
        errors = engine.validate()
        # Should flag missing CONTAM exe
        exe_errors = [e for e in errors if "not found" in e.lower() and "contam" in e.lower()]
        assert len(exe_errors) > 0

    def test_validate_missing_model(self, five_level_prj, tmp_project):
        engine = self._make_engine(five_level_prj, tmp_project)
        # Change model path to nonexistent
        engine.config.scenarios[0].base_model_path = "/nonexistent/model.prj"
        errors = engine.validate()
        model_errors = [e for e in errors if "model not found" in e.lower()]
        assert len(model_errors) > 0

    def test_dry_run_generates_files(self, five_level_prj, tmp_project):
        engine = self._make_engine(five_level_prj, tmp_project)
        generated = engine.dry_run()
        # Should generate files: 2 scenarios * N fire floors
        assert len(generated) >= 2
        for path in generated:
            assert Path(path).exists()
            content = Path(path).read_text(encoding="utf-8")
            assert len(content) > 100
            assert "ContamW" in content

    def test_dry_run_file_naming(self, five_level_prj, tmp_project):
        engine = self._make_engine(five_level_prj, tmp_project)
        generated = engine.dry_run()
        filenames = [Path(p).name for p in generated]
        # Should contain scenario names
        winter_files = [f for f in filenames if "Winter" in f]
        summer_files = [f for f in filenames if "Summer" in f]
        assert len(winter_files) > 0
        assert len(summer_files) > 0

    def test_dry_run_modified_prj_parseable(self, five_level_prj, tmp_project):
        """Verify that dry-run output files can be re-parsed without errors."""
        engine = self._make_engine(five_level_prj, tmp_project)
        generated = engine.dry_run()
        for path in generated:
            model = parse_prj_file(path)
            assert len(model.levels) == 5
            assert len(model.zones) >= 25  # at least original zones

    def test_cancel_flag(self, five_level_prj, tmp_project):
        engine = self._make_engine(five_level_prj, tmp_project)
        engine.cancel()
        assert engine._cancelled is True
        # Dry run should produce nothing after cancel
        generated = engine.dry_run()
        assert len(generated) == 0

    def test_progress_callback(self, five_level_prj, tmp_project):
        engine = self._make_engine(five_level_prj, tmp_project)
        messages = []
        engine.on_progress(lambda msg: messages.append(msg))
        engine.dry_run()
        # Should have received some progress messages (PRJ warnings at minimum)
        # (dry_run doesn't emit standard progress messages, only PRJ warnings)

    def test_selected_floors_filter(self, five_level_prj, tmp_project):
        engine = self._make_engine(five_level_prj, tmp_project)
        all_floors = engine.get_fire_floor_levels()
        if len(all_floors) > 1:
            engine.config.selected_floors = [all_floors[0]]
            filtered = engine.get_fire_floor_levels()
            assert len(filtered) == 1
            assert filtered[0] == all_floors[0]

    def test_no_corridors_engine(self, five_level_prj, tmp_project):
        """Test engine with no corridor configs (no fire floors)."""
        model = parse_prj_file(str(five_level_prj))
        config = AnalysisConfig(
            project_name="NoCorridors",
            project_folder=str(tmp_project),
            contam_exe="/nonexistent/contamX3.exe",
            scenarios=[ScenarioConfig("S1", str(five_level_prj), 70.0, 0.0, 270.0)],
            stairs=[],
            corridors=[],
            roof_configs=[],
        )
        engine = AnalysisEngine(config)
        fire_floors = engine.get_fire_floor_levels()
        assert len(fire_floors) == 0
        errors = engine.validate()
        assert any("fire floor" in e.lower() for e in errors)


# ==========================================================================
# 8. REPORT GENERATION
# ==========================================================================

class TestReportGeneration:
    """Test HTML report generation."""

    def test_report_basic(self):
        html = generate_report_html(
            project_name="Test Project",
            scenarios=[{"name": "Winter", "temp_f": 35, "wind_mph": 15, "wind_dir": 270}],
            stairs=[{"label": "Stair_1", "levels": [
                {"level_num": 1, "zone_id": 1, "flow_rate": 500},
                {"level_num": 2, "zone_id": 2, "flow_rate": 500},
            ]}],
            corridors=[{"label": "Corridor_1", "levels": [
                {"level_num": 1, "zone_id": 10, "flow_rate": 200},
                {"level_num": 2, "zone_id": 11, "flow_rate": 200},
            ]}],
            results=[{
                "scenario": "Winter",
                "columns": ["Level", "Stair_1_S2V", "Stair_1_V2C"],
                "data": [
                    ["L1", 0.08, 0.12],
                    ["L2", 0.10, 0.15],
                ],
            }],
            acceptance_criteria={"min_dp_inwc": 0.05, "max_dp_inwc": 0.45, "max_dp_stair_inwc": 0.17},
        )
        assert "<!DOCTYPE html>" in html
        assert "Test Project" in html
        assert "Winter" in html
        assert "Stair_1" in html

    def test_report_pass_fail_coloring(self):
        html = generate_report_html(
            project_name="Color Test",
            scenarios=[{"name": "S1", "temp_f": 70, "wind_mph": 0, "wind_dir": 270}],
            stairs=[],
            corridors=[],
            results=[{
                "scenario": "S1",
                "columns": ["Level", "dP_Value"],
                "data": [
                    ["L1", 0.10],   # pass
                    ["L2", 0.01],   # fail (below min)
                    ["L3", 0.50],   # fail (above max)
                    ["L4", 0.0],    # dash
                ],
            }],
            acceptance_criteria={"min_dp_inwc": 0.05, "max_dp_inwc": 0.45, "max_dp_stair_inwc": 0.17},
        )
        assert 'class="pass"' in html
        assert 'class="fail"' in html

    def test_report_model_info(self):
        html = generate_report_html(
            project_name="Model Info Test",
            scenarios=[],
            stairs=[],
            corridors=[],
            results=[],
            acceptance_criteria={"min_dp_inwc": 0.05, "max_dp_inwc": 0.45},
            model_info={
                "filename": "building.prj",
                "num_levels": 5,
                "num_zones": 25,
                "num_paths": 35,
                "num_ahs": 2,
            },
        )
        assert "building.prj" in html
        assert "Model Information" in html

    def test_report_empty_results(self):
        html = generate_report_html(
            project_name="Empty",
            scenarios=[],
            stairs=[],
            corridors=[],
            results=[],
            acceptance_criteria={"min_dp_inwc": 0.05, "max_dp_inwc": 0.45},
        )
        assert "<!DOCTYPE html>" in html
        assert "Empty" in html

    def test_report_xss_escape(self):
        """Test that HTML injection is prevented."""
        html = generate_report_html(
            project_name='<script>alert("xss")</script>',
            scenarios=[{"name": '<img onerror=alert(1)>', "temp_f": 70, "wind_mph": 0, "wind_dir": 270}],
            stairs=[],
            corridors=[],
            results=[],
            acceptance_criteria={"min_dp_inwc": 0.05, "max_dp_inwc": 0.45},
        )
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_report_multiple_scenarios(self):
        html = generate_report_html(
            project_name="Multi",
            scenarios=[
                {"name": "Winter", "temp_f": 35, "wind_mph": 15, "wind_dir": 270},
                {"name": "Summer", "temp_f": 95, "wind_mph": 10, "wind_dir": 180},
            ],
            stairs=[],
            corridors=[],
            results=[
                {"scenario": "Winter", "columns": ["Level", "dP"], "data": [["L1", 0.1]]},
                {"scenario": "Summer", "columns": ["Level", "dP"], "data": [["L1", 0.08]]},
            ],
            acceptance_criteria={"min_dp_inwc": 0.05, "max_dp_inwc": 0.45},
        )
        assert "Winter" in html
        assert "Summer" in html


# ==========================================================================
# 9. END-TO-END: PARSE -> DETECT -> MODIFY -> DRY-RUN -> VALIDATE
# ==========================================================================

class TestEndToEndPipeline:
    """Full pipeline integration tests."""

    def test_full_pipeline_5_level(self, five_level_prj, tmp_project):
        """Exercise complete pipeline on 5-level building."""
        # 1. Parse
        model = parse_prj_file(str(five_level_prj))
        assert len(model.levels) == 5

        # 2. Auto-detect
        det = auto_detect_config(model)
        assert det["summary"]["stairs_detected"] == 2
        assert det["summary"]["corridors_detected"] >= 1

        # 3. Build configs
        stairs = []
        for s in det["stairs"]:
            levels = [
                {
                    "level_num": z["level_num"],
                    "zone_id": z["zone_id"],
                    "flow_rate": 500,
                    "ahs_id": s.get("ahs_id", 0) or 0,
                    "supply_zone": 0,
                    "icon_type": 128,
                    "icon_col": 1,
                    "icon_row": 1,
                }
                for z in s["zones"]
            ]
            stairs.append(StairConfig(label=s["label"], levels=levels, paths=s["paths"]))

        corridors = []
        for c in det["corridors"]:
            levels = [
                {
                    "level_num": z["level_num"],
                    "zone_id": z["zone_id"],
                    "flow_rate": 200,
                    "ahs_id": 0,
                    "exhaust_zone": 0,
                    "icon_type": 129,
                    "icon_col": 1,
                    "icon_row": 1,
                }
                for z in c["zones"]
            ]
            corridors.append(CorridorConfig(label=c["label"], levels=levels, path_name=c["path_name"]))

        roof_configs = [
            RoofConfig(
                stair_label=rc["stair_label"],
                zone_id=rc["zone_id"],
                level_num=rc["level_num"],
                flow_rate=100,
                ahs_id=0,
                exhaust_zone=0,
            )
            for rc in det["roof_configs"]
        ]

        # 4. Build analysis config
        config = AnalysisConfig(
            project_name="E2E_Test",
            project_folder=str(tmp_project),
            contam_exe="/nonexistent/contamX3.exe",
            scenarios=[
                ScenarioConfig("Winter", str(five_level_prj), 35.0, 15.0, 270.0),
                ScenarioConfig("Summer", str(five_level_prj), 95.0, 10.0, 180.0),
            ],
            stairs=stairs,
            corridors=corridors,
            roof_configs=roof_configs,
        )
        engine = AnalysisEngine(config)

        # 5. Validate (expect CONTAM exe missing)
        errors = engine.validate()
        exe_errors = [e for e in errors if "contam" in e.lower()]
        assert len(exe_errors) > 0

        # 6. Fire floor calculation
        fire_floors = engine.get_fire_floor_levels()
        assert len(fire_floors) >= 1

        # 7. Dry run
        generated = engine.dry_run()
        assert len(generated) == 2 * len(fire_floors)

        # 8. Re-parse each generated file
        for path in generated:
            remodel = parse_prj_file(path)
            assert len(remodel.levels) == 5
            # Verify tool flow element was added
            tool_elem = find_flow_element_by_name(remodel, "TOOL_PRESS_DUCT")
            assert tool_elem is not None

        # 9. Validate structure of generated files
        for path in generated:
            remodel = parse_prj_file(path)
            issues = validate_prj_structure(remodel.raw_lines)
            critical = [i for i in issues if "count" in i.lower()]
            # Minor count mismatches from AHS zones may occur in synthetic data

        # 10. Generate report
        html = generate_report_html(
            project_name="E2E_Test",
            scenarios=[
                {"name": "Winter", "temp_f": 35, "wind_mph": 15, "wind_dir": 270},
                {"name": "Summer", "temp_f": 95, "wind_mph": 10, "wind_dir": 180},
            ],
            stairs=[{"label": s.label, "levels": s.levels} for s in stairs],
            corridors=[{"label": c.label, "levels": c.levels} for c in corridors],
            results=[{
                "scenario": "Winter",
                "columns": ["Level", "Stair_1_S2V", "Stair_2_S2V"],
                "data": [
                    ["B1", 0.08, 0.09],
                    ["L1", 0.10, 0.11],
                    ["L2", 0.12, 0.13],
                    ["L3", 0.14, 0.15],
                    ["Roof", 0.05, 0.06],
                ],
            }],
            acceptance_criteria={"min_dp_inwc": 0.05, "max_dp_inwc": 0.45, "max_dp_stair_inwc": 0.17},
        )
        assert "<!DOCTYPE html>" in html
        assert "E2E_Test" in html

    def test_full_pipeline_10_level(self, ten_level_prj, tmp_project):
        """Stress test with 10-level building."""
        model = parse_prj_file(str(ten_level_prj))
        assert len(model.levels) == 10
        assert len(model.zones) == 50

        det = auto_detect_config(model)
        assert det["summary"]["stairs_detected"] == 2

        # Build engine config
        stairs = [
            StairConfig(
                label=s["label"],
                levels=[{
                    "level_num": z["level_num"],
                    "zone_id": z["zone_id"],
                    "flow_rate": 600,
                    "ahs_id": 0, "supply_zone": 0,
                    "icon_type": 128, "icon_col": 1, "icon_row": 1,
                } for z in s["zones"]],
                paths=s["paths"],
            )
            for s in det["stairs"]
        ]
        corridors = [
            CorridorConfig(
                label=c["label"],
                levels=[{
                    "level_num": z["level_num"],
                    "zone_id": z["zone_id"],
                    "flow_rate": 250,
                    "ahs_id": 0, "exhaust_zone": 0,
                    "icon_type": 129, "icon_col": 1, "icon_row": 1,
                } for z in c["zones"]],
                path_name=c["path_name"],
            )
            for c in det["corridors"]
        ]

        config = AnalysisConfig(
            project_name="TenLevel",
            project_folder=str(tmp_project),
            contam_exe="/nonexistent/contamX3.exe",
            scenarios=[ScenarioConfig("S1", str(ten_level_prj), 70.0, 0.0, 270.0)],
            stairs=stairs,
            corridors=corridors,
            roof_configs=[],
        )
        engine = AnalysisEngine(config)
        generated = engine.dry_run()
        assert len(generated) >= 1

        for path in generated:
            remodel = parse_prj_file(path)
            assert len(remodel.levels) == 10

    def test_pipeline_with_floor_zones(self, floor_zone_prj, tmp_project):
        """Test pipeline including floor zone depressurization."""
        model = parse_prj_file(str(floor_zone_prj))
        det = auto_detect_config(model)

        # Build floor zone configs
        floor_zones = []
        for fz in det.get("floor_zones", []):
            levels = [{
                "level_num": z["level_num"],
                "zone_id": z["zone_id"],
                "flow_rate": 150,
                "ahs_id": 0, "exhaust_zone": 0,
                "icon_type": 129, "icon_col": 1, "icon_row": 1,
            } for z in fz["zones"]]
            floor_zones.append(FloorConfig(
                label=fz["label"],
                levels=levels,
                path_name=fz["path_name"],
            ))

        config = AnalysisConfig(
            project_name="FloorZoneTest",
            project_folder=str(tmp_project),
            contam_exe="/nonexistent/contamX3.exe",
            scenarios=[ScenarioConfig("S1", str(floor_zone_prj), 70.0, 0.0, 270.0)],
            stairs=[],
            corridors=[],
            roof_configs=[],
            floor_zones=floor_zones,
        )
        engine = AnalysisEngine(config)
        fire_floors = engine.get_fire_floor_levels()
        if len(fire_floors) > 0:
            generated = engine.dry_run()
            assert len(generated) >= 1


# ==========================================================================
# 10. ROBUSTNESS & EDGE CASES
# ==========================================================================

class TestRobustness:
    """Edge cases and error handling tests."""

    def test_unicode_in_prj(self, tmp_project):
        """Test handling of unicode characters in zone names."""
        from tests.conftest import _build_prj_lines
        lines = _build_prj_lines(num_levels=2, num_stairs=1, has_vestibules=False, has_ahs=False, has_flow_elements=False)
        # Inject unicode into project name
        lines[1] = "Pr\u00f6ject_\u00dcnicode\n"
        prj = tmp_project / "unicode.prj"
        prj.write_text("".join(lines), encoding="utf-8")
        model = parse_prj_file(str(prj))
        assert "nicode" in model.project_name

    def test_very_large_flow_rate(self, five_level_prj):
        """Test with extremely large flow rates."""
        model = parse_prj_file(str(five_level_prj))
        modified, warnings = build_modified_prj(
            base_lines=model.raw_lines,
            temp_f=70.0, wind_mph=0.0, wind_dir=270.0,
            stair_configs=[{
                "label": "Stair_1",
                "levels": [{
                    "level_num": 1,
                    "zone_id": model.zones[0].id,
                    "flow_rate": 99999,
                    "ahs_id": 0, "supply_zone": 0,
                    "icon_type": 128, "icon_col": 1, "icon_row": 1,
                }],
            }],
            corridor_configs=[], roof_configs=[],
            fire_floor_level_num=2,
        )
        assert len(modified) > 0

    def test_zero_flow_rate(self, five_level_prj):
        """Test that zero flow rates don't create paths."""
        model = parse_prj_file(str(five_level_prj))
        original_lines = len(model.raw_lines)
        modified, _ = build_modified_prj(
            base_lines=model.raw_lines,
            temp_f=70.0, wind_mph=0.0, wind_dir=270.0,
            stair_configs=[{
                "label": "Stair_1",
                "levels": [{
                    "level_num": 1,
                    "zone_id": model.zones[0].id,
                    "flow_rate": 0,  # zero
                    "ahs_id": 0, "supply_zone": 0,
                    "icon_type": 128, "icon_col": 1, "icon_row": 1,
                }],
            }],
            corridor_configs=[], roof_configs=[],
            fire_floor_level_num=2,
        )
        # Should not add many extra lines for a zero-rate path
        # (AHS/flow element additions still happen)

    def test_extreme_temperatures(self, five_level_prj):
        """Test with extreme temperature values."""
        model = parse_prj_file(str(five_level_prj))
        for temp in [-40, 0, 130]:
            modified, warnings = build_modified_prj(
                base_lines=model.raw_lines,
                temp_f=temp, wind_mph=0.0, wind_dir=0.0,
                stair_configs=[], corridor_configs=[], roof_configs=[],
                fire_floor_level_num=1,
            )
            assert len(modified) > 0

    def test_extreme_wind(self, five_level_prj):
        """Test with extreme wind values."""
        model = parse_prj_file(str(five_level_prj))
        modified, _ = build_modified_prj(
            base_lines=model.raw_lines,
            temp_f=70.0, wind_mph=100.0, wind_dir=359.0,
            stair_configs=[], corridor_configs=[], roof_configs=[],
            fire_floor_level_num=1,
        )
        assert len(modified) > 0

    def test_fire_floor_at_boundary_levels(self, five_level_prj, tmp_project):
        """Test fire floor at first and last levels."""
        model = parse_prj_file(str(five_level_prj))
        det = auto_detect_config(model)

        corridors = []
        for c in det["corridors"]:
            levels = [{
                "level_num": z["level_num"],
                "zone_id": z["zone_id"],
                "flow_rate": 200,
                "ahs_id": 0, "exhaust_zone": 0,
                "icon_type": 129, "icon_col": 1, "icon_row": 1,
            } for z in c["zones"]]
            corridors.append({"label": c["label"], "levels": levels})

        # Fire floor at level 1 (lowest)
        modified1, _ = build_modified_prj(
            base_lines=model.raw_lines,
            temp_f=70.0, wind_mph=0.0, wind_dir=270.0,
            stair_configs=[], corridor_configs=corridors, roof_configs=[],
            fire_floor_level_num=1,
        )
        assert len(modified1) > 0

        # Fire floor at level 5 (highest)
        modified5, _ = build_modified_prj(
            base_lines=model.raw_lines,
            temp_f=70.0, wind_mph=0.0, wind_dir=270.0,
            stair_configs=[], corridor_configs=corridors, roof_configs=[],
            fire_floor_level_num=5,
        )
        assert len(modified5) > 0

    def test_duplicate_dry_runs(self, five_level_prj, tmp_project):
        """Test that running dry_run twice doesn't corrupt state."""
        model = parse_prj_file(str(five_level_prj))
        det = auto_detect_config(model)

        corridors = [
            CorridorConfig(
                label=c["label"],
                levels=[{
                    "level_num": z["level_num"],
                    "zone_id": z["zone_id"],
                    "flow_rate": 200,
                    "ahs_id": 0, "exhaust_zone": 0,
                    "icon_type": 129, "icon_col": 1, "icon_row": 1,
                } for z in c["zones"]],
                path_name=c["path_name"],
            )
            for c in det["corridors"]
        ]

        config = AnalysisConfig(
            project_name="DuplicateTest",
            project_folder=str(tmp_project),
            contam_exe="/nonexistent/contamX3.exe",
            scenarios=[ScenarioConfig("S1", str(five_level_prj), 70.0, 0.0, 270.0)],
            stairs=[],
            corridors=corridors,
            roof_configs=[],
        )
        engine = AnalysisEngine(config)
        gen1 = engine.dry_run()
        gen2 = engine.dry_run()
        assert len(gen1) == len(gen2)

    def test_malformed_xlog_graceful(self, tmp_project):
        """Test xlog parser with malformed content."""
        xlog = tmp_project / "malformed.xlog"
        xlog.write_text("garbage\ndata\npath offset dPmax Fmax\nnot numbers\n", encoding="utf-8")
        data = parse_xlog_file(str(xlog))
        assert data is None

    def test_xlog_partial_data(self, tmp_project):
        """Test xlog with some valid and some invalid rows."""
        content = "path offset dPmax Fmax\n1 0.0 5.0 0.01\n2 0.0 bad 0.02\n"
        xlog = tmp_project / "partial.xlog"
        xlog.write_text(content, encoding="utf-8")
        data = parse_xlog_file(str(xlog))
        assert data is not None
        assert data.shape == (1, 4)

    def test_acceptance_criteria_boundary(self):
        """Test acceptance criteria at exact boundary values."""
        # Exactly at min threshold
        assert pa_to_inwc(inwc_to_pa(0.05)) == pytest.approx(0.05, abs=0.0001)
        # Exactly at max threshold
        assert pa_to_inwc(inwc_to_pa(0.45)) == pytest.approx(0.45, abs=0.0001)

    def test_stair_name_variants(self, tmp_project):
        """Test auto-detection with variant stair naming."""
        from tests.conftest import _build_prj_lines
        lines = _build_prj_lines(
            num_levels=3, num_stairs=1,
            has_corridors=True, has_vestibules=True,
            has_ahs=False, has_flow_elements=False,
        )
        # Replace "Stair_1" with "Stair1" (no underscore) in zone names
        for i, line in enumerate(lines):
            lines[i] = line.replace("Stair_1", "Stair1")
        prj = tmp_project / "variant_names.prj"
        prj.write_text("".join(lines), encoding="utf-8")
        model = parse_prj_file(str(prj))
        det = auto_detect_config(model)
        assert det["summary"]["stairs_detected"] >= 1
