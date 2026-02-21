"""Data models for Smoke Control Rational Analysis (SCRA) generation.

Captures project description, building configuration, smoke zone definitions,
code references, and all inputs needed to produce a complete SCRA report
matching the format of the SGH reference document.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Project Metadata
# ---------------------------------------------------------------------------
@dataclass
class ProjectInfo:
    """Cover page / header information."""
    project_name: str = ""                # e.g. "Creative Artists Agency Tenant Space"
    project_number: str = ""              # e.g. "231440"
    project_address: str = ""             # e.g. "1950 Avenue of the Stars"
    project_city: str = ""                # e.g. "Los Angeles"
    project_state: str = "California"
    submittal_type: str = "First Submittal"
    report_date: str = ""                 # e.g. "18 February 2026"
    prepared_for_name: str = ""           # e.g. "Pacific Edge Projects"
    prepared_for_address: str = ""
    prepared_by_name: str = "Simpson Gumpertz & Heger Inc."
    prepared_by_address: str = ""
    prepared_by_phone: str = ""


# ---------------------------------------------------------------------------
# Building Description
# ---------------------------------------------------------------------------
@dataclass
class BuildingDescription:
    """Section 1 — Building description and scope."""
    building_name: str = ""               # e.g. "Culver City Center"
    building_abbreviation: str = ""       # e.g. "CCC"
    total_stories: int = 37               # Total above-grade stories
    above_grade_parking: int = 2          # Parking levels above grade
    subterranean_levels: int = 4          # Parking levels below grade
    building_type: str = "high-rise office tower"
    is_high_rise: bool = True
    is_sprinklered: bool = True

    # Scope of work
    tenant_name: str = ""                 # e.g. "CAA"
    scope_bottom_level: int = 4           # Bottom level of scope (inclusive)
    scope_top_level: int = 21             # Top level of scope (inclusive)
    scope_description: str = ""           # e.g. "Levels 4 through 21"

    # Level naming
    level_names: Dict[int, str] = field(default_factory=dict)
    # e.g. {-4: "P4", -3: "P3", ..., 0: "G", 1: "1", 2: "2", ...}

    # Base building SCRA reference
    base_scra_author: str = ""            # e.g. "CCI"
    base_scra_date: str = ""              # e.g. "23 March 2020"
    base_scra_revision: str = ""          # e.g. "Revision Bulletin #2.2 dated 20 May 2024"


# ---------------------------------------------------------------------------
# Climate / Design Conditions
# ---------------------------------------------------------------------------
@dataclass
class ClimateData:
    """Appendix A — Climate and temperature data."""
    weather_station: str = ""             # e.g. "Santa Monica Municipal Airport"
    winter_design_db: float = 44.4        # Winter 1% design dry-bulb (°F)
    summer_design_db: float = 83.7        # Summer 1% design dry-bulb (°F)
    indoor_design_temp: float = 68.0      # Indoor design temperature (°F)
    elevation: float = 0.0                # Site elevation (ft)
    # Converted to SI internally
    winter_design_db_C: float = 6.9
    summer_design_db_C: float = 28.7
    indoor_design_temp_C: float = 20.0


# ---------------------------------------------------------------------------
# Stairwell Definition (per stairwell)
# ---------------------------------------------------------------------------
@dataclass
class StairDefinition:
    """Individual stairwell for SCRA analysis."""
    label: str = "Stair 1"               # e.g. "Stair1", "Stair 2"
    stair_id: str = ""                    # Internal ID
    serves_levels: str = ""               # e.g. "B3 through 37"
    serves_bottom_level: int = 1
    serves_top_level: int = 37
    n_floors_served: int = 0              # Computed
    has_vestibule: bool = True
    is_smokeproof: bool = True            # Per LABC 909.20
    pressurization_type: str = "variable-speed drive"

    # Door specs
    door_width_m: float = 1.1            # m
    door_height_m: float = 2.1           # m
    door_gap_mm: float = 3.0             # mm
    doors_per_floor: int = 1
    door_leakage_area_m2: float = 0.02   # m² per door

    # Geometry
    cross_section_area_m2: float = 10.0  # m²
    cross_section_perimeter_m: float = 8.0  # m
    n_exterior_walls: int = 0
    exterior_wall_length_m: float = 0.0  # m per floor

    # Air transfer openings
    has_ato_stair_to_vestibule: bool = True  # Stair-to-vestibule ATO
    ato_fire_damper_rating: str = "90 min."

    # Results (filled by generator)
    supply_closed_cfm: float = 0.0
    supply_open_cfm: float = 0.0
    supply_design_cfm: float = 0.0


# ---------------------------------------------------------------------------
# Smoke Zone Definition
# ---------------------------------------------------------------------------
@dataclass
class SmokeZone:
    """Smoke zone description for Section 4."""
    zone_id: str = ""                     # e.g. "CAA Open Office Level XX"
    levels: str = ""                      # e.g. "Level 4 to Level 21"
    approach_items: List[str] = field(default_factory=list)
    # e.g. ["Smokeproof enclosures (pressurized per LABC 909.20)",
    #        "Open office zones depressurized", ...]


# ---------------------------------------------------------------------------
# Passive Subzone
# ---------------------------------------------------------------------------
@dataclass
class PassiveSubzone:
    """Description of a passive subzone type."""
    subzone_type: str = ""                # e.g. "Lounge", "Convenience Stair", "Utility"
    description: str = ""
    separation_type: str = ""             # e.g. "two-hour fire barrier"
    levels: str = ""                      # e.g. "Levels 4 through 21"
    ato_status: str = "removed"           # "removed", "unchanged", "modified"
    rationale: str = ""


# ---------------------------------------------------------------------------
# Equipment / Sequence
# ---------------------------------------------------------------------------
@dataclass
class InitiatingDevice:
    """Smoke control initiating device."""
    device_type: str = ""                 # "waterflow", "smoke_detector", "manual_pull"
    location: str = ""
    action: str = ""                      # What it triggers


@dataclass
class SequenceStep:
    """One step in the sequence of operations."""
    step_number: int = 0
    description: str = ""
    sub_steps: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Leakage Data (for Appendix A Table A-1)
# ---------------------------------------------------------------------------
@dataclass
class LeakageComponent:
    """Building component leakage data."""
    component: str = ""                   # e.g. "Door (3 ft wide)"
    leakage_area: str = ""                # e.g. "0.385 sq ft/door"
    leakage_area_m2: float = 0.0          # SI value
    flow_exponent: float = 0.65


# ---------------------------------------------------------------------------
# CONTAM Results (for Appendix D)
# ---------------------------------------------------------------------------
@dataclass
class CONTAMResult:
    """Pressure differential result from CONTAM simulation."""
    scenario: str = ""                    # e.g. "Winter Wind"
    fire_floor: int = 0
    fire_floor_label: str = ""
    exhaust_rate_cfm: float = 0.0
    # Pressure differentials
    dp_floor_above: float = 0.0          # in. H₂O
    dp_floor_below: float = 0.0          # in. H₂O
    stair_vestibule_dps: Dict[str, float] = field(default_factory=dict)
    # e.g. {"Stair 1": 0.120, "Stair 2": 0.136, ...}
    vestibule_floor_dps: Dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# ADO (Automatic Door Operator) Requirement
# ---------------------------------------------------------------------------
@dataclass
class ADORequirement:
    """Door requiring an Automatic Door Operator."""
    stair_label: str = ""
    floor_label: str = ""
    dp_inwg: float = 0.0
    force_lbf: float = 0.0
    reason: str = ""                      # e.g. "F > 15 lbf"


# ---------------------------------------------------------------------------
# Complete SCRA Configuration
# ---------------------------------------------------------------------------
@dataclass
class SCRAConfig:
    """Complete configuration for generating an SCRA report."""
    project: ProjectInfo = field(default_factory=ProjectInfo)
    building: BuildingDescription = field(default_factory=BuildingDescription)
    climate: ClimateData = field(default_factory=ClimateData)
    stairs: List[StairDefinition] = field(default_factory=list)
    smoke_zones: List[SmokeZone] = field(default_factory=list)
    passive_subzones: List[PassiveSubzone] = field(default_factory=list)
    leakage_table: List[LeakageComponent] = field(default_factory=list)
    initiating_devices: List[InitiatingDevice] = field(default_factory=list)
    sequence_steps: List[SequenceStep] = field(default_factory=list)

    # Floor heights from PRJ (level_num → height_m)
    floor_heights: Dict[int, float] = field(default_factory=dict)
    floor_labels: Dict[int, str] = field(default_factory=dict)

    # Exhaust rates per fire floor (CFM)
    exhaust_rates: Dict[int, float] = field(default_factory=dict)

    # Design criteria
    min_dp_inwg: float = 0.05             # in. w.g. (LABC 909.6.1)
    max_door_force_lbf: float = 30.0      # lbf (CBC 909.20.6.2)
    max_door_force_egress_lbf: float = 15.0  # lbf (LABC 1010.1.3)
    max_dp_exit_door_inwg: float = 0.17   # in. w.g.
    max_dp_stair_door_inwg: float = 0.34  # in. w.g.
    min_dp_vestibule_inwg: float = 0.05   # in. w.g. vestibule requirements
    min_dp_no_vestibule_inwg: float = 0.10  # in. w.g. (stairs w/o vestibule)

    # ADO requirements
    ado_requirements: List[ADORequirement] = field(default_factory=list)

    # Code jurisdiction
    code_jurisdiction: str = "LABC"       # "LABC", "IBC", "CBC"
    code_references: Dict[str, str] = field(default_factory=lambda: {
        "smoke_control": "LABC 909",
        "high_rise": "LABC 403",
        "smokeproof": "LABC 909.20",
        "min_dp": "LABC 909.6.1",
        "max_force": "CBC 909.20.6.2",
        "door_force_egress": "LABC 1010.1.3",
        "power": "LABC 909.11",
        "detection": "LABC 909.12",
        "fscp": "LABC 909.16",
        "response_time": "LABC 909.17",
        "leakage": "LABC 909.5",
    })

    # PRJ file path (for CONTAM analysis)
    prj_file_path: str = ""


# ---------------------------------------------------------------------------
# SCRA Output / Results
# ---------------------------------------------------------------------------
@dataclass
class SCRAResults:
    """Complete results of SCRA analysis."""
    config: SCRAConfig = field(default_factory=SCRAConfig)

    # Estimation results (from estimation engine, per stair)
    estimation_results: Optional[object] = None  # EstimationResult

    # CONTAM results (if available)
    contam_results: List[CONTAMResult] = field(default_factory=list)

    # Per-stair summary
    stair_supply_summary: Dict[str, Dict[str, float]] = field(default_factory=dict)
    # e.g. {"Stair1": {"closed_cfm": 6250, "open_cfm": 11145, "design_cfm": 11145}}

    # ADO requirements
    ado_list: List[ADORequirement] = field(default_factory=list)

    # Overall pass/fail
    all_criteria_met: bool = False
    warnings: List[str] = field(default_factory=list)
