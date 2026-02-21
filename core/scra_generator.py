"""SCRA Generator — Orchestrates Smoke Control Rational Analysis.

Takes a CONTAM .prj file and building description, runs the analytical
estimation calculations (EQ-01 through EQ-26), extracts CONTAM results
when available, and assembles all data needed for the SCRA report.
"""

import logging
import math
import re
from typing import Dict, List, Optional, Tuple

from .estimation_engine import (
    EstimationEngine,
    cms_to_cfm,
    n_to_lbf,
    pa_to_inwg,
    eq01_air_density,
    eq02_door_leakage_area,
    eq07_stack_effect,
    eq10b_total_door_force,
    eq03_orifice_flow_volume,
    eq12_required_open_door_flow,
    R_AIR,
    STACK_COEFF,
)
from .estimation_models import (
    BuildingGeometry,
    DesignConditions,
    DesignCriteria,
    ElevatorShaftConfig,
    EstimationConfig,
    EstimationResult,
    LeakageData,
    StairwellGeometry,
)
from .prj_parser import parse_prj_file
from .scra_models import (
    ADORequirement,
    BuildingDescription,
    ClimateData,
    CONTAMResult,
    InitiatingDevice,
    LeakageComponent,
    PassiveSubzone,
    ProjectInfo,
    SCRAConfig,
    SCRAResults,
    SequenceStep,
    SmokeZone,
    StairDefinition,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Temperature conversion helpers
# ---------------------------------------------------------------------------
def _f_to_c(t_f: float) -> float:
    return (t_f - 32.0) * 5.0 / 9.0


def _c_to_k(t_c: float) -> float:
    return t_c + 273.15


def _f_to_k(t_f: float) -> float:
    return _c_to_k(_f_to_c(t_f))


def _m_to_ft(m: float) -> float:
    return m * 3.28084


def _ft_to_m(ft: float) -> float:
    return ft / 3.28084


def _sqm_to_sqft(m2: float) -> float:
    return m2 * 10.7639


# ---------------------------------------------------------------------------
# PRJ File Extraction
# ---------------------------------------------------------------------------
def extract_building_from_prj(prj_path: str) -> dict:
    """Parse a CONTAM .prj file and extract building geometry.

    Returns a dict with:
        levels: [{index, name, ref_height, delta_height}, ...]
        zones: [{id, name, level_num, volume, temperature}, ...]
        stairs: [stair_label, ...]
        floor_heights: {level_index: height_m}
        floor_labels: {level_index: label}
        n_levels: int
        outdoor_temp_K: float
    """
    model = parse_prj_file(prj_path)

    levels = []
    floor_heights = {}
    floor_labels = {}

    for lvl in model.levels:
        levels.append({
            "index": lvl.index,
            "name": lvl.name,
            "ref_height": lvl.ref_height,
            "delta_height": lvl.delta_height,
        })
        floor_heights[lvl.index] = lvl.ref_height
        floor_labels[lvl.index] = lvl.name

    # Auto-detect stairwells from zone names
    stair_labels = set()
    stair_zones = {}  # stair_label -> [zone objects]
    for zone in model.zones:
        name = zone.name.strip()
        # Match patterns like "Stair_1", "Stair1", "ST1", "S1"
        m = re.match(r'^(Stair[_\s]?\d+|ST\d+|S\d+)(?:_.*)?$', name, re.IGNORECASE)
        if m:
            base = m.group(1).replace('_', '').replace(' ', '')
            # Normalize: "Stair1" style
            num_match = re.search(r'(\d+)', base)
            if num_match:
                label = f"Stair{num_match.group(1)}"
                stair_labels.add(label)
                stair_zones.setdefault(label, []).append(zone)

    # Detect vestibules
    vestibule_zones = {}
    for zone in model.zones:
        name = zone.name.strip()
        m = re.match(r'^(Stair[_\s]?\d+|ST\d+|S\d+)[_\s]*(V|Vest|Vestibule)', name, re.IGNORECASE)
        if m:
            base = m.group(1).replace('_', '').replace(' ', '')
            num_match = re.search(r'(\d+)', base)
            if num_match:
                label = f"Stair{num_match.group(1)}"
                vestibule_zones.setdefault(label, []).append(zone)

    # Detect elevator zones
    elevator_zones = []
    for zone in model.zones:
        name = zone.name.strip().lower()
        if any(k in name for k in ['elev', 'shaft', 'lift', 'hoistway']):
            if not any(k in name for k in ['stair', 'corr', 'lobby']):
                elevator_zones.append(zone)

    # Extract weather
    outdoor_temp_K = model.weather.get('temperature', 293.15) if hasattr(model, 'weather') and model.weather else 293.15

    # Build stair info
    stairs_info = []
    for label in sorted(stair_labels):
        zones = stair_zones.get(label, [])
        has_vestibule = label in vestibule_zones
        # Determine served levels
        served_levels = set()
        for z in zones:
            served_levels.add(z.level_num)
        stairs_info.append({
            "label": label,
            "has_vestibule": has_vestibule,
            "n_floors_served": len(served_levels),
            "served_levels": sorted(served_levels),
        })

    return {
        "levels": levels,
        "zones": [{"id": z.id, "name": z.name, "level_num": z.level_num,
                    "volume": z.volume, "temperature": z.temperature}
                   for z in model.zones],
        "stairs": stairs_info,
        "elevator_zones": len(elevator_zones),
        "floor_heights": floor_heights,
        "floor_labels": floor_labels,
        "n_levels": len(levels),
        "outdoor_temp_K": outdoor_temp_K,
    }


# ---------------------------------------------------------------------------
# Default SCRA Leakage Table
# ---------------------------------------------------------------------------
DEFAULT_LEAKAGE_TABLE = [
    LeakageComponent("Door (3 ft wide)", "0.385 sq ft/door", 0.0358, 0.65),
    LeakageComponent("Elevator door (3.5 ft wide)", "0.53 sq ft/door", 0.0492, 0.65),
    LeakageComponent("Interior wall", "0.0018 sq ft per 1 sq ft wall", 0.000167, 0.65),
    LeakageComponent("Exterior wall", "0.00017 sq ft per 1 sq ft wall", 0.0000158, 0.65),
    LeakageComponent("Corridor wall (fire partition)", "0.00035 sq ft per 1 sq ft wall", 0.0000325, 0.65),
    LeakageComponent("Floor assembly", "0.00017 sq ft per 1 sq ft floor", 0.0000158, 0.65),
    LeakageComponent("Exit stairwell wall", "0.00011 sq ft per 1 sq ft wall", 0.0000102, 0.65),
    LeakageComponent("Elevator shaft wall", "0.00084 sq ft per 1 sq ft wall", 0.0000780, 0.65),
]


# ---------------------------------------------------------------------------
# Default Sequence of Operations
# ---------------------------------------------------------------------------
def _build_default_sequence(config: SCRAConfig) -> List[SequenceStep]:
    """Build the standard sequence of operations."""
    scope = config.building.scope_description or "fire floor"
    stair_labels = ", ".join(s.label for s in config.stairs) if config.stairs else "all stairs"

    return [
        SequenceStep(1,
            "Initiate evacuation sequence and associated alarms per NFPA 72 and "
            "local requirements, i.e., evacuation signals to operate in the smoke zone "
            "of origin, the smoke zone above, and the smoke zone below.",
            [f"When the smoke zone of origin is {scope}, the evacuation sequence will "
             "sound on the Fire Floor, the Level above, and the Level below."]),
        SequenceStep(2,
            f"Start all stairwell pressurization fans serving smokeproof enclosures at {stair_labels}.",
            []),
        SequenceStep(3,
            "Shut down all shared HVAC systems serving the smoke zone of origin "
            "and the immediately adjacent smoke zones.",
            ["Supply and return systems with a capacity of greater than 2,000 cfm "
             "provided with duct detectors will shut down when the associated supply "
             "or return duct detector activates."]),
        SequenceStep(4,
            "Close combination fire/smoke dampers (CFSDs) serving common supply and "
            "exhaust shafts throughout.",
            []),
        SequenceStep(5,
            "Open CFSD serving the smoke exhaust shaft on the fire floor only.",
            []),
        SequenceStep(6,
            "Start smoke exhaust fan serving the common smoke exhaust shaft.",
            []),
        SequenceStep(7,
            "Release doors on hold-opens or initiate closure of automatic-closing fire "
            "assemblies at elevator lobbies, in the smoke zone of origin, and the "
            "immediately adjacent smoke zones.",
            []),
        SequenceStep(8,
            "Deploy horizontal fire shutter for convenience stair zone and associated "
            "lobby on the floor of alarm.",
            []),
        SequenceStep(9,
            "Recall elevators as described in the Smoke Control Functional Matrix.",
            []),
    ]


# ---------------------------------------------------------------------------
# Main SCRA Generator
# ---------------------------------------------------------------------------
class SCRAGenerator:
    """Generate a complete Smoke Control Rational Analysis."""

    def __init__(self, config: SCRAConfig):
        self.config = config
        self.results = SCRAResults(config=config)

    def extract_from_prj(self) -> dict:
        """Extract building info from the PRJ file."""
        if not self.config.prj_file_path:
            return {}
        try:
            return extract_building_from_prj(self.config.prj_file_path)
        except Exception as e:
            logger.error(f"Failed to parse PRJ file: {e}")
            return {}

    def auto_populate_from_prj(self, prj_data: dict) -> None:
        """Populate SCRA config from extracted PRJ data."""
        if not prj_data:
            return

        # Floor heights and labels
        self.config.floor_heights = prj_data.get("floor_heights", {})
        self.config.floor_labels = prj_data.get("floor_labels", {})

        # Auto-detect stairs if none defined
        if not self.config.stairs:
            for si in prj_data.get("stairs", []):
                served = si.get("served_levels", [])
                sd = StairDefinition(
                    label=si["label"],
                    stair_id=si["label"],
                    has_vestibule=si.get("has_vestibule", True),
                    n_floors_served=si.get("n_floors_served", 0),
                    serves_bottom_level=min(served) if served else 1,
                    serves_top_level=max(served) if served else 1,
                )
                self.config.stairs.append(sd)

        # Set floor labels on stairs
        for stair in self.config.stairs:
            bottom = stair.serves_bottom_level
            top = stair.serves_top_level
            bottom_label = self.config.floor_labels.get(bottom, str(bottom))
            top_label = self.config.floor_labels.get(top, str(top))
            stair.serves_levels = f"{bottom_label} through {top_label}"
            if stair.n_floors_served == 0:
                stair.n_floors_served = top - bottom + 1

    def build_estimation_config(self) -> EstimationConfig:
        """Convert SCRA config to estimation engine config."""
        bldg = self.config.building
        climate = self.config.climate
        heights = self.config.floor_heights

        # Determine floor-to-floor height from PRJ data
        sorted_heights = sorted(heights.values()) if heights else []
        if len(sorted_heights) >= 2:
            deltas = [sorted_heights[i+1] - sorted_heights[i]
                      for i in range(len(sorted_heights)-1)]
            avg_height = sum(deltas) / len(deltas)
        else:
            avg_height = 3.5  # default

        # Count floors above/below grade
        n_below = bldg.subterranean_levels
        n_above = bldg.total_stories + bldg.above_grade_parking

        # Build stairwell geometries
        stairwells = []
        for sd in self.config.stairs:
            sg = StairwellGeometry(
                label=sd.label,
                cross_section_perimeter=sd.cross_section_perimeter_m,
                cross_section_area=sd.cross_section_area_m2,
                door_width=sd.door_width_m,
                door_height=sd.door_height_m,
                door_gap_mm=sd.door_gap_mm,
                doors_per_floor=sd.doors_per_floor,
                serves_bottom=1,  # 1-indexed for engine
                serves_top=sd.serves_top_level - sd.serves_bottom_level + 1 + n_below,
                n_exterior_walls=sd.n_exterior_walls,
                exterior_wall_length=sd.exterior_wall_length_m,
            )
            stairwells.append(sg)

        # If no stairs defined, create a default
        if not stairwells:
            stairwells = [StairwellGeometry(label="Stair 1")]

        # Design conditions
        cond = DesignConditions(
            T_outdoor_winter=climate.winter_design_db_C,
            T_outdoor_summer=climate.summer_design_db_C,
            T_indoor=climate.indoor_design_temp_C,
            T_fire=300.0,  # default fire temp
            wind_speed=0.0,  # base case: no wind
            wind_direction=0.0,
            P_atm=101325.0,
            n_open_doors=1,
            is_sprinklered=bldg.is_sprinklered,
        )

        # Design criteria (per LABC / CBC)
        criteria = DesignCriteria(
            min_dp_closed=12.5,       # 0.05 in. w.g. = 12.5 Pa
            max_dp_closed=87.0,       # ~0.35 in. w.g.
            min_door_velocity=1.0,
            max_door_force=133.0,     # 30 lbf = 133 N
            floor_exhaust_dp=25.0,    # 0.10 in. w.g. = 25 Pa
            door_closer_force=55.0,
            handle_to_latch=0.075,
        )

        return EstimationConfig(
            building=BuildingGeometry(
                n_floors_above=n_above,
                n_floors_below=n_below,
                floor_height=avg_height,
                building_perimeter=120.0,  # default
                floor_area=1000.0,         # default
            ),
            stairwells=stairwells,
            elevators=ElevatorShaftConfig(
                n_shafts=max(1, self.config.building.total_stories // 10),
            ),
            conditions=cond,
            leakage=LeakageData(
                use_crack_method_for_stair_door=True,
            ),
            criteria=criteria,
            fire_floor=n_below + (bldg.scope_bottom_level if bldg.scope_bottom_level > 0
                                  else 1),
        )

    def run_estimation(self) -> EstimationResult:
        """Run the analytical estimation engine."""
        est_config = self.build_estimation_config()
        engine = EstimationEngine(est_config)
        result = engine.run_full()

        # Store results back into stair definitions
        for i, sr in enumerate(result.stair_results):
            if i < len(self.config.stairs):
                self.config.stairs[i].supply_closed_cfm = cms_to_cfm(sr.q_supply_closed)
                self.config.stairs[i].supply_open_cfm = cms_to_cfm(sr.q_supply_open)
                self.config.stairs[i].supply_design_cfm = cms_to_cfm(sr.q_supply_design)

        # Build stair supply summary
        for sr in result.stair_results:
            self.results.stair_supply_summary[sr.label] = {
                "closed_cfm": cms_to_cfm(sr.q_supply_closed),
                "open_cfm": cms_to_cfm(sr.q_supply_open),
                "design_cfm": cms_to_cfm(sr.q_supply_design),
                "closed_cms": sr.q_supply_closed,
                "open_cms": sr.q_supply_open,
                "design_cms": sr.q_supply_design,
            }

        # Determine ADO requirements
        criteria = est_config.criteria
        for sr in result.stair_results:
            for fr in sr.floor_results:
                force_lbf = n_to_lbf(fr.f_total)
                dp_inwg = pa_to_inwg(fr.dp_net)
                if force_lbf > 15.0:  # Exceeds egress limit
                    ado = ADORequirement(
                        stair_label=sr.label,
                        floor_label=fr.floor_label,
                        dp_inwg=dp_inwg,
                        force_lbf=force_lbf,
                        reason=f"Door force {force_lbf:.1f} lbf exceeds 15 lbf",
                    )
                    self.results.ado_list.append(ado)

        self.results.estimation_results = result
        self.results.all_criteria_met = result.all_constraints_met
        self.results.warnings = result.warnings

        return result

    def populate_defaults(self) -> None:
        """Fill in default values for sections not provided by user."""
        # Default leakage table
        if not self.config.leakage_table:
            self.config.leakage_table = list(DEFAULT_LEAKAGE_TABLE)

        # Default sequence of operations
        if not self.config.sequence_steps:
            self.config.sequence_steps = _build_default_sequence(self.config)

        # Default smoke zones
        if not self.config.smoke_zones:
            bldg = self.config.building
            scope = f"Level {bldg.scope_bottom_level} to Level {bldg.scope_top_level}"
            stair_labels = ", ".join(s.label for s in self.config.stairs)
            self.config.smoke_zones = [
                SmokeZone(
                    zone_id=f"{bldg.tenant_name} Open Office Smoke Zone" if bldg.tenant_name
                            else "Open Office Smoke Zone",
                    levels=scope,
                    approach_items=[
                        f"Enclosed stairs will be smokeproof enclosures "
                        f"(pressurized per {self.config.code_references.get('smokeproof', 'LABC 909.20')}) "
                        f"using variable-speed drive fans.",
                        "Open office zones will be depressurized by variable-speed drive fans.",
                        f"Passive elevator lobbies ({self.config.code_references.get('high_rise', 'LABC 403')}.4.7).",
                        "All other enclosed spaces within each smoke zone are passive subzones.",
                    ],
                ),
            ]

        # Default passive subzones
        if not self.config.passive_subzones:
            scope = (f"Levels {self.config.building.scope_bottom_level} through "
                     f"{self.config.building.scope_top_level}")
            self.config.passive_subzones = [
                PassiveSubzone(
                    subzone_type="Elevator Lobbies",
                    description="Passive elevator lobbies separated by one-hour fire partitions "
                                "with 45-min smoke control and draft doors.",
                    separation_type="one-hour fire partition",
                    levels=scope,
                    ato_status="unchanged",
                ),
                PassiveSubzone(
                    subzone_type="Small Utility Spaces",
                    description="Mechanical, electrical, janitor, and storage rooms treated as "
                                "passive subzones of the main floor.",
                    separation_type="fire-rated construction",
                    levels=scope,
                    ato_status="removed",
                    rationale="Reduces active depressurized volume, decreases number of dampers, "
                              "improves system reliability.",
                ),
            ]

        # Default initiating devices
        if not self.config.initiating_devices:
            self.config.initiating_devices = [
                InitiatingDevice("waterflow",
                    "Each smoke zone",
                    "Initiate smoke control per functional matrix"),
                InitiatingDevice("smoke_detector",
                    "Elevator lobbies, elevator machine rooms, duct",
                    "Initiate elevator recall, release hold-opens, start stair fans"),
                InitiatingDevice("manual_pull",
                    "Location approved by fire department",
                    "Initiate general alarm and smoke control"),
            ]

    def generate(self) -> SCRAResults:
        """Run the full SCRA generation pipeline.

        1. Extract building data from PRJ
        2. Auto-populate config from PRJ
        3. Fill in defaults
        4. Run estimation engine
        5. Assemble results

        Returns SCRAResults with all data needed for report generation.
        """
        # Step 1: Extract PRJ data
        prj_data = self.extract_from_prj()

        # Step 2: Auto-populate from PRJ
        self.auto_populate_from_prj(prj_data)

        # Step 3: Fill defaults
        self.populate_defaults()

        # Step 4: Run estimation
        self.run_estimation()

        return self.results
