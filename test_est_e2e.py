"""
End-to-end simulation of the PRJ → Estimation Tool flow.

Simulates:
  1. User drops a .prj file on the estimation page
  2. POST /api/estimation/extract-from-prj
  3. Response data → applyPrjData() → setFormVal() for each field
  4. Verify every estimation input is correctly populated
  5. Verify the populated values can then be used with /api/estimation/run
"""
import json
import sys
sys.path.insert(0, "/home/user/SGH/contam-pressure-tool")

from fastapi.testclient import TestClient
from app import app

client = TestClient(app)

PRJ_FILES = [
    "Projects/CAA Base Model.prj",
    "5411_WinterWind_Level-EM.prj",
]

# HTML form element IDs and the JSON key path that populates them
BUILDING_FIELDS = {
    "est-n-floors-above": ("building", "n_floors_above"),
    "est-n-floors-below": ("building", "n_floors_below"),
    "est-floor-height":   ("building", "floor_height"),
    "est-bldg-perimeter": ("building", "building_perimeter"),
    "est-floor-area":     ("building", "floor_area"),
}
CONDITION_FIELDS = {
    "est-t-winter":    ("conditions", "T_outdoor_winter"),
    "est-wind-speed":  ("conditions", "wind_speed"),
    "est-wind-dir":    ("conditions", "wind_direction"),
}
ELEVATOR_FIELDS = {
    "est-elev-n":    ("elevators", "n_shafts"),
    "est-elev-area": ("elevators", "shaft_area"),
}

STAIRWELL_KEYS = ["label", "area", "doorW", "doorH", "gap", "doors",
                  "bottom", "top", "extWalls", "extLen", "perim"]

# HTML input constraints (min/max from estimation.html)
INPUT_CONSTRAINTS = {
    "est-n-floors-above": (2, 99),
    "est-n-floors-below": (0, 10),
    "est-floor-height":   (2.5, 6),
    "est-bldg-perimeter": (20, 600),
    "est-floor-area":     (100, 10000),
    "est-elev-n":         (None, None),  # no explicit bounds in html
    "est-elev-area":      (None, None),
}

STAIR_CONSTRAINTS = {
    "area":     (3, 200),
    "doorW":    (0.8, 1.5),
    "doorH":    (1.8, 2.5),
    "gap":      (1, 10),
    "doors":    (1, 2),
    "extWalls": (0, 4),
    "extLen":   (0, 20),
    "perim":    (4, 80),
}

errors = []
warnings = []

def err(msg):
    errors.append(msg)
    print(f"  ERROR: {msg}")

def warn(msg):
    warnings.append(msg)
    print(f"  WARN:  {msg}")


for prj_file in PRJ_FILES:
    print(f"\n{'='*70}")
    print(f"Testing: {prj_file}")
    print('='*70)

    # ----- Step 1: POST the file to the extraction endpoint -----
    print("\n[Step 1] POST /api/estimation/extract-from-prj")
    try:
        with open(prj_file, "rb") as f:
            resp = client.post(
                "/api/estimation/extract-from-prj",
                files={"file": (prj_file.split("/")[-1], f, "application/octet-stream")}
            )
    except Exception as e:
        err(f"Request crashed: {e}")
        continue

    print(f"  Status: {resp.status_code}")
    if resp.status_code != 200:
        err(f"Expected 200, got {resp.status_code}: {resp.text[:300]}")
        continue

    data = resp.json()
    print(f"  Response keys: {list(data.keys())}")

    # ----- Step 2: Validate response structure -----
    print("\n[Step 2] Validate response structure")
    for section in ("building", "stairwells", "elevators", "conditions"):
        if section not in data:
            err(f"Missing top-level key: '{section}'")
        else:
            print(f"  '{section}': present")

    building = data.get("building", {})
    conditions = data.get("conditions", {})
    elevators = data.get("elevators", {})
    stairwells_data = data.get("stairwells", [])

    # ----- Step 3: Validate building fields (non-None, non-zero) -----
    print("\n[Step 3] Validate building fields -> form mappings")
    for form_id, (section_name, key) in BUILDING_FIELDS.items():
        section = data.get(section_name, {})
        val = section.get(key)
        if val is None:
            err(f"  {form_id} <- {section_name}.{key} is None")
        elif val == 0 and key != "n_floors_below":
            warn(f"  {form_id} <- {section_name}.{key} = 0 (possibly unexpected)")
        else:
            print(f"  {form_id} <- {section_name}.{key} = {val}")

        # Check HTML constraints
        if form_id in INPUT_CONSTRAINTS and val is not None:
            lo, hi = INPUT_CONSTRAINTS[form_id]
            if lo is not None and val < lo:
                warn(f"  {form_id}={val} is below HTML min={lo} (browser may show invalid)")
            if hi is not None and val > hi:
                warn(f"  {form_id}={val} exceeds HTML max={hi} (browser may show invalid)")

    # ----- Step 4: Validate condition fields -----
    print("\n[Step 4] Validate condition fields -> form mappings")
    for form_id, (section_name, key) in CONDITION_FIELDS.items():
        section = data.get(section_name, {})
        val = section.get(key)
        if val is None:
            err(f"  {form_id} <- {section_name}.{key} is None")
        else:
            print(f"  {form_id} <- {section_name}.{key} = {val}")

    # ----- Step 5: Validate elevator fields -----
    print("\n[Step 5] Validate elevator fields -> form mappings")
    for form_id, (section_name, key) in ELEVATOR_FIELDS.items():
        section = data.get(section_name, {})
        val = section.get(key)
        if val is None:
            err(f"  {form_id} <- {section_name}.{key} is None")
        else:
            print(f"  {form_id} <- {section_name}.{key} = {val}")

    # ----- Step 6: Validate stairwells -----
    print(f"\n[Step 6] Validate stairwells ({len(stairwells_data)} detected)")
    if len(stairwells_data) == 0:
        warn("  No stairwells detected from PRJ file — default single stairwell will be used")

    for i, stair in enumerate(stairwells_data):
        missing = [k for k in STAIRWELL_KEYS if k not in stair]
        if missing:
            err(f"  Stair[{i}] '{stair.get('label','?')}': missing keys: {missing}")
        else:
            print(f"  Stair[{i}] '{stair['label']}': area={stair['area']}m², "
                  f"floors {stair['bottom']}-{stair['top']}, "
                  f"extWalls={stair['extWalls']}, perim={stair['perim']}m")

        # Check constraints
        for key, (lo, hi) in STAIR_CONSTRAINTS.items():
            val = stair.get(key)
            if val is not None:
                if lo is not None and val < lo:
                    warn(f"  Stair[{i}] '{stair.get('label','?')}': {key}={val} < HTML min={lo}")
                if hi is not None and val > hi:
                    warn(f"  Stair[{i}] '{stair.get('label','?')}': {key}={val} > HTML max={hi}")

    # ----- Step 7: Simulate applyPrjData logic -----
    print(f"\n[Step 7] Simulate applyPrjData -> setFormVal calls")
    # This simulates what the JS does: for each setFormVal(id, value), check that
    # the value is not undefined/null (which would cause the JS to skip the field)
    form_values = {}

    # Building
    for form_id, (section_name, key) in BUILDING_FIELDS.items():
        val = data.get(section_name, {}).get(key)
        if val is not None:
            form_values[form_id] = val
        else:
            err(f"  setFormVal('{form_id}', undefined) — field will NOT be updated!")

    # Conditions (only set if not undefined)
    for form_id, (section_name, key) in CONDITION_FIELDS.items():
        val = data.get(section_name, {}).get(key)
        if val is not None:
            form_values[form_id] = val

    # Elevators (only set if not undefined)
    for form_id, (section_name, key) in ELEVATOR_FIELDS.items():
        val = data.get(section_name, {}).get(key)
        if val is not None:
            form_values[form_id] = val

    # Fire floor
    total = (building.get("n_floors_above") or 10) + (building.get("n_floors_below") or 0)
    form_values["est-fire-floor"] = max(1, total // 2)

    print(f"  Form fields that would be set: {len(form_values)}")
    for fid, fval in form_values.items():
        print(f"    #{fid} = {fval}")

    # ----- Step 8: Verify the data can be used for estimation run -----
    print(f"\n[Step 8] Verify full estimation run with extracted values")

    # Build the body that collectInputs() would produce
    stair_inputs = []
    for i, s in enumerate(stairwells_data if stairwells_data else [{
        "label": "Stair A", "area": 10, "doorW": 1.1, "doorH": 2.1,
        "gap": 3, "doors": 1, "bottom": 1, "top": total, "extWalls": 1, "extLen": 4,
        "perim": 6 * (10 / 2) ** 0.5,
    }]):
        stair_inputs.append({
            "label": s.get("label", f"Stair {chr(65+i)}"),
            "cross_section_area": s.get("area", 10),
            "cross_section_perimeter": s.get("perim", 6 * (s.get("area", 10) / 2) ** 0.5),
            "door_width": s.get("doorW", 1.1),
            "door_height": s.get("doorH", 2.1),
            "door_gap_mm": s.get("gap", 3),
            "doors_per_floor": s.get("doors", 1),
            "serves_bottom": s.get("bottom", 1),
            "serves_top": s.get("top", total),
            "n_exterior_walls": s.get("extWalls", 1),
            "exterior_wall_length": s.get("extLen", 4),
        })

    run_body = {
        "building": {
            "n_floors_above": building.get("n_floors_above", 10),
            "n_floors_below": building.get("n_floors_below", 0),
            "floor_height": building.get("floor_height", 3.5),
            "building_perimeter": building.get("building_perimeter", 120),
            "floor_area": building.get("floor_area", 1000),
            "wall_construction": "curtain_wall",
        },
        "stairwells": stair_inputs,
        "elevators": {
            "n_shafts": elevators.get("n_shafts", 2),
            "shaft_area": elevators.get("shaft_area", 6),
            "door_type": "center_opening",
            "vent_area": 0,
        },
        "conditions": {
            "T_outdoor_winter": conditions.get("T_outdoor_winter", -18),
            "T_outdoor_summer": 35,
            "T_indoor": 22,
            "T_fire": 927,
            "wind_speed": conditions.get("wind_speed", 0),
            "wind_direction": conditions.get("wind_direction", 0),
            "P_atm": 101325,
            "n_open_doors": 1,
            "is_sprinklered": True,
            "design_fire_hrr": 1055,
        },
        "leakage": {
            "exterior_wall": "tight",
            "interior_wall": "average",
            "floor_ceiling": "average",
            "stair_door": "average",
            "elevator_door": "average",
        },
        "criteria": {
            "min_dp_closed": 12.5,
            "max_dp_closed": 87,
            "min_door_velocity": 1.0,
            "max_door_force": 133,
            "floor_exhaust_dp": 50,
            "door_closer_force": 44.5,
        },
        "stairwell_temp_assumption": "match_indoor",
        "fire_floor": form_values.get("est-fire-floor", max(1, total // 2)),
    }

    try:
        run_resp = client.post("/api/estimation/run", json=run_body)
        print(f"  /api/estimation/run status: {run_resp.status_code}")
        if run_resp.status_code == 200:
            run_data = run_resp.json()
            if run_data.get("status") == "ok":
                n_stairs = len(run_data.get("stair_results", []))
                all_met = run_data.get("all_constraints_met")
                print(f"  Estimation result: status=ok, {n_stairs} stair results, "
                      f"all_constraints_met={all_met}")
                for sr in run_data.get("stair_results", []):
                    print(f"    {sr['label']}: supply_design={sr['q_supply_design_cfm']} CFM")
                if run_data.get("exhaust_result"):
                    er = run_data["exhaust_result"]
                    print(f"    Exhaust: {er['q_exhaust_total_cfm']} CFM (std)")
            else:
                err(f"  Estimation run returned status={run_data.get('status')}: "
                    f"{run_data.get('detail', 'unknown')}")
        else:
            err(f"  Estimation run HTTP {run_resp.status_code}: {run_resp.text[:300]}")
    except Exception as e:
        err(f"  Estimation run crashed: {e}")


# ----- Summary -----
print(f"\n{'='*70}")
print("END-TO-END SIMULATION SUMMARY")
print('='*70)
print(f"  Files tested: {len(PRJ_FILES)}")
print(f"  Errors:   {len(errors)}")
print(f"  Warnings: {len(warnings)}")

if errors:
    print("\nERRORS:")
    for e in errors:
        print(f"  - {e}")

if warnings:
    print("\nWARNINGS:")
    for w in warnings:
        print(f"  - {w}")

if not errors:
    print("\n  ALL CHECKS PASSED")

sys.exit(1 if errors else 0)
