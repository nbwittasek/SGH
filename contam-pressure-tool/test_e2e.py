"""End-to-end dry-run test for the CONTAM analysis pipeline.

Tests the full workflow:
1. Parse PRJ file
2. Auto-detect configuration
3. Build modified PRJ files (dry run)
4. Validate generated files
"""
import json
import sys
import os
import tempfile
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from core.prj_parser import parse_prj_file, auto_detect_config, find_paths_by_element_name
from core.prj_writer import build_modified_prj, ensure_ahs_systems
from core.analysis_engine import (
    AnalysisConfig, AnalysisEngine, ScenarioConfig,
    StairConfig, CorridorConfig, RoofConfig,
)
from core.units import f_to_kelvin, mph_to_ms


def test_parse_and_autodetect(prj_path):
    """Test parsing and auto-detection."""
    print(f"\n{'='*60}")
    print(f"TESTING: {Path(prj_path).name}")
    print(f"{'='*60}")

    # 1. Parse
    print("\n[1] Parsing PRJ file...")
    model = parse_prj_file(prj_path)
    print(f"    Levels: {len(model.levels)}")
    print(f"    Zones: {len(model.zones)}")
    print(f"    Flow Elements: {len(model.flow_elements)}")
    print(f"    Airflow Paths: {len(model.airflow_paths)}")
    print(f"    AHS Systems: {len(model.ahs_systems)}")
    assert len(model.levels) > 0, "No levels parsed"
    assert len(model.zones) > 0, "No zones parsed"
    assert len(model.flow_elements) > 0, "No flow elements parsed"
    assert len(model.airflow_paths) > 0, "No airflow paths parsed"
    print("    PASS")

    # 2. Auto-detect
    print("\n[2] Auto-detecting configuration...")
    config = auto_detect_config(model)
    print(f"    Confidence: {config['confidence']}")
    print(f"    Stairs detected: {config['summary']['stairs_detected']}")
    print(f"    Corridors detected: {config['summary']['corridors_detected']}")
    print(f"    Vestibules detected: {config['summary'].get('vestibules_detected', 0)}")
    print(f"    Detection details:")
    for d in config.get('detection_details', []):
        print(f"      - {d}")

    stairs = config['stairs']
    corridors = config['corridors']
    assert len(stairs) > 0, "No stairs detected"
    assert len(corridors) > 0, "No corridors detected"
    print("    PASS")

    # 3. Verify stair zone assignments
    print("\n[3] Verifying stair zone assignments...")
    for stair in stairs:
        zones_count = len(stair['zones'])
        paths = stair.get('paths', {})
        print(f"    {stair['label']}: {zones_count} zones, paths={list(k for k,v in paths.items() if v)}")
        assert zones_count > 0, f"Stair {stair['label']} has no zones"
        # Check zone IDs are valid
        for z in stair['zones']:
            zone_id = z.get('zone_id', 0)
            assert zone_id > 0, f"Stair {stair['label']} zone on level {z['level_num']} has invalid ID: {zone_id}"
    print("    PASS")

    # 4. Verify corridor zone assignments
    print("\n[4] Verifying corridor zone assignments...")
    for corr in corridors:
        zones_count = len(corr['zones'])
        print(f"    {corr['label']}: {zones_count} zones")
        assert zones_count > 0, f"Corridor {corr['label']} has no zones"
    print("    PASS")

    # 5. Verify path elements exist in model and have paths
    print("\n[5] Verifying path element references...")
    for stair in stairs:
        paths = stair.get('paths', {})
        for path_key, elem_name in paths.items():
            if not elem_name:
                continue
            matching = find_paths_by_element_name(model, elem_name)
            status = "OK" if len(matching) > 0 else "UNUSED"
            print(f"    {stair['label']}.{path_key} = '{elem_name}' -> {len(matching)} paths [{status}]")
            # All detected elements must have at least one path (since we filter by used_elem_ids)
            assert len(matching) > 0, f"Path element '{elem_name}' detected but has no airflow paths"

    corr_path = config.get('corridor_path_element', '')
    if corr_path:
        matching = find_paths_by_element_name(model, corr_path)
        print(f"    Corridor path = '{corr_path}' -> {len(matching)} paths")
        assert len(matching) > 0, f"Corridor path element '{corr_path}' not found"
    print("    PASS")

    return model, config


def test_prj_modification(model, config, prj_path):
    """Test PRJ file modification (weather, pressurization, AHS)."""
    print("\n[6] Testing PRJ modification...")

    stairs = config['stairs']
    corridors = config['corridors']
    roof_configs = config.get('roof_configs', [])

    # Build stair configs
    stair_configs = []
    for stair in stairs:
        levels = []
        for z in stair['zones']:
            levels.append({
                'level_num': z['level_num'],
                'zone_id': z['zone_id'],
                'flow_rate': 1000,  # Test flow rate: 1000 SCFM
                'ahs_id': stair.get('ahs_id', 0),
                'supply_zone': 0,
                'icon_type': 128,
                'icon_col': 1,
                'icon_row': 1,
            })
        stair_configs.append({
            'label': stair['label'],
            'levels': levels,
        })

    # Build corridor configs (use first few levels as fire floors)
    corr_configs = []
    for corr in corridors:
        levels = []
        for z in corr['zones'][:5]:  # First 5 levels as fire floors
            levels.append({
                'level_num': z['level_num'],
                'zone_id': z['zone_id'],
                'flow_rate': 500,  # Test flow rate
                'ahs_id': corr.get('ahs_id', 0),
                'exhaust_zone': 0,
                'icon_type': 129,
                'icon_col': 1,
                'icon_row': 1,
            })
        corr_configs.append({
            'label': corr['label'],
            'levels': levels,
        })

    # Build roof configs
    roof_cfgs = []
    for rc in roof_configs:
        roof_cfgs.append({
            'zone_id': rc.get('zone_id', 0),
            'level_num': rc.get('level_num', 0),
            'flow_rate': 500,
            'ahs_id': 0,
            'exhaust_zone': 0,
            'icon_type': 129,
            'icon_col': 1,
            'icon_row': 1,
        })

    # Pick a fire floor level
    fire_floor_level = corr_configs[0]['levels'][0]['level_num'] if corr_configs[0]['levels'] else 2

    # Build modified PRJ
    try:
        modified_lines = build_modified_prj(
            base_lines=model.raw_lines,
            temp_f=37.0,   # Winter
            wind_mph=20.0,
            wind_dir=270.0,
            stair_configs=stair_configs,
            corridor_configs=corr_configs,
            roof_configs=roof_cfgs,
            fire_floor_level_num=fire_floor_level,
            ahs_systems=model.ahs_systems,
        )
        print(f"    Modified PRJ: {len(modified_lines)} lines (original: {len(model.raw_lines)})")
        lines_added = len(modified_lines) - len(model.raw_lines)
        print(f"    Lines added: {lines_added}")
        assert len(modified_lines) > len(model.raw_lines), "Modified PRJ should have more lines than original"
    except Exception as e:
        print(f"    FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Write to temp file and verify it can be re-parsed
    print("\n[7] Verifying modified PRJ can be re-parsed...")
    with tempfile.NamedTemporaryFile(mode='w', suffix='.prj', delete=False, encoding='utf-8') as f:
        f.writelines(modified_lines)
        temp_path = f.name

    try:
        modified_model = parse_prj_file(temp_path)
        print(f"    Modified levels: {len(modified_model.levels)}")
        print(f"    Modified zones: {len(modified_model.zones)}")
        print(f"    Modified paths: {len(modified_model.airflow_paths)}")
        print(f"    Modified AHS: {len(modified_model.ahs_systems)}")

        # Verify more paths than original (pressurization paths added)
        orig_paths = len(model.airflow_paths)
        mod_paths = len(modified_model.airflow_paths)
        print(f"    Path count: {orig_paths} -> {mod_paths} (+{mod_paths - orig_paths})")
        assert mod_paths > orig_paths, "Modified PRJ should have more paths"

        # Verify AHS exists (even if original had none)
        if len(model.ahs_systems) == 0:
            print(f"    AHS auto-created: {len(modified_model.ahs_systems)} systems")
            assert len(modified_model.ahs_systems) >= 2, "Should have auto-created SUPPLY and RETURN AHS"

        # Verify weather was modified
        # Check the weather line in the modified file
        from core.prj_parser import check_keywords
        for i, line in enumerate(modified_lines):
            if check_keywords(line, "!TaPbWsWdrh"):
                weather_line = modified_lines[i + 1]
                parts = weather_line.split()
                temp_k = float(parts[0])
                expected_k = f_to_kelvin(37.0)
                assert abs(temp_k - expected_k) < 0.01, f"Temperature mismatch: {temp_k} vs {expected_k}"
                wind_ms = float(parts[2])
                expected_ms = mph_to_ms(20.0)
                assert abs(wind_ms - expected_ms) < 0.01, f"Wind speed mismatch: {wind_ms} vs {expected_ms}"
                print(f"    Weather: T={temp_k:.3f}K, Ws={wind_ms:.3f}m/s  PASS")
                break

        print("    PASS")

    except Exception as e:
        print(f"    FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        os.unlink(temp_path)

    return True


def test_dry_run(prj_path, config):
    """Test the full dry run via AnalysisEngine."""
    print("\n[8] Testing AnalysisEngine dry run...")

    stairs = config['stairs']
    corridors = config['corridors']

    # Build stair configs with paths
    stair_cfgs = []
    for stair in stairs:
        levels = []
        for z in stair['zones']:
            levels.append({
                'level_num': z['level_num'],
                'zone_id': z['zone_id'],
                'flow_rate': 1000,
                'ahs_id': stair.get('ahs_id', 0),
                'supply_zone': 0,
                'icon_type': 128,
                'icon_col': 1,
                'icon_row': 1,
            })
        stair_cfgs.append(StairConfig(
            label=stair['label'],
            levels=levels,
            paths=stair.get('paths', {}),
        ))

    # Build corridor configs
    corr_cfgs = []
    for corr in corridors:
        levels = []
        for z in corr['zones'][:3]:  # Use 3 fire floors for speed
            levels.append({
                'level_num': z['level_num'],
                'zone_id': z['zone_id'],
                'flow_rate': 500,
                'ahs_id': corr.get('ahs_id', 0),
                'exhaust_zone': 0,
                'icon_type': 129,
                'icon_col': 1,
                'icon_row': 1,
            })
        corr_cfgs.append(CorridorConfig(
            label=corr['label'],
            levels=levels,
            path_name=config.get('corridor_path_element', ''),
        ))

    with tempfile.TemporaryDirectory() as tmp_dir:
        scenarios = [
            ScenarioConfig("WinterWind", prj_path, 37.0, 20.0, 270.0),
            ScenarioConfig("SummerNoWind", prj_path, 93.0, 0.0, 270.0),
        ]

        analysis_config = AnalysisConfig(
            project_name="E2E Test",
            project_folder=tmp_dir,
            contam_exe="contamX3.exe",  # Doesn't need to exist for dry run
            scenarios=scenarios,
            stairs=stair_cfgs,
            corridors=corr_cfgs,
            roof_configs=[],
        )

        engine = AnalysisEngine(analysis_config)

        # Validate
        errors = engine.validate()
        warnings = [e for e in errors if e.startswith("Warning")]
        critical = [e for e in errors if not e.startswith("Warning")]
        print(f"    Validation: {len(critical)} errors, {len(warnings)} warnings")
        for w in warnings:
            print(f"      Warning: {w}")
        # Skip CONTAM exe check for dry run
        critical = [e for e in critical if "executable" not in e.lower()]
        if critical:
            for e in critical:
                print(f"      ERROR: {e}")

        # Count total runs
        fire_floors = engine.get_fire_floor_levels()
        total = engine.count_total_runs()
        print(f"    Fire floors: {len(fire_floors)} = {fire_floors}")
        print(f"    Total runs: {total} (2 scenarios x {len(fire_floors)} fire floors)")
        assert len(fire_floors) > 0, "No fire floors found"

        # Dry run
        generated = engine.dry_run()
        print(f"    Generated PRJ files: {len(generated)}")
        assert len(generated) == total, f"Expected {total} files, got {len(generated)}"

        # Verify each generated file can be parsed
        print("\n[9] Verifying generated PRJ files...")
        errors_found = 0
        for i, filepath in enumerate(generated):
            try:
                m = parse_prj_file(filepath)
                if i == 0:
                    print(f"    First file: {Path(filepath).name}")
                    print(f"      Zones: {len(m.zones)}, Paths: {len(m.airflow_paths)}, AHS: {len(m.ahs_systems)}")
            except Exception as e:
                print(f"    FAILED to parse {Path(filepath).name}: {e}")
                errors_found += 1

        if errors_found == 0:
            print(f"    All {len(generated)} files parsed successfully. PASS")
        else:
            print(f"    {errors_found} files failed to parse. FAIL")
            return False

    return True


def main():
    # Find PRJ files
    projects_dir = Path(__file__).parent / "Projects"
    prj_files = list(projects_dir.glob("*.prj"))

    if not prj_files:
        print("No .prj files found in Projects/")
        sys.exit(1)

    print(f"Found {len(prj_files)} PRJ files:")
    for f in prj_files:
        print(f"  - {f.name}")

    all_passed = True
    for prj_path in prj_files:
        try:
            model, config = test_parse_and_autodetect(str(prj_path))
            if not test_prj_modification(model, config, str(prj_path)):
                all_passed = False
                continue
            if not test_dry_run(str(prj_path), config):
                all_passed = False
        except Exception as e:
            print(f"\nFAILED: {e}")
            import traceback
            traceback.print_exc()
            all_passed = False

    print(f"\n{'='*60}")
    if all_passed:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
    print(f"{'='*60}")
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
