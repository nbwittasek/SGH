"""Stair Pressurization & Floor Depressurization Estimation Engine.

Implements all equations from the technical specification (EQ-01 through EQ-26)
and the simultaneous iterative solution procedure (Section 6).

All calculations use SI units internally.
"""

import copy
import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .estimation_models import (
    LEAKAGE_DEFAULTS,
    WIND_CP,
    BuildingGeometry,
    CalculationTrace,
    DesignConditions,
    DesignCriteria,
    ElevatorShaftConfig,
    EstimationConfig,
    EstimationResult,
    ExhaustResult,
    FloorResult,
    LeakageData,
    SensitivityCase,
    StairResult,
    StairwellGeometry,
)

logger = logging.getLogger(__name__)

# Constants
R_AIR = 287.058        # J/(kg·K) — specific gas constant for dry air
GRAVITY = 9.81         # m/s^2
STACK_COEFF = 3460.0   # Pa·K/m  (g / R_air rounded, per spec)
C_P_AIR = 1005.0       # J/(kg·K) — specific heat of air
T_STD_K = 293.15       # 20 deg C in K (standard conditions)

# Conversion helpers
CMS_TO_CFM = 2118.88   # 1 m^3/s = 2118.88 CFM
N_TO_LBF = 0.224809    # 1 N = 0.224809 lbf
PA_TO_INWG = 1.0 / 249.089  # 1 Pa = 0.004015 in. w.g.


def _c_to_k(t_c: float) -> float:
    """Celsius to Kelvin."""
    return t_c + 273.15


def cms_to_cfm(q_cms: float) -> float:
    """m^3/s to CFM."""
    return q_cms * CMS_TO_CFM


def cfm_to_cms(q_cfm: float) -> float:
    """CFM to m^3/s."""
    return q_cfm / CMS_TO_CFM


def n_to_lbf(f_n: float) -> float:
    """Newtons to pounds-force."""
    return f_n * N_TO_LBF


def pa_to_inwg(p_pa: float) -> float:
    """Pascals to inches water gauge."""
    return p_pa * PA_TO_INWG


# ---------------------------------------------------------------------------
# Individual Equations (EQ-01 through EQ-26)
# ---------------------------------------------------------------------------

def eq01_air_density(P_atm: float, T_K: float) -> float:
    """EQ-01: Air density from ideal gas law.

    rho = P_atm / (R_air * T)
    """
    return P_atm / (R_AIR * T_K)


def eq02_door_leakage_area(g_d_m: float, w_d: float, h_d: float,
                           w_threshold: Optional[float] = None) -> float:
    """EQ-02: Leakage area from door perimeter crack.

    A_Ld = g_d * (2*w_d + 2*h_d - w_threshold)
    g_d in metres.  If w_threshold is None, assume threshold sealed (= w_d).
    """
    if w_threshold is None:
        w_threshold = w_d
    return g_d_m * (2.0 * w_d + 2.0 * h_d - w_threshold)


def eq03_orifice_flow_volume(C_d: float, A: float, dP: float,
                             rho: float) -> float:
    """EQ-03: Volumetric orifice flow.

    Q = C_d * A * sqrt(2 * |dP| / rho)
    Returns positive Q; sign of dP indicates direction.
    """
    if abs(dP) < 1e-12 or rho <= 0:
        return 0.0
    return C_d * A * math.sqrt(2.0 * abs(dP) / rho)


def eq04_orifice_flow_mass(C_d: float, A: float, rho: float,
                           dP: float) -> float:
    """EQ-04: Mass flow through orifice.

    m_dot = C_d * A * sqrt(2 * rho * |dP|)
    """
    if abs(dP) < 1e-12 or rho <= 0:
        return 0.0
    return C_d * A * math.sqrt(2.0 * rho * abs(dP))


def eq05_parallel_areas(areas: List[float]) -> float:
    """EQ-05: Parallel leakage area combination.

    A_eff = A_1 + A_2 + ... + A_n
    """
    return sum(areas)


def eq06_series_areas(areas: List[float]) -> float:
    """EQ-06: Series leakage area combination.

    1/A_eff^2 = 1/A_1^2 + 1/A_2^2 + ... + 1/A_n^2
    """
    inv_sum = 0.0
    for a in areas:
        if a <= 0:
            return 0.0
        inv_sum += 1.0 / (a * a)
    if inv_sum <= 0:
        return 0.0
    return 1.0 / math.sqrt(inv_sum)


def eq07_stack_effect(T_o_K: float, T_s_K: float, h: float,
                      h_npp: float) -> float:
    """EQ-07: Stack-effect pressure differential.

    dP_s(h) = 3460 * (1/T_o - 1/T_s) * (h - h_NPP)

    Positive = stairwell at higher pressure than adjacent floor.
    """
    return STACK_COEFF * (1.0 / T_o_K - 1.0 / T_s_K) * (h - h_npp)


def eq09_wind_pressure(C_p: float, rho_o: float, V_w: float) -> float:
    """EQ-09: Wind-induced pressure on a building face.

    dP_w = 0.5 * C_p * rho_o * V_w^2
    """
    return 0.5 * C_p * rho_o * V_w * V_w


def eq10a_pressure_force(dP: float, w_d: float, h_d: float) -> float:
    """EQ-10a: Force from pressure differential on door.

    F_p = dP * w_d * h_d / 2
    """
    return abs(dP) * w_d * h_d / 2.0


def eq10b_total_door_force(F_closer: float, dP: float, w_d: float,
                           h_d: float, d: float) -> float:
    """EQ-10b: Total door-opening force.

    F_total = F_closer + F_p * (w_d / (w_d - d))
    where F_p = dP * w_d * h_d / 2

    When dP > 0 (stair at higher pressure), pressure opposes door opening.
    When dP < 0 (floor at higher pressure), pressure assists door opening.
    """
    F_p = eq10a_pressure_force(dP, w_d, h_d)  # always positive (uses abs)
    if w_d <= d:
        return float('inf')
    moment_factor = w_d / (w_d - d)
    if dP >= 0:
        return F_closer + F_p * moment_factor
    else:
        return max(0.0, F_closer - F_p * moment_factor)


def eq11_doorway_velocity(Q_door: float, w_d: float, h_d: float) -> float:
    """EQ-11: Average velocity through open doorway.

    V_door = Q_door / (w_d * h_d)
    """
    A_door = w_d * h_d
    if A_door <= 0:
        return 0.0
    return Q_door / A_door


def eq12_required_open_door_flow(V_min: float, w_d: float,
                                 h_d: float) -> float:
    """EQ-12: Required volumetric flow through one open door.

    Q_open = V_min * w_d * h_d
    """
    return V_min * w_d * h_d


def eq19_stair_leak_to_fire_floor(C_d: float, A_Ld: float, n_d: int,
                                  dP_mech: float, dP_exhaust: float,
                                  rho_s: float) -> float:
    """EQ-19: Leakage from one stairwell into fire floor.

    Q = C_d * A_Ld * n_d * sqrt(2 * (dP_mech + dP_exhaust) / rho_s)
    """
    total_dp = dP_mech + dP_exhaust
    if total_dp <= 0:
        return 0.0
    return C_d * A_Ld * n_d * math.sqrt(2.0 * total_dp / rho_s)


def eq20_elevator_leak_to_fire_floor(C_d: float, A_Le: float, n_elev: int,
                                     dP_elev: float, rho_i: float) -> float:
    """EQ-20: Elevator shaft leakage into fire floor.

    Q = C_d * A_Le * n_elev * sqrt(2 * |dP_elev| / rho_i)
    """
    if dP_elev <= 0:
        return 0.0
    return C_d * A_Le * n_elev * math.sqrt(2.0 * dP_elev / rho_i)


def eq21_exterior_leak_to_fire_floor(C_d: float, A_Lw_per_m2: float,
                                     P_bldg: float, h_f: float,
                                     dP_exhaust: float, dP_wind: float,
                                     rho_o: float) -> float:
    """EQ-21: Exterior wall leakage into fire floor.

    Q = C_d * (A_Lw * P_bldg * h_f) * sqrt(2 * (dP_exhaust + dP_wind) / rho_o)
    Calculated per face; this is for one face. Caller sums faces.
    """
    A_total = A_Lw_per_m2 * P_bldg * h_f
    net_dp = dP_exhaust + dP_wind
    if net_dp <= 0:
        return 0.0
    return C_d * A_total * math.sqrt(2.0 * net_dp / rho_o)


def eq22_vertical_leak(C_d: float, A_Lf_per_m2: float, A_floor: float,
                       dP_exhaust: float, rho_i: float) -> float:
    """EQ-22: Leakage from one adjacent floor (above or below).

    Q = C_d * (A_Lf * A_floor) * sqrt(2 * dP_exhaust / rho_i)
    """
    if dP_exhaust <= 0:
        return 0.0
    A_total = A_Lf_per_m2 * A_floor
    return C_d * A_total * math.sqrt(2.0 * dP_exhaust / rho_i)


def eq23_thermal_expansion(Q_fire: float, T_f_K: float,
                           T_i_K: float) -> float:
    """EQ-23: Thermal expansion volume from fire.

    Q_expansion = Q_fire * (T_f / T_i - 1)
    """
    if T_i_K <= 0:
        return 0.0
    return Q_fire * (T_f_K / T_i_K - 1.0)


def eq24_fire_entrainment(H_dot_kW: float, rho_i: float,
                          T_f_K: float, T_i_K: float) -> float:
    """EQ-24: Volumetric rate of air entrained into fire plume.

    Q_fire = H_dot / (rho_i * c_p * (T_f - T_i))
    H_dot in kW = 1000 W
    """
    dT = T_f_K - T_i_K
    if dT <= 0 or rho_i <= 0:
        return 0.0
    return (H_dot_kW * 1000.0) / (rho_i * C_P_AIR * dT)


def max_dp_from_force(F_max: float, F_closer: float, w_d: float,
                      h_d: float, d: float) -> float:
    """Rearrange EQ-10b to find the maximum allowable dP.

    dP_max = 2 * (F_max - F_closer) * (w_d - d) / (w_d * h_d * w_d)
           = 2 * (F_max - F_closer) * (w_d - d) / (w_d^2 * h_d)
    """
    if w_d <= d or w_d <= 0 or h_d <= 0:
        return 0.0
    F_available = F_max - F_closer
    if F_available <= 0:
        return 0.0
    return 2.0 * F_available * (w_d - d) / (w_d * w_d * h_d)


# ---------------------------------------------------------------------------
# Leakage area helpers
# ---------------------------------------------------------------------------

def get_leakage_area(component: str, tightness: str) -> float:
    """Look up default leakage area from LEAKAGE_DEFAULTS."""
    return LEAKAGE_DEFAULTS.get(component, {}).get(tightness, 0.0)


def get_stair_door_leakage(config: EstimationConfig,
                           stair: StairwellGeometry) -> float:
    """Get effective leakage area for one stair door."""
    if config.leakage.custom_stair_door_area is not None:
        return config.leakage.custom_stair_door_area
    if config.leakage.use_crack_method_for_stair_door:
        g_d_m = stair.door_gap_mm / 1000.0
        return eq02_door_leakage_area(g_d_m, stair.door_width, stair.door_height)
    return get_leakage_area("stair_door", config.leakage.stair_door)


def get_elevator_door_leakage(config: EstimationConfig) -> float:
    """Get effective leakage area for one elevator door."""
    if config.leakage.custom_elevator_door_area is not None:
        return config.leakage.custom_elevator_door_area
    return get_leakage_area("elevator_door", config.leakage.elevator_door)


# ---------------------------------------------------------------------------
# Wind pressure per face
# ---------------------------------------------------------------------------

def compute_wind_pressures(V_w: float, wind_dir_deg: float,
                           rho_o: float) -> Dict[str, float]:
    """Compute wind pressure on each building face.

    Returns dict with keys 'north','south','east','west' (or face indices).
    For simplicity, we model a rectangular building with 4 faces:
      - Face 0 (north, normal = 0 deg)
      - Face 1 (east, normal = 90 deg)
      - Face 2 (south, normal = 180 deg)
      - Face 3 (west, normal = 270 deg)
    The windward face is the one most directly facing the wind.
    """
    face_normals = [0, 90, 180, 270]
    face_names = ["north", "east", "south", "west"]
    pressures = {}

    for i, normal in enumerate(face_normals):
        angle = abs(wind_dir_deg - normal) % 360
        if angle > 180:
            angle = 360 - angle
        # Determine C_p based on angle
        if angle <= 45:
            C_p = WIND_CP["windward"]
        elif angle >= 135:
            C_p = WIND_CP["leeward"]
        else:
            C_p = WIND_CP["side_a"]
        pressures[face_names[i]] = eq09_wind_pressure(C_p, rho_o, V_w)

    return pressures


# ---------------------------------------------------------------------------
# Main Estimation Engine
# ---------------------------------------------------------------------------

class EstimationEngine:
    """Implements the full calculation procedure per Sections 4-7."""

    def __init__(self, config: EstimationConfig):
        self.config = config
        self.traces: List[CalculationTrace] = []
        self.warnings: List[str] = []

        # Derived quantities (populated in _compute_densities)
        self.rho_o: float = 0.0   # outdoor air density
        self.rho_i: float = 0.0   # indoor air density
        self.rho_f: float = 0.0   # fire floor air density
        self.rho_s: float = 0.0   # stairwell air density
        self.T_o_K: float = 0.0
        self.T_i_K: float = 0.0
        self.T_f_K: float = 0.0
        self.T_s_K: float = 0.0

        # Building height info
        self.total_floors = config.building.n_floors_above + config.building.n_floors_below
        self.total_height = self.total_floors * config.building.floor_height
        self.grade_height = config.building.n_floors_below * config.building.floor_height

        # NPP
        self.h_npp: float = self.total_height / 2.0

    def _add_trace(self, eq_id: str, description: str, formula: str,
                   inputs: Dict[str, str], substitution: str,
                   result: str) -> None:
        self.traces.append(CalculationTrace(
            equation_id=eq_id,
            description=description,
            formula=formula,
            inputs=inputs,
            substitution=substitution,
            result=result,
        ))

    def _floor_height(self, floor_num: int) -> float:
        """Height of floor floor_num above grade datum.

        floor_num is 1-indexed: floor 1 = ground level.
        Below-grade floors are numbered -N_b ... 0 (but we use 1-indexed
        where floor 1 is the lowest occupied).
        Convention: floor 1 is at height 0 (grade), floor 2 at h_f, etc.
        Below-grade: floor 0 at -h_f, floor -1 at -2*h_f, etc.
        """
        h_f = self.config.building.floor_height
        return (floor_num - 1) * h_f

    def _floor_label(self, floor_num: int) -> str:
        """Human-readable floor label."""
        n_below = self.config.building.n_floors_below
        actual = floor_num - n_below
        if actual < 0:
            return f"B{-actual}"
        elif actual == 0:
            return "G"
        else:
            return str(actual)

    def _all_floor_numbers(self) -> List[int]:
        """List of all floor numbers, bottom to top (1-indexed)."""
        return list(range(1, self.total_floors + 1))

    def _compute_densities(self, season: str = "winter") -> None:
        """Compute air densities for the given season."""
        cond = self.config.conditions
        P = cond.P_atm

        if season == "winter":
            self.T_o_K = _c_to_k(cond.T_outdoor_winter)
        else:
            self.T_o_K = _c_to_k(cond.T_outdoor_summer)

        self.T_i_K = _c_to_k(cond.T_indoor)
        self.T_f_K = _c_to_k(cond.T_fire)

        # Stairwell temperature assumption
        if self.config.stairwell_temp_assumption == "outdoor":
            self.T_s_K = self.T_o_K
        else:
            self.T_s_K = self.T_i_K

        self.rho_o = eq01_air_density(P, self.T_o_K)
        self.rho_i = eq01_air_density(P, self.T_i_K)
        self.rho_f = eq01_air_density(P, self.T_f_K)
        self.rho_s = eq01_air_density(P, self.T_s_K)

        self._add_trace(
            "EQ-01", "Outdoor air density", "rho = P_atm / (R_air * T)",
            {"P_atm": f"{P:.0f} Pa", "T": f"{self.T_o_K:.2f} K"},
            f"rho = {P:.0f} / (287.058 * {self.T_o_K:.2f})",
            f"rho_o = {self.rho_o:.4f} kg/m^3",
        )
        self._add_trace(
            "EQ-01", "Indoor air density", "rho = P_atm / (R_air * T)",
            {"P_atm": f"{P:.0f} Pa", "T": f"{self.T_i_K:.2f} K"},
            f"rho = {P:.0f} / (287.058 * {self.T_i_K:.2f})",
            f"rho_i = {self.rho_i:.4f} kg/m^3",
        )
        self._add_trace(
            "EQ-01", "Fire floor air density", "rho = P_atm / (R_air * T)",
            {"P_atm": f"{P:.0f} Pa", "T": f"{self.T_f_K:.2f} K"},
            f"rho = {P:.0f} / (287.058 * {self.T_f_K:.2f})",
            f"rho_f = {self.rho_f:.4f} kg/m^3",
        )

    def _compute_npp(self, dP_mech: float) -> float:
        """Solve for neutral pressure plane height via bisection (EQ-08).

        Mass conservation: sum of mass flows in = sum of mass flows out
        across all floors. We iterate h_NPP until the net mass flow ~ 0.
        """
        floors = self._all_floor_numbers()
        h_f = self.config.building.floor_height
        C_d = 0.65

        # Get leakage areas
        A_Lw = get_leakage_area("exterior_wall", self.config.leakage.exterior_wall)
        wall_area_per_floor = self.config.building.building_perimeter * h_f

        h_low = 0.0
        h_high = self.total_height
        tolerance = 0.01  # m

        for _iter in range(200):
            h_mid = (h_low + h_high) / 2.0
            net_mass = 0.0

            for f in floors:
                h = self._floor_height(f)
                dP_stack = eq07_stack_effect(self.T_o_K, self.T_i_K, h, h_mid)
                # Positive dP_stack means building interior > exterior at this height
                # Mass flow: positive = inward (into building)
                dP_net = -dP_stack  # exterior to interior positive means inflow
                A = A_Lw * wall_area_per_floor
                if dP_net > 0:
                    net_mass += eq04_orifice_flow_mass(C_d, A, self.rho_o, dP_net)
                else:
                    net_mass -= eq04_orifice_flow_mass(C_d, A, self.rho_i, -dP_net)

            if abs(net_mass) < 0.001:
                break
            if net_mass > 0:
                # Too much inflow: NPP too high (all floors below NPP), lower it
                h_high = h_mid
            else:
                # Too much outflow: NPP too low (all floors above NPP), raise it
                h_low = h_mid

        return (h_low + h_high) / 2.0

    def _compute_stair_pressurization(
        self, stair: StairwellGeometry, dP_mech: float,
        dP_exhaust: float, wind_pressures: Dict[str, float],
        open_door_floors: List[int],
    ) -> StairResult:
        """Compute supply air for one stairwell (Section 4)."""
        cond = self.config.conditions
        criteria = self.config.criteria
        C_d_closed = 0.65
        C_d_open = 0.60
        h_f = self.config.building.floor_height

        A_Ld = get_stair_door_leakage(self.config, stair)

        # Trace EQ-02 (door leakage area)
        g_d_m = stair.door_gap_mm / 1000.0
        self._add_trace(
            "EQ-02", f"{stair.label} — Door leakage area",
            "A_Ld = g_d × (2×w_d + 2×h_d − w_threshold)",
            {"g_d": f"{g_d_m:.4f} m", "w_d": f"{stair.door_width} m",
             "h_d": f"{stair.door_height} m"},
            f"A_Ld = {g_d_m:.4f} × (2×{stair.door_width} + 2×{stair.door_height} − {stair.door_width})",
            f"A_Ld = {A_Ld:.5f} m² (used value: {A_Ld:.5f} m²)",
        )

        # Leakage area for stair exterior walls
        A_Lw = get_leakage_area("exterior_wall", self.config.leakage.exterior_wall)

        # Minimum door velocity
        V_min = criteria.min_door_velocity
        if not cond.is_sprinklered:
            V_min = 1.7

        Q_open_per_door = eq12_required_open_door_flow(
            V_min, stair.door_width, stair.door_height
        )

        # Trace EQ-12 (required open door flow)
        self._add_trace(
            "EQ-12", f"{stair.label} — Required open-door flow",
            "Q_open = V_min × w_d × h_d",
            {"V_min": f"{V_min} m/s", "w_d": f"{stair.door_width} m",
             "h_d": f"{stair.door_height} m"},
            f"Q_open = {V_min} × {stair.door_width} × {stair.door_height}",
            f"Q_open = {Q_open_per_door:.4f} m³/s ({cms_to_cfm(Q_open_per_door):.0f} CFM)",
        )

        floor_results: List[FloorResult] = []
        total_q_closed = 0.0
        total_q_open_closed_part = 0.0
        total_q_walls = 0.0

        min_dp_val = float('inf')
        min_dp_floor = ""
        max_force_val = 0.0
        max_force_floor = ""

        all_ok = True

        floors = self._all_floor_numbers()
        fire_floor = self.config.fire_floor
        _traced_first = False  # Trace detailed calcs for first served floor

        for f in floors:
            # Check if this stair serves this floor
            if f < stair.serves_bottom or f > stair.serves_top:
                continue

            h = self._floor_height(f)
            label = self._floor_label(f)
            _do_trace = not _traced_first or f == fire_floor

            # Stack effect at this floor (EQ-07)
            dP_stack = eq07_stack_effect(self.T_i_K, self.T_s_K, h, self.h_npp)

            if _do_trace:
                self._add_trace(
                    "EQ-07", f"{stair.label} Floor {label} — Stack effect",
                    "ΔP_s = 3460 × (1/T_i − 1/T_s) × (h − h_NPP)",
                    {"T_i": f"{self.T_i_K:.2f} K", "T_s": f"{self.T_s_K:.2f} K",
                     "h": f"{h:.2f} m", "h_NPP": f"{self.h_npp:.2f} m"},
                    f"ΔP_s = 3460 × (1/{self.T_i_K:.2f} − 1/{self.T_s_K:.2f}) × ({h:.2f} − {self.h_npp:.2f})",
                    f"ΔP_stack = {dP_stack:.2f} Pa ({pa_to_inwg(dP_stack):.4f} in. w.g.)",
                )

            # Wind effect on stair-to-floor differential
            dP_wind = 0.0
            if stair.n_exterior_walls > 0 and wind_pressures:
                stair_wall_area = stair.exterior_wall_length * h_f * stair.n_exterior_walls
                stair_total_area = stair.cross_section_perimeter * h_f
                wall_fraction = stair_wall_area / max(stair_total_area, 1.0)
                min_wind = min(wind_pressures.values())
                dP_wind = min_wind * wall_fraction * 0.2

                if _do_trace:
                    self._add_trace(
                        "EQ-09", f"{stair.label} Floor {label} — Wind pressure contribution",
                        "ΔP_w = P_wind × A_ext_frac × 0.2",
                        {"P_wind_min": f"{min_wind:.2f} Pa", "wall_frac": f"{wall_fraction:.3f}"},
                        f"ΔP_w = {min_wind:.2f} × {wall_fraction:.3f} × 0.2",
                        f"ΔP_wind = {dP_wind:.2f} Pa ({pa_to_inwg(dP_wind):.4f} in. w.g.)",
                    )

            # Depressurization offset (fire floor only)
            dP_depress = dP_exhaust if f == fire_floor else 0.0

            # EQ-15: Net pressure differential
            dP_net = dP_mech + dP_stack + dP_wind - dP_depress

            if _do_trace:
                self._add_trace(
                    "EQ-15", f"{stair.label} Floor {label} — Net pressure differential",
                    "ΔP_net = ΔP_mech + ΔP_stack + ΔP_wind − ΔP_exhaust",
                    {"ΔP_mech": f"{dP_mech:.2f} Pa", "ΔP_stack": f"{dP_stack:.2f} Pa",
                     "ΔP_wind": f"{dP_wind:.2f} Pa", "ΔP_exhaust": f"{dP_depress:.2f} Pa"},
                    f"ΔP_net = {dP_mech:.2f} + {dP_stack:.2f} + {dP_wind:.2f} − {dP_depress:.2f}",
                    f"ΔP_net = {dP_net:.2f} Pa ({pa_to_inwg(dP_net):.4f} in. w.g.)",
                )

            # Leakage through closed door(s) at this floor (EQ-03)
            is_open = f in open_door_floors
            q_leak_closed = 0.0
            q_flow_open = 0.0

            if is_open:
                q_flow_open = Q_open_per_door * stair.doors_per_floor
            else:
                if dP_net > 0:
                    q_leak_closed = eq03_orifice_flow_volume(
                        C_d_closed, A_Ld * stair.doors_per_floor,
                        dP_net, self.rho_s
                    )

                    if _do_trace:
                        A_total = A_Ld * stair.doors_per_floor
                        self._add_trace(
                            "EQ-03", f"{stair.label} Floor {label} — Closed-door leakage flow",
                            "Q = C_d × A × √(2 × ΔP / ρ)",
                            {"C_d": "0.65", "A": f"{A_total:.5f} m²",
                             "ΔP": f"{dP_net:.2f} Pa", "ρ_s": f"{self.rho_s:.4f} kg/m³"},
                            f"Q = 0.65 × {A_total:.5f} × √(2 × {dP_net:.2f} / {self.rho_s:.4f})",
                            f"Q_leak = {q_leak_closed:.5f} m³/s ({cms_to_cfm(q_leak_closed):.1f} CFM)",
                        )
                else:
                    q_leak_closed = 0.0

            # Wall leakage for this floor (stair exterior walls)
            q_wall = 0.0
            if stair.n_exterior_walls > 0 and dP_net > 0:
                wall_area = stair.exterior_wall_length * h_f * stair.n_exterior_walls
                q_wall = eq03_orifice_flow_volume(
                    C_d_closed, A_Lw * wall_area, dP_net, self.rho_s
                )
            total_q_walls += q_wall

            # Door-opening force (EQ-10b)
            f_total = eq10b_total_door_force(
                criteria.door_closer_force, dP_net,
                stair.door_width, stair.door_height,
                criteria.handle_to_latch
            )

            if _do_trace:
                F_p = abs(dP_net) * stair.door_width * stair.door_height / 2.0
                self._add_trace(
                    "EQ-10b", f"{stair.label} Floor {label} — Door-opening force",
                    "F_total = F_closer + (ΔP × w_d × h_d / 2) × w_d / (w_d − d)",
                    {"F_closer": f"{criteria.door_closer_force:.1f} N ({n_to_lbf(criteria.door_closer_force):.1f} lbf)",
                     "ΔP": f"{dP_net:.2f} Pa", "w_d": f"{stair.door_width} m",
                     "h_d": f"{stair.door_height} m", "d": f"{criteria.handle_to_latch} m"},
                    f"F_p = {F_p:.2f} N; F_total = {criteria.door_closer_force:.1f} + {F_p:.2f} × {stair.door_width}/({stair.door_width} − {criteria.handle_to_latch})",
                    f"F_total = {f_total:.1f} N ({n_to_lbf(f_total):.1f} lbf)",
                )
                _traced_first = True

            # Check constraints
            status = "PASS"
            failures = []
            if not is_open and dP_net < criteria.min_dp_closed:
                status = "FAIL"
                failures.append(f"dP={dP_net:.1f} Pa < min {criteria.min_dp_closed} Pa")
                all_ok = False
            if dP_net > criteria.max_dp_closed:
                status = "FAIL"
                failures.append(f"dP={dP_net:.1f} Pa > max {criteria.max_dp_closed} Pa")
                all_ok = False
            if f_total > criteria.max_door_force:
                status = "FAIL"
                failures.append(f"F={f_total:.1f} N > max {criteria.max_door_force} N")
                all_ok = False

            floor_results.append(FloorResult(
                floor_label=label,
                floor_number=f,
                height=h,
                dp_stack=dP_stack,
                dp_wind=dP_wind,
                dp_net=dP_net,
                q_leak_closed=q_leak_closed,
                q_flow_open=q_flow_open,
                f_total=f_total,
                status=status,
                failure_reasons=failures,
            ))

            # Track critical floors
            if not is_open and dP_net < min_dp_val:
                min_dp_val = dP_net
                min_dp_floor = label
            if f_total > max_force_val:
                max_force_val = f_total
                max_force_floor = label

            total_q_closed += q_leak_closed
            if not is_open:
                total_q_open_closed_part += q_leak_closed

        # EQ-13: Total supply, all doors closed
        q_supply_closed = total_q_closed + total_q_walls

        self._add_trace(
            "EQ-13", f"{stair.label} — Total supply (all doors closed)",
            "Q_supply_closed = Σ Q_leak_doors + Σ Q_leak_walls",
            {"Σ Q_leak_doors": f"{total_q_closed:.5f} m³/s",
             "Σ Q_leak_walls": f"{total_q_walls:.5f} m³/s"},
            f"Q_supply_closed = {total_q_closed:.5f} + {total_q_walls:.5f}",
            f"Q_supply_closed = {q_supply_closed:.5f} m³/s ({cms_to_cfm(q_supply_closed):.0f} CFM)",
        )

        # EQ-14: Total supply, design doors open
        n_open = len(open_door_floors)
        q_open_doors = n_open * Q_open_per_door * stair.doors_per_floor if n_open > 0 else 0.0
        q_supply_open = total_q_open_closed_part + q_open_doors + total_q_walls

        self._add_trace(
            "EQ-14", f"{stair.label} — Total supply (doors open)",
            "Q_supply_open = Σ Q_leak_closed_floors + Q_open_doors + Σ Q_leak_walls",
            {"Σ Q_closed": f"{total_q_open_closed_part:.5f} m³/s",
             "Q_open_doors": f"{q_open_doors:.5f} m³/s ({n_open} doors)",
             "Σ Q_walls": f"{total_q_walls:.5f} m³/s"},
            f"Q_supply_open = {total_q_open_closed_part:.5f} + {q_open_doors:.5f} + {total_q_walls:.5f}",
            f"Q_supply_open = {q_supply_open:.5f} m³/s ({cms_to_cfm(q_supply_open):.0f} CFM)",
        )

        q_supply_design = max(q_supply_closed, q_supply_open)

        governing = "all closed" if q_supply_closed >= q_supply_open else "doors open"
        self._add_trace(
            "DESIGN", f"{stair.label} — Governing supply air rate",
            "Q_design = max(Q_closed, Q_open)",
            {"Q_closed": f"{cms_to_cfm(q_supply_closed):.0f} CFM",
             "Q_open": f"{cms_to_cfm(q_supply_open):.0f} CFM"},
            f"Governing case: {governing}",
            f"Q_design = {q_supply_design:.5f} m³/s ({cms_to_cfm(q_supply_design):.0f} CFM)",
        )

        return StairResult(
            label=stair.label,
            floor_results=floor_results,
            q_supply_closed=q_supply_closed,
            q_supply_open=q_supply_open,
            q_supply_design=q_supply_design,
            q_leak_walls=total_q_walls,
            critical_floor_min_dp=min_dp_floor,
            critical_floor_max_force=max_force_floor,
            all_constraints_met=all_ok,
        )

    def _compute_exhaust(
        self, stair_results: List[StairResult], dP_mech: float,
        dP_exhaust: float, wind_pressures: Dict[str, float],
    ) -> ExhaustResult:
        """Compute fire floor exhaust requirement (Section 5)."""
        cond = self.config.conditions
        bldg = self.config.building
        elev = self.config.elevators
        h_f = bldg.floor_height
        C_d = 0.65
        fire_floor = self.config.fire_floor

        # -- EQ-19: Leakage from stairwells --
        q_stairs_total = 0.0
        for i, stair in enumerate(self.config.stairwells):
            A_Ld = get_stair_door_leakage(self.config, stair)
            q_s = eq19_stair_leak_to_fire_floor(
                C_d, A_Ld, stair.doors_per_floor,
                dP_mech, dP_exhaust, self.rho_s
            )
            self._add_trace(
                "EQ-19", f"Exhaust — Stair leakage from {stair.label} into fire floor",
                "Q = C_d × A_Ld × n_d × √(2 × (ΔP_mech + ΔP_exhaust) / ρ_s)",
                {"C_d": "0.65", "A_Ld": f"{A_Ld:.5f} m²",
                 "n_d": str(stair.doors_per_floor),
                 "ΔP_mech": f"{dP_mech:.2f} Pa", "ΔP_exhaust": f"{dP_exhaust:.2f} Pa",
                 "ρ_s": f"{self.rho_s:.4f} kg/m³"},
                f"Q = 0.65 × {A_Ld:.5f} × {stair.doors_per_floor} × √(2 × ({dP_mech:.2f} + {dP_exhaust:.2f}) / {self.rho_s:.4f})",
                f"Q_stair = {q_s:.5f} m³/s ({cms_to_cfm(q_s):.0f} CFM)",
            )
            q_stairs_total += q_s

        # -- EQ-20: Elevator leakage --
        A_Le = get_elevator_door_leakage(self.config)
        h_fire = self._floor_height(fire_floor)
        dP_elev_stack = eq07_stack_effect(self.T_o_K, self.T_i_K, h_fire, self.h_npp)
        dP_elev = abs(dP_elev_stack) + dP_exhaust
        q_elev = eq20_elevator_leak_to_fire_floor(
            C_d, A_Le, elev.n_shafts, dP_elev, self.rho_i
        )

        self._add_trace(
            "EQ-20", "Exhaust — Elevator shaft leakage into fire floor",
            "Q = C_d × A_Le × n_elev × √(2 × ΔP_elev / ρ_i)",
            {"C_d": "0.65", "A_Le": f"{A_Le:.5f} m²",
             "n_elev": str(elev.n_shafts),
             "ΔP_elev": f"{dP_elev:.2f} Pa (stack={dP_elev_stack:.2f} + exhaust={dP_exhaust:.2f})",
             "ρ_i": f"{self.rho_i:.4f} kg/m³"},
            f"Q = 0.65 × {A_Le:.5f} × {elev.n_shafts} × √(2 × {dP_elev:.2f} / {self.rho_i:.4f})",
            f"Q_elev = {q_elev:.5f} m³/s ({cms_to_cfm(q_elev):.0f} CFM)",
        )

        # -- EQ-21: Exterior wall leakage --
        A_Lw = get_leakage_area("exterior_wall", self.config.leakage.exterior_wall)
        q_ext_total = 0.0
        n_faces = 4
        perimeter_per_face = bldg.building_perimeter / n_faces
        for face_name, dP_w in wind_pressures.items():
            effective_dP_w = max(dP_w, 0.0)
            q_face = eq21_exterior_leak_to_fire_floor(
                C_d, A_Lw, perimeter_per_face, h_f,
                dP_exhaust, effective_dP_w, self.rho_o
            )
            q_ext_total += q_face

        A_wall_total = A_Lw * bldg.building_perimeter * h_f
        self._add_trace(
            "EQ-21", "Exhaust — Exterior wall leakage into fire floor (all faces)",
            "Q = Σ_faces[ C_d × (A_Lw × P_face × h_f) × √(2 × (ΔP_exh + ΔP_wind) / ρ_o) ]",
            {"A_Lw": f"{A_Lw:.5e} m²/m²", "P_bldg": f"{bldg.building_perimeter} m",
             "h_f": f"{h_f} m", "ΔP_exhaust": f"{dP_exhaust:.2f} Pa",
             "ρ_o": f"{self.rho_o:.4f} kg/m³"},
            f"Total wall leakage area = {A_wall_total:.5f} m², summed over 4 faces",
            f"Q_ext = {q_ext_total:.5f} m³/s ({cms_to_cfm(q_ext_total):.0f} CFM)",
        )

        # -- EQ-22: Vertical leakage (above + below) --
        A_Lf = get_leakage_area("floor_ceiling", self.config.leakage.floor_ceiling)
        q_above = eq22_vertical_leak(C_d, A_Lf, bldg.floor_area, dP_exhaust, self.rho_i)
        q_below = eq22_vertical_leak(C_d, A_Lf, bldg.floor_area, dP_exhaust, self.rho_i)
        q_vertical = q_above + q_below

        A_floor_total = A_Lf * bldg.floor_area
        self._add_trace(
            "EQ-22", "Exhaust — Vertical leakage (floor above + below fire floor)",
            "Q = 2 × C_d × (A_Lf × A_floor) × √(2 × ΔP_exhaust / ρ_i)",
            {"A_Lf": f"{A_Lf:.5e} m²/m²", "A_floor": f"{bldg.floor_area} m²",
             "ΔP_exhaust": f"{dP_exhaust:.2f} Pa", "ρ_i": f"{self.rho_i:.4f} kg/m³"},
            f"Q_each = 0.65 × {A_floor_total:.5f} × √(2 × {dP_exhaust:.2f} / {self.rho_i:.4f}); Q_vert = 2 × Q_each",
            f"Q_vertical = {q_vertical:.5f} m³/s ({cms_to_cfm(q_vertical):.0f} CFM)",
        )

        # -- EQ-24: Fire entrainment --
        Q_fire = eq24_fire_entrainment(
            cond.design_fire_hrr, self.rho_i, self.T_f_K, self.T_i_K
        )

        self._add_trace(
            "EQ-24", "Exhaust — Fire plume entrainment",
            "Q_fire = H_dot / (ρ_i × c_p × (T_f − T_i))",
            {"H_dot": f"{cond.design_fire_hrr:.0f} kW",
             "ρ_i": f"{self.rho_i:.4f} kg/m³",
             "T_f": f"{self.T_f_K:.2f} K", "T_i": f"{self.T_i_K:.2f} K"},
            f"Q_fire = ({cond.design_fire_hrr:.0f} × 1000) / ({self.rho_i:.4f} × 1005 × ({self.T_f_K:.2f} − {self.T_i_K:.2f}))",
            f"Q_fire = {Q_fire:.5f} m³/s ({cms_to_cfm(Q_fire):.0f} CFM)",
        )

        # -- EQ-23: Thermal expansion --
        q_expansion = eq23_thermal_expansion(Q_fire, self.T_f_K, self.T_i_K)

        self._add_trace(
            "EQ-23", "Exhaust — Thermal expansion volume",
            "Q_expansion = Q_fire × (T_f / T_i − 1)",
            {"Q_fire": f"{Q_fire:.5f} m³/s",
             "T_f": f"{self.T_f_K:.2f} K", "T_i": f"{self.T_i_K:.2f} K"},
            f"Q_expansion = {Q_fire:.5f} × ({self.T_f_K:.2f} / {self.T_i_K:.2f} − 1)",
            f"Q_expansion = {q_expansion:.5f} m³/s ({cms_to_cfm(q_expansion):.0f} CFM)",
        )

        # -- EQ-25: Total exhaust --
        q_exhaust = q_stairs_total + q_elev + q_ext_total + q_vertical + q_expansion

        self._add_trace(
            "EQ-25", "Exhaust — Total fire floor exhaust (at fire temperature)",
            "Q_exhaust = Q_stairs + Q_elev + Q_ext + Q_vert + Q_expansion",
            {"Q_stairs": f"{q_stairs_total:.5f} m³/s",
             "Q_elev": f"{q_elev:.5f} m³/s",
             "Q_ext": f"{q_ext_total:.5f} m³/s",
             "Q_vert": f"{q_vertical:.5f} m³/s",
             "Q_expansion": f"{q_expansion:.5f} m³/s"},
            f"Q_exhaust = {q_stairs_total:.5f} + {q_elev:.5f} + {q_ext_total:.5f} + {q_vertical:.5f} + {q_expansion:.5f}",
            f"Q_exhaust = {q_exhaust:.5f} m³/s ({cms_to_cfm(q_exhaust):.0f} CFM)",
        )

        # -- EQ-26: Standard conditions --
        q_exhaust_std = q_exhaust * (self.T_f_K / T_STD_K)

        self._add_trace(
            "EQ-26", "Exhaust — Standard conditions (20°C reference)",
            "Q_std = Q_exhaust × (T_f / T_std)",
            {"Q_exhaust": f"{q_exhaust:.5f} m³/s",
             "T_f": f"{self.T_f_K:.2f} K", "T_std": f"{T_STD_K:.2f} K"},
            f"Q_std = {q_exhaust:.5f} × ({self.T_f_K:.2f} / {T_STD_K:.2f})",
            f"Q_std = {q_exhaust_std:.5f} m³/s ({cms_to_cfm(q_exhaust_std):.0f} CFM)",
        )

        fire_label = self._floor_label(fire_floor)

        return ExhaustResult(
            fire_floor=fire_floor,
            fire_floor_label=fire_label,
            q_leak_stairs=q_stairs_total,
            q_leak_elevators=q_elev,
            q_leak_exterior=q_ext_total,
            q_leak_vertical=q_vertical,
            q_expansion=q_expansion,
            q_exhaust_total=q_exhaust,
            q_exhaust_std=q_exhaust_std,
        )

    def solve(self, season: str = "winter") -> EstimationResult:
        """Run the full simultaneous solution (Section 6).

        Returns an EstimationResult with all stair and exhaust results.
        """
        self.traces = []
        self.warnings = []

        # Step 1: Compute densities
        self._compute_densities(season)

        # Wind pressures (EQ-09)
        wind_pressures = compute_wind_pressures(
            self.config.conditions.wind_speed,
            self.config.conditions.wind_direction,
            self.rho_o,
        )

        # Trace wind pressures
        if self.config.conditions.wind_speed > 0:
            wp_str = ", ".join(f"{k}={v:.2f} Pa" for k, v in wind_pressures.items())
            self._add_trace(
                "EQ-09", "Wind pressures on building faces",
                "ΔP_w = 0.5 × C_p × ρ_o × V_w²",
                {"V_w": f"{self.config.conditions.wind_speed} m/s",
                 "ρ_o": f"{self.rho_o:.4f} kg/m³",
                 "wind_dir": f"{self.config.conditions.wind_direction}°"},
                f"Per face: {wp_str}",
                f"Windward max = {max(wind_pressures.values()):.2f} Pa ({pa_to_inwg(max(wind_pressures.values())):.4f} in. w.g.)",
            )

        # Design targets
        dP_mech = max(
            self.config.criteria.min_dp_closed,
            self.config.criteria.floor_exhaust_dp
        )
        dP_exhaust = self.config.criteria.floor_exhaust_dp

        self._add_trace(
            "SETUP", "Design pressure targets",
            "ΔP_mech = max(min_dp_closed, floor_exhaust_dp)",
            {"min_dp_closed": f"{self.config.criteria.min_dp_closed} Pa ({pa_to_inwg(self.config.criteria.min_dp_closed):.4f} in. w.g.)",
             "floor_exhaust_dp": f"{dP_exhaust} Pa ({pa_to_inwg(dP_exhaust):.4f} in. w.g.)"},
            f"ΔP_mech = max({self.config.criteria.min_dp_closed}, {dP_exhaust})",
            f"ΔP_mech = {dP_mech:.2f} Pa ({pa_to_inwg(dP_mech):.4f} in. w.g.)",
        )

        # Check max allowable dP from door force
        for stair in self.config.stairwells:
            dP_max_force = max_dp_from_force(
                self.config.criteria.max_door_force,
                self.config.criteria.door_closer_force,
                stair.door_width, stair.door_height,
                self.config.criteria.handle_to_latch,
            )
            if dP_mech > dP_max_force:
                self.warnings.append(
                    f"{stair.label}: Design dP ({dP_mech:.1f} Pa) exceeds max "
                    f"allowable from door force ({dP_max_force:.1f} Pa). "
                    f"Multiple injection points or lower dP may be needed."
                )

        # Step 2: Compute NPP
        self.h_npp = self._compute_npp(dP_mech)

        # Open door floors for the design case
        fire_floor = self.config.fire_floor
        n_open = self.config.conditions.n_open_doors
        open_door_floors = []
        if n_open >= 1:
            open_door_floors.append(fire_floor)
        if n_open >= 2 and fire_floor + 1 <= self.total_floors:
            open_door_floors.append(fire_floor + 1)
        if n_open >= 3 and fire_floor - 1 >= 1:
            open_door_floors.append(fire_floor - 1)

        # Iterative solution (Section 6.1)
        MAX_ITER = 50
        FLOW_TOL = 0.005  # 0.5% convergence

        prev_total_supply = 0.0
        prev_total_exhaust = 0.0

        stair_results: List[StairResult] = []
        exhaust_result: Optional[ExhaustResult] = None

        # Save setup traces (EQ-01, EQ-09, SETUP) — emitted once before iteration
        setup_traces = list(self.traces)

        for iteration in range(MAX_ITER):
            # Reset per-iteration traces; keep setup traces for final output
            self.traces = list(setup_traces)

            # Step 3: Compute stairwell supply
            stair_results = []
            for stair in self.config.stairwells:
                sr = self._compute_stair_pressurization(
                    stair, dP_mech, dP_exhaust, wind_pressures,
                    open_door_floors,
                )
                stair_results.append(sr)

            # Step 4: Compute exhaust
            exhaust_result = self._compute_exhaust(
                stair_results, dP_mech, dP_exhaust, wind_pressures,
            )

            # Check convergence
            total_supply = sum(sr.q_supply_design for sr in stair_results)
            total_exhaust = exhaust_result.q_exhaust_total

            if iteration > 0:
                supply_change = (abs(total_supply - prev_total_supply) /
                                 max(prev_total_supply, 1e-12))
                exhaust_change = (abs(total_exhaust - prev_total_exhaust) /
                                  max(prev_total_exhaust, 1e-12))
                if supply_change < FLOW_TOL and exhaust_change < FLOW_TOL:
                    break

            prev_total_supply = total_supply
            prev_total_exhaust = total_exhaust

            # Step 5: Update NPP with new flow information
            self.h_npp = self._compute_npp(dP_mech)

        all_ok = all(sr.all_constraints_met for sr in stair_results)

        return EstimationResult(
            config=self.config,
            stair_results=stair_results,
            exhaust_result=exhaust_result,
            sensitivity_cases=[],  # filled by run_sensitivity
            calculation_traces=self.traces,
            npp_height=self.h_npp,
            all_constraints_met=all_ok,
            warnings=self.warnings,
        )

    def run_sensitivity(self, base_result: EstimationResult) -> List[SensitivityCase]:
        """Run mandatory sensitivity analysis (Section 7).

        Varies parameters per Section 7.1 and reports changes.
        """
        cases: List[SensitivityCase] = []
        base_supply = sum(sr.q_supply_design for sr in base_result.stair_results)
        base_exhaust = base_result.exhaust_result.q_exhaust_total

        def _pct_change(new_val: float, base_val: float) -> float:
            if abs(base_val) < 1e-12:
                return 0.0
            return (new_val - base_val) / base_val * 100.0

        # --- Case 1: Exterior wall leakage (tight, loose) ---
        for tightness in ["tight", "loose"]:
            cfg = copy.deepcopy(self.config)
            cfg.leakage.exterior_wall = tightness
            eng = EstimationEngine(cfg)
            r = eng.solve()
            t_supply = sum(sr.q_supply_design for sr in r.stair_results)
            t_exhaust = r.exhaust_result.q_exhaust_total
            crit = r.stair_results[0].critical_floor_min_dp if r.stair_results else ""
            cases.append(SensitivityCase(
                parameter="Exterior wall leakage",
                value_description=tightness.capitalize(),
                stair_supply_total=t_supply,
                exhaust_total=t_exhaust,
                stair_supply_change_pct=_pct_change(t_supply, base_supply),
                exhaust_change_pct=_pct_change(t_exhaust, base_exhaust),
                critical_floor=crit,
                constraints_violated=not r.all_constraints_met,
            ))

        # --- Case 2: Door leakage area +/- 50% ---
        for factor, desc in [(0.5, "-50%"), (1.5, "+50%")]:
            cfg = copy.deepcopy(self.config)
            base_area = get_stair_door_leakage(self.config, self.config.stairwells[0])
            cfg.leakage.custom_stair_door_area = base_area * factor
            eng = EstimationEngine(cfg)
            r = eng.solve()
            t_supply = sum(sr.q_supply_design for sr in r.stair_results)
            t_exhaust = r.exhaust_result.q_exhaust_total
            crit = r.stair_results[0].critical_floor_min_dp if r.stair_results else ""
            cases.append(SensitivityCase(
                parameter="Door leakage area",
                value_description=desc,
                stair_supply_total=t_supply,
                exhaust_total=t_exhaust,
                stair_supply_change_pct=_pct_change(t_supply, base_supply),
                exhaust_change_pct=_pct_change(t_exhaust, base_exhaust),
                critical_floor=crit,
                constraints_violated=not r.all_constraints_met,
            ))

        # --- Case 3: Outdoor temperature (winter vs summer) ---
        cfg = copy.deepcopy(self.config)
        eng = EstimationEngine(cfg)
        r = eng.solve(season="summer")
        t_supply = sum(sr.q_supply_design for sr in r.stair_results)
        t_exhaust = r.exhaust_result.q_exhaust_total
        crit = r.stair_results[0].critical_floor_min_dp if r.stair_results else ""
        cases.append(SensitivityCase(
            parameter="Outdoor temperature",
            value_description="Summer design",
            stair_supply_total=t_supply,
            exhaust_total=t_exhaust,
            stair_supply_change_pct=_pct_change(t_supply, base_supply),
            exhaust_change_pct=_pct_change(t_exhaust, base_exhaust),
            critical_floor=crit,
            constraints_violated=not r.all_constraints_met,
        ))

        # --- Case 4: Number of open doors (0, 1, 2, 3) ---
        for n_open in [0, 1, 2, 3]:
            if n_open == self.config.conditions.n_open_doors:
                continue
            cfg = copy.deepcopy(self.config)
            cfg.conditions.n_open_doors = n_open
            eng = EstimationEngine(cfg)
            r = eng.solve()
            t_supply = sum(sr.q_supply_design for sr in r.stair_results)
            t_exhaust = r.exhaust_result.q_exhaust_total
            crit = r.stair_results[0].critical_floor_min_dp if r.stair_results else ""
            cases.append(SensitivityCase(
                parameter="Number of open doors",
                value_description=str(n_open),
                stair_supply_total=t_supply,
                exhaust_total=t_exhaust,
                stair_supply_change_pct=_pct_change(t_supply, base_supply),
                exhaust_change_pct=_pct_change(t_exhaust, base_exhaust),
                critical_floor=crit,
                constraints_violated=not r.all_constraints_met,
            ))

        # --- Case 5: Fire floor temperature (200, 400, 600 deg C) ---
        for T_fire in [200, 400, 600]:
            if abs(T_fire - self.config.conditions.T_fire) < 1:
                continue
            cfg = copy.deepcopy(self.config)
            cfg.conditions.T_fire = float(T_fire)
            eng = EstimationEngine(cfg)
            r = eng.solve()
            t_supply = sum(sr.q_supply_design for sr in r.stair_results)
            t_exhaust = r.exhaust_result.q_exhaust_total
            crit = r.stair_results[0].critical_floor_min_dp if r.stair_results else ""
            cases.append(SensitivityCase(
                parameter="Fire floor temperature",
                value_description=f"{T_fire} deg C",
                stair_supply_total=t_supply,
                exhaust_total=t_exhaust,
                stair_supply_change_pct=_pct_change(t_supply, base_supply),
                exhaust_change_pct=_pct_change(t_exhaust, base_exhaust),
                critical_floor=crit,
                constraints_violated=not r.all_constraints_met,
            ))

        # --- Case 6: Wind speed (0%, 50%, 100%) ---
        for pct, desc in [(0, "0%"), (50, "50%")]:
            cfg = copy.deepcopy(self.config)
            cfg.conditions.wind_speed = self.config.conditions.wind_speed * pct / 100.0
            eng = EstimationEngine(cfg)
            r = eng.solve()
            t_supply = sum(sr.q_supply_design for sr in r.stair_results)
            t_exhaust = r.exhaust_result.q_exhaust_total
            crit = r.stair_results[0].critical_floor_min_dp if r.stair_results else ""
            cases.append(SensitivityCase(
                parameter="Wind speed",
                value_description=f"{desc} of design",
                stair_supply_total=t_supply,
                exhaust_total=t_exhaust,
                stair_supply_change_pct=_pct_change(t_supply, base_supply),
                exhaust_change_pct=_pct_change(t_exhaust, base_exhaust),
                critical_floor=crit,
                constraints_violated=not r.all_constraints_met,
            ))

        # --- Case 7: Elevator shaft vented vs unvented ---
        if self.config.elevators.vent_area == 0:
            cfg = copy.deepcopy(self.config)
            cfg.elevators.vent_area = 0.1  # small vent
            eng = EstimationEngine(cfg)
            r = eng.solve()
            t_supply = sum(sr.q_supply_design for sr in r.stair_results)
            t_exhaust = r.exhaust_result.q_exhaust_total
            crit = r.stair_results[0].critical_floor_min_dp if r.stair_results else ""
            cases.append(SensitivityCase(
                parameter="Elevator shaft config",
                value_description="Vented (0.1 m^2)",
                stair_supply_total=t_supply,
                exhaust_total=t_exhaust,
                stair_supply_change_pct=_pct_change(t_supply, base_supply),
                exhaust_change_pct=_pct_change(t_exhaust, base_exhaust),
                critical_floor=crit,
                constraints_violated=not r.all_constraints_met,
            ))
        else:
            cfg = copy.deepcopy(self.config)
            cfg.elevators.vent_area = 0.0
            eng = EstimationEngine(cfg)
            r = eng.solve()
            t_supply = sum(sr.q_supply_design for sr in r.stair_results)
            t_exhaust = r.exhaust_result.q_exhaust_total
            crit = r.stair_results[0].critical_floor_min_dp if r.stair_results else ""
            cases.append(SensitivityCase(
                parameter="Elevator shaft config",
                value_description="Unvented",
                stair_supply_total=t_supply,
                exhaust_total=t_exhaust,
                stair_supply_change_pct=_pct_change(t_supply, base_supply),
                exhaust_change_pct=_pct_change(t_exhaust, base_exhaust),
                critical_floor=crit,
                constraints_violated=not r.all_constraints_met,
            ))

        return cases

    def run_full(self) -> EstimationResult:
        """Run the full analysis including sensitivity."""
        result = self.solve()
        result.sensitivity_cases = self.run_sensitivity(result)
        return result
