"""Unit conversion constants and functions for CONTAM analysis.

All user-facing inputs/outputs use US customary units.
CONTAM uses SI internally.
"""

# Airflow: SCFM to kg/s
# Standard conditions: 59 deg F (15 deg C), 1 atm
# This constant is preserved exactly from the existing script.
SCFM_TO_KG_PER_S = 1.0 / 1759.721156  # approx 5.683e-4


def f_to_kelvin(temp_f: float) -> float:
    """Convert temperature from Fahrenheit to Kelvin."""
    return (temp_f - 32.0) * 5.0 / 9.0 + 273.15


def kelvin_to_f(temp_k: float) -> float:
    """Convert temperature from Kelvin to Fahrenheit."""
    return (temp_k - 273.15) * 9.0 / 5.0 + 32.0


# Wind speed: mph to m/s
MPH_TO_MS = 1.0 / 2.237  # approx 0.44704


def mph_to_ms(speed_mph: float) -> float:
    """Convert wind speed from mph to m/s."""
    return speed_mph * MPH_TO_MS


def ms_to_mph(speed_ms: float) -> float:
    """Convert wind speed from m/s to mph."""
    return speed_ms / MPH_TO_MS


# Pressure: Pa to inches of water column
PA_TO_INWC = 1.0 / 249.0  # 1 in. w.c. approx 249 Pa


def pa_to_inwc(pressure_pa: float) -> float:
    """Convert pressure from Pascals to inches of water column."""
    return pressure_pa * PA_TO_INWC


def inwc_to_pa(pressure_inwc: float) -> float:
    """Convert pressure from inches of water column to Pascals."""
    return pressure_inwc / PA_TO_INWC


def scfm_to_kgs(flow_scfm: float) -> float:
    """Convert airflow from SCFM to kg/s."""
    return flow_scfm * SCFM_TO_KG_PER_S
