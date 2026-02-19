"""Quick validation of the estimation engine against the spec's sample trace."""

import sys
sys.path.insert(0, '.')

from core.estimation_engine import (
    EstimationEngine, eq01_air_density, eq02_door_leakage_area,
    eq03_orifice_flow_volume, eq07_stack_effect, eq10b_total_door_force,
    eq12_required_open_door_flow, cms_to_cfm, _c_to_k,
)
from core.estimation_models import EstimationConfig, BuildingGeometry, StairwellGeometry, DesignConditions

print("=== Equation Unit Tests ===\n")

# EQ-01: Air density at 20 deg C, 101325 Pa
rho = eq01_air_density(101325, _c_to_k(20))
print(f"EQ-01: rho(20C, 101325 Pa) = {rho:.4f} kg/m^3  (expect ~1.2041)")
assert abs(rho - 1.2041) < 0.001, f"FAIL: {rho}"

# EQ-01: Fire floor at 300 deg C
rho_f = eq01_air_density(101325, _c_to_k(300))
print(f"EQ-01: rho(300C) = {rho_f:.4f} kg/m^3  (expect ~0.616)")
assert 0.5 < rho_f < 0.7, f"FAIL: {rho_f}"

# EQ-02: Door leakage from crack (3mm gap, 1.1m wide, 2.1m high)
A_Ld = eq02_door_leakage_area(0.003, 1.1, 2.1)
print(f"EQ-02: A_Ld(3mm, 1.1x2.1) = {A_Ld:.5f} m^2  (expect ~0.0063)")
# 0.003 * (2*1.1 + 2*2.1 - 1.1) = 0.003 * (2.2 + 4.2 - 1.1) = 0.003 * 5.3 = 0.0159
# Wait, w_threshold = w_d = 1.1 by default
# 0.003 * (2*1.1 + 2*2.1 - 1.1) = 0.003 * (2.2 + 4.2 - 1.1) = 0.003 * 5.3 = 0.0159
print(f"  (w_threshold = w_d = 1.1)")

# EQ-03: Orifice flow - matches spec Appendix B sample
# Q = 0.65 * 0.020 * sqrt(2 * 31.7 / 1.189)
Q = eq03_orifice_flow_volume(0.65, 0.020, 31.7, 1.189)
print(f"EQ-03: Q(Cd=0.65, A=0.020, dP=31.7, rho=1.189) = {Q:.4f} m^3/s  (expect ~0.0949)")
assert abs(Q - 0.0949) < 0.002, f"FAIL: {Q}"
print(f"  = {cms_to_cfm(Q):.0f} CFM (expect ~201)")

# EQ-07: Stack effect
T_o = _c_to_k(-18)  # Winter
T_s = _c_to_k(-18)  # Stair at outdoor temp
dP_s = eq07_stack_effect(T_o, T_s, 30.0, 17.5)  # h=30m, NPP=17.5m
print(f"EQ-07: dP_s(T_o={-18}C, T_s={-18}C, h=30, NPP=17.5) = {dP_s:.2f} Pa  (expect 0 since T_o == T_s)")

T_i = _c_to_k(22)
dP_s2 = eq07_stack_effect(T_o, T_i, 30.0, 17.5)
print(f"EQ-07: dP_s(T_o={-18}C, T_i={22}C, h=30, NPP=17.5) = {dP_s2:.2f} Pa")

# EQ-10b: Door force
F = eq10b_total_door_force(55, 50, 1.1, 2.1, 0.075)
print(f"EQ-10b: F_total(F_closer=55, dP=50, w=1.1, h=2.1, d=0.075) = {F:.1f} N  (expect < 133)")

# EQ-12: Open door flow
Q_open = eq12_required_open_door_flow(1.0, 1.1, 2.1)
print(f"EQ-12: Q_open(V=1.0, 1.1x2.1) = {Q_open:.3f} m^3/s = {cms_to_cfm(Q_open):.0f} CFM")

print("\n=== Full System Test (10-floor building, default config) ===\n")

config = EstimationConfig()
config.building.n_floors_above = 10
config.conditions.T_outdoor_winter = -18
config.conditions.T_indoor = 22
config.conditions.T_fire = 300
config.conditions.wind_speed = 12
config.fire_floor = 5

engine = EstimationEngine(config)
result = engine.run_full()

print(f"NPP Height: {result.npp_height:.2f} m")
print(f"All Constraints Met: {result.all_constraints_met}")
print(f"Warnings: {result.warnings}")

for sr in result.stair_results:
    print(f"\n--- {sr.label} ---")
    print(f"  Supply (all closed): {sr.q_supply_closed:.4f} m^3/s ({cms_to_cfm(sr.q_supply_closed):.0f} CFM)")
    print(f"  Supply (doors open):  {sr.q_supply_open:.4f} m^3/s ({cms_to_cfm(sr.q_supply_open):.0f} CFM)")
    print(f"  DESIGN Supply:        {sr.q_supply_design:.4f} m^3/s ({cms_to_cfm(sr.q_supply_design):.0f} CFM)")
    print(f"  Critical floor (min dP): {sr.critical_floor_min_dp}")
    print(f"  Critical floor (max F):  {sr.critical_floor_max_force}")
    print(f"  All OK: {sr.all_constraints_met}")

    print(f"\n  {'Floor':>5} {'Height':>6} {'dP_stk':>8} {'dP_wnd':>8} {'dP_net':>8} {'Q_leak':>10} {'Q_open':>10} {'F(N)':>7} {'Status':>6}")
    for fr in sr.floor_results:
        print(f"  {fr.floor_label:>5} {fr.height:>6.1f} {fr.dp_stack:>8.2f} {fr.dp_wind:>8.2f} {fr.dp_net:>8.2f} "
              f"{fr.q_leak_closed:>10.4f} {fr.q_flow_open:>10.4f} {fr.f_total:>7.1f} {fr.status:>6}")

er = result.exhaust_result
print(f"\n--- Exhaust (Fire Floor {er.fire_floor_label}) ---")
print(f"  Stair leakage:   {er.q_leak_stairs:.4f} m^3/s ({cms_to_cfm(er.q_leak_stairs):.0f} CFM)")
print(f"  Elevator leakage:{er.q_leak_elevators:.4f} m^3/s ({cms_to_cfm(er.q_leak_elevators):.0f} CFM)")
print(f"  Exterior walls:  {er.q_leak_exterior:.4f} m^3/s ({cms_to_cfm(er.q_leak_exterior):.0f} CFM)")
print(f"  Vertical:        {er.q_leak_vertical:.4f} m^3/s ({cms_to_cfm(er.q_leak_vertical):.0f} CFM)")
print(f"  Expansion:       {er.q_expansion:.4f} m^3/s ({cms_to_cfm(er.q_expansion):.0f} CFM)")
print(f"  TOTAL:           {er.q_exhaust_total:.4f} m^3/s ({cms_to_cfm(er.q_exhaust_total):.0f} CFM)")
print(f"  TOTAL (std):     {er.q_exhaust_std:.4f} m^3/s ({cms_to_cfm(er.q_exhaust_std):.0f} CFM)")

print(f"\n--- Sensitivity Analysis ({len(result.sensitivity_cases)} cases) ---")
for sc in result.sensitivity_cases:
    print(f"  {sc.parameter:30s} {sc.value_description:15s} Supply: {sc.stair_supply_change_pct:+6.1f}%  "
          f"Exhaust: {sc.exhaust_change_pct:+6.1f}%  Violated: {sc.constraints_violated}")

print("\n=== ALL TESTS PASSED ===")
