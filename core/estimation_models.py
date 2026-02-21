"""Data models for the Stair Pressurization & Floor Depressurization Estimation Tool.

All input/output structures per the technical specification.
SI units are used internally; conversions to imperial for display only.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Leakage area defaults (m^2 per m^2 of wall area, or absolute for doors)
# Source: ASHRAE HSCE Table 6.4, NFPA 80, NFPA 92 Annex A
# ---------------------------------------------------------------------------
LEAKAGE_DEFAULTS = {
    "exterior_wall": {"tight": 0.5e-4, "average": 1.7e-4, "loose": 5.0e-4},
    "interior_wall": {"tight": 0.3e-4, "average": 1.1e-4, "loose": 3.5e-4},
    "floor_ceiling": {"tight": 0.2e-4, "average": 0.8e-4, "loose": 2.5e-4},
    "stair_door": {"tight": 0.01, "average": 0.02, "loose": 0.04},       # m^2 absolute per door
    "elevator_door": {"tight": 0.02, "average": 0.06, "loose": 0.11},    # m^2 absolute per door
}

# Wind pressure coefficients (simplified rectangular building)
WIND_CP = {
    "windward": 0.7,
    "leeward": -0.45,
    "side_a": -0.6,
    "side_b": -0.6,
}


# ---------------------------------------------------------------------------
# Input Models
# ---------------------------------------------------------------------------
@dataclass
class BuildingGeometry:
    """Section 2.1 — Building Geometry."""
    n_floors_above: int = 10           # N
    n_floors_below: int = 0            # N_b
    floor_height: float = 3.5          # h_f (m)
    building_perimeter: float = 120.0  # P_bldg (m)
    floor_area: float = 1000.0         # A_floor (m^2)
    wall_construction: str = "average" # tight / average / loose


@dataclass
class StairwellGeometry:
    """Section 2.2 — Stairwell Geometry (per stairwell)."""
    label: str = "Stair A"
    cross_section_perimeter: float = 8.0    # P_stair (m)
    cross_section_area: float = 10.0        # A_stair (m^2)
    door_width: float = 1.1                 # w_d (m)
    door_height: float = 2.1                # h_d (m)
    door_gap_mm: float = 3.0                # g_d (mm)
    doors_per_floor: int = 1                # n_d
    serves_bottom: int = 1                  # bottom floor served (1-indexed)
    serves_top: int = 10                    # top floor served
    n_exterior_walls: int = 1               # n_ext
    exterior_wall_length: float = 4.0       # L_ext (m) per floor


@dataclass
class ElevatorShaftConfig:
    """Section 2.3 — Elevator Shafts."""
    n_shafts: int = 2                 # n_elev
    shaft_area: float = 6.0           # A_elev (m^2)
    door_type: str = "center-opening" # single-slide, center-opening, freight
    wall_construction: str = "average"
    vent_area: float = 0.0            # A_elev_vent (m^2), 0 = unvented


@dataclass
class DesignConditions:
    """Section 2.4 — Design Conditions."""
    T_outdoor_winter: float = -18.0    # T_o,w (deg C)
    T_outdoor_summer: float = 35.0     # T_o,s (deg C)
    T_indoor: float = 22.0             # T_i (deg C)
    T_fire: float = 300.0              # T_f (deg C)
    wind_speed: float = 12.0           # V_w (m/s)
    wind_direction: float = 0.0        # theta_w (deg)
    P_atm: float = 101325.0            # Pa
    n_open_doors: int = 1              # n_open
    is_sprinklered: bool = True
    design_fire_hrr: float = 2000.0    # kW


@dataclass
class LeakageData:
    """Section 2.5 — Leakage Area Data."""
    exterior_wall: str = "average"      # tight / average / loose
    interior_wall: str = "average"
    floor_ceiling: str = "average"
    stair_door: str = "average"
    elevator_door: str = "average"
    # User overrides (None = use default from tightness)
    custom_stair_door_area: Optional[float] = None   # m^2 per door
    custom_elevator_door_area: Optional[float] = None # m^2 per door
    use_crack_method_for_stair_door: bool = False     # If True, use EQ-02


@dataclass
class DesignCriteria:
    """Section 2.6 — Design Criteria."""
    min_dp_closed: float = 12.5        # Pa
    max_dp_closed: float = 87.0        # Pa
    min_door_velocity: float = 1.0     # m/s (sprinklered default)
    max_door_force: float = 133.0      # N
    floor_exhaust_dp: float = 19.92     # Pa (0.08 in. w.g.)
    door_closer_force: float = 55.0    # N (typical)
    handle_to_latch: float = 0.075     # m


@dataclass
class EstimationConfig:
    """Complete input configuration for the estimation tool."""
    building: BuildingGeometry = field(default_factory=BuildingGeometry)
    stairwells: List[StairwellGeometry] = field(default_factory=lambda: [StairwellGeometry()])
    elevators: ElevatorShaftConfig = field(default_factory=ElevatorShaftConfig)
    conditions: DesignConditions = field(default_factory=DesignConditions)
    leakage: LeakageData = field(default_factory=LeakageData)
    criteria: DesignCriteria = field(default_factory=DesignCriteria)
    injection_points: Dict[str, List[int]] = field(default_factory=dict)
    stairwell_temp_assumption: str = "outdoor"  # "outdoor" or "indoor"
    fire_floor: int = 5                         # Floor number with fire (1-indexed)


# ---------------------------------------------------------------------------
# Output Models
# ---------------------------------------------------------------------------
@dataclass
class CalculationTrace:
    """Single calculation step for traceability (Appendix B format)."""
    equation_id: str            # e.g. "EQ-03"
    description: str            # e.g. "Leakage flow through Stair A door, Floor 5"
    formula: str                # e.g. "Q = C_d x A x sqrt(2 x dP / rho)"
    inputs: Dict[str, str]      # e.g. {"C_d": "0.65", "A": "0.020 m^2", ...}
    substitution: str           # e.g. "Q = 0.65 x 0.020 x sqrt(2 x 28.3 / 1.20)"
    result: str                 # e.g. "Q = 0.0893 m^3/s (189 CFM)"


@dataclass
class FloorResult:
    """Per-floor result for a single stairwell (Section 8.3)."""
    floor_label: str
    floor_number: int
    height: float               # m above datum
    dp_stack: float             # Pa (from EQ-07)
    dp_wind: float              # Pa (from EQ-09)
    dp_net: float               # Pa (from EQ-15)
    q_leak_closed: float        # m^3/s
    q_flow_open: float          # m^3/s (0 if not an open-door floor)
    f_total: float              # N (door-opening force)
    status: str                 # "PASS" / "FAIL"
    failure_reasons: List[str] = field(default_factory=list)


@dataclass
class StairResult:
    """Results for one stairwell (Section 8.4)."""
    label: str
    floor_results: List[FloorResult]
    q_supply_closed: float       # m^3/s, all doors closed
    q_supply_open: float         # m^3/s, design doors open
    q_supply_design: float       # m^3/s, governing (max)
    q_leak_walls: float          # m^3/s, wall leakage
    critical_floor_min_dp: str   # Floor with lowest net dP
    critical_floor_max_force: str # Floor with highest door force
    all_constraints_met: bool


@dataclass
class ExhaustResult:
    """Fire floor exhaust results — ambient temperature leakage method per ASHRAE."""
    fire_floor: int
    fire_floor_label: str
    q_leak_stairs: float         # m^3/s (from all stairwells)
    q_leak_elevators: float      # m^3/s
    q_leak_exterior: float       # m^3/s
    q_leak_vertical: float       # m^3/s (above + below)
    q_exhaust_total: float       # m^3/s (at ambient conditions)


@dataclass
class SensitivityCase:
    """One sensitivity run result (Section 7)."""
    parameter: str               # e.g. "Exterior wall leakage"
    value_description: str       # e.g. "Tight"
    stair_supply_total: float    # m^3/s
    exhaust_total: float         # m^3/s
    stair_supply_change_pct: float
    exhaust_change_pct: float
    critical_floor: str
    constraints_violated: bool
    violations: List[str] = field(default_factory=list)


@dataclass
class EstimationResult:
    """Complete output of the estimation tool."""
    config: EstimationConfig
    stair_results: List[StairResult]
    exhaust_result: ExhaustResult
    sensitivity_cases: List[SensitivityCase]
    calculation_traces: List[CalculationTrace]
    npp_height: float               # m, neutral pressure plane
    all_constraints_met: bool
    warnings: List[str] = field(default_factory=list)
