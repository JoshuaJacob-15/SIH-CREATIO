"""
thermal_index.py - Fixed

Heat-stress calculations:
- WBGT (Wet-Bulb Globe Temperature) and its risk category
- Black globe temperature (Liljegren-style linearised estimate)
- Heat Index (NWS Rothfusz regression with adjustments)
- UTCI (Universal Thermal Climate Index)
- Mean Radiant Temperature (ISO 7726)
- Solar zenith angle

UNIT CONVENTIONS (read this first)
----------------------------------
- Wind speed at every public function boundary is in **km/h** (this is what
  the weather fetcher returns). Conversion to m/s or m/h happens inside.
- Temperatures are in °C. The globe formula is a linearisation around 40 °C
  and works in °C (do NOT convert Ta to Kelvin there).
- Radiation: `S` is total shortwave irradiance in W/m². `fdb` and `fdif` are
  DIMENSIONLESS FRACTIONS of S (direct / diffuse). Use `split_radiation()`
  to build them from W/m² values.
- Solar zenith angle is in radians.

Requires pythermalcomfort >= 3.0 (result object with .utci / .stress_category).
"""

import math
import logging
import numbers
from typing import Tuple

from pythermalcomfort.models import utci
import pandas as pd
import pvlib

logger = logging.getLogger(__name__)

SIGMA = 5.67e-8  # Stefan-Boltzmann constant, W/(m²·K⁴)

# Below this the solar beam term is capped (zenith ~87°) so it cannot explode
# near sunrise/sunset.
MIN_COS_ZENITH = 0.05

# Minimum wind used in convection terms (m/s). Zero wind makes the globe
# formula degenerate (C -> 0).
MIN_WIND_MS = 0.5

# WBGT flag thresholds (°C). NOTE: these are the thresholds your project
# already used. The common US military scheme (TB MED 507) is different:
# white <25.6, green <27.8, yellow <29.4, red <31.1, black >=31.1.
# Confirm which standard you intend and cite it.
WBGT_THRESHOLDS = (
    (27.7, "White"),
    (29.4, "Green"),
    (31.0, "Yellow"),
    (32.1, "Red"),
)


def _check_number(name: str, value) -> float:
    """Raise ValueError unless value is a finite real number."""
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise ValueError(f"{name} must be numeric, got {type(value).__name__}")
    if math.isnan(value) or math.isinf(value):
        raise ValueError(f"{name} must be finite, got {value}")
    return float(value)


# ---------------------------------------------------------
# RADIATION HELPER
# ---------------------------------------------------------

def split_radiation(direct: float, diffuse: float) -> Tuple[float, float, float]:
    """
    Build (S, fdb, fdif) for `black_globe_temperature` from W/m² values.

    Args:
        direct: Direct radiation on the horizontal plane, W/m²
        diffuse: Diffuse radiation, W/m²

    Returns:
        (S, fdb, fdif) where S = direct + diffuse (W/m²) and fdb/fdif are
        the dimensionless fractions of S. Returns (0, 0, 0) when there is
        no sunlight.

    Note:
        Use direct and diffuse from the SAME time basis (both instantaneous
        or both hourly means). Mixing them with a separate `solar_radiation`
        field gives inconsistent fractions.
    """
    direct = max(_check_number("direct", direct), 0.0)
    diffuse = max(_check_number("diffuse", diffuse), 0.0)
    s = direct + diffuse
    if s <= 0:
        return 0.0, 0.0, 0.0
    return s, direct / s, diffuse / s


def radiation_from_dni(dni: float, diffuse: float, z: float) -> Tuple[float, float, float]:
    """
    PREFERRED way to build (S, fdb, fdif): from direct NORMAL irradiance,
    diffuse horizontal irradiance and the solar zenith angle.

    Direct horizontal = DNI * cos(z), so the result is self-consistent with
    the zenith angle. This avoids the common mismatch where hourly-mean
    "direct radiation" is large while the sun is already at the horizon.

    Args:
        dni: Direct normal irradiance, W/m²
        diffuse: Diffuse horizontal irradiance, W/m²
        z: Solar zenith angle, radians

    Returns:
        (S, fdb, fdif); (0, 0, 0) when the sun is down or there is no light.
    """
    dni = max(_check_number("dni", dni), 0.0)
    diffuse = max(_check_number("diffuse", diffuse), 0.0)
    z = _check_number("z", z)
    cos_z = math.cos(z)
    direct_h = dni * cos_z if cos_z > 0 else 0.0
    return split_radiation(direct_h, diffuse)


# ---------------------------------------------------------
# WBGT
# ---------------------------------------------------------

def compute_wbgt(temp_c: float, tw: float, tg: float, outdoor: bool = True) -> float:
    """
    Wet-Bulb Globe Temperature.

    Outdoor (solar load): WBGT = 0.7*Tw + 0.2*Tg + 0.1*Ta
    Indoor / no solar:    WBGT = 0.7*Tw + 0.3*Tg

    Args:
        temp_c: Air temperature, °C
        tw: NATURAL wet-bulb temperature, °C (not psychrometric wet-bulb;
            a psychrometric value will underestimate WBGT)
        tg: Black globe temperature, °C
        outdoor: True outdoors, False indoors

    Returns:
        WBGT in °C, rounded to 2 decimals.
    """
    temp_c = _check_number("temp_c", temp_c)
    tw = _check_number("tw", tw)
    tg = _check_number("tg", tg)

    if not (-50 <= tw <= 50 and -50 <= tg <= 80 and -50 <= temp_c <= 60):
        logger.warning("WBGT inputs may be out of realistic range: Ta=%s, Tw=%s, Tg=%s",
                       temp_c, tw, tg)

    if outdoor:
        wbgt = 0.7 * tw + 0.2 * tg + 0.1 * temp_c
    else:
        wbgt = 0.7 * tw + 0.3 * tg

    wbgt = round(wbgt, 2)
    logger.debug("WBGT result: %s °C", wbgt)
    return wbgt


def wbgt_category(wbgt_c: float) -> str:
    """
    Convert WBGT to a colour-flag category using WBGT_THRESHOLDS.

    Args:
        wbgt_c: WBGT in °C

    Returns:
        "White", "Green", "Yellow", "Red" or "Black"
    """
    wbgt_c = _check_number("wbgt_c", wbgt_c)
    for upper, label in WBGT_THRESHOLDS:
        if wbgt_c <= upper:
            return label
    return "Black"


# ---------------------------------------------------------
# BLACK GLOBE TEMPERATURE
# ---------------------------------------------------------

def black_globe_temperature(
    u: float,
    Ta: float,
    Td: float,
    S: float,
    fdb: float,
    fdif: float,
    z: float,
    P: float,
) -> float:
    """
    Estimate black globe temperature (150 mm sphere).

    Args:
        u: Wind speed in km/h
        Ta: Air temperature, °C
        Td: Dew point, °C
        S: Total shortwave irradiance on the horizontal, W/m²
        fdb: Fraction of S that is direct beam (0-1, dimensionless)
        fdif: Fraction of S that is diffuse (0-1, dimensionless)
        z: Solar zenith angle, radians
        P: Barometric pressure, hPa

    Returns:
        Black globe temperature in °C. At night (sun below the horizon) only
        the diffuse term is used, so the result is close to Ta.

    Raises:
        ValueError: on invalid inputs or an implausible result.
    """
    u = _check_number("u", u)
    Ta = _check_number("Ta", Ta)
    Td = _check_number("Td", Td)
    S = _check_number("S", S)
    fdb = _check_number("fdb", fdb)
    fdif = _check_number("fdif", fdif)
    z = _check_number("z", z)
    P = _check_number("P", P)

    if u < 0:
        raise ValueError(f"Wind speed cannot be negative: {u}")
    if S < 0:
        raise ValueError(f"Solar irradiance cannot be negative: {S}")
    if not (0.0 <= fdb <= 1.0 and 0.0 <= fdif <= 1.0):
        raise ValueError(
            f"fdb and fdif must be fractions in [0, 1], got fdb={fdb}, fdif={fdif}. "
            "If you have W/m² values, use split_radiation()."
        )

    # km/h -> m/s -> m/h (the formula's C term expects m/h), with a wind floor.
    u_ms = max(u * 1000.0 / 3600.0, MIN_WIND_MS)
    u_m_hour = u_ms * 3600.0

    h = 0.315  # sphere heat-transfer coefficient

    # Atmospheric vapour pressure (hPa) - Liljegren/Bolton form
    ea = (
        math.exp(17.67 * (Td - Ta) / (Td + 243.5))
        * (1.0007 + 0.00000346 * P)
        * 6.112
        * math.exp(17.502 * Ta / (240.97 + Ta))
    )
    epsilon_a = 0.575 * (ea ** (1.0 / 7.0))

    cos_z = math.cos(z)
    if cos_z <= 0:
        # Sun below horizon: no beam, diffuse only
        solar = S * (1.2 / SIGMA) * fdif
    else:
        cos_z = max(cos_z, MIN_COS_ZENITH)
        solar = S * (fdb / (4.0 * SIGMA * cos_z) + (1.2 / SIGMA) * fdif)

    B = solar + epsilon_a * (Ta ** 4)
    C = (h * (u_m_hour ** 0.58)) / 5.3865e-8

    # Linearised around 40 °C: 256000 = 4*40^3, 7680000 = 3*40^4
    Tg = (B + C * Ta + 7680000.0) / (C + 256000.0)

    # Sanity check so garbage never reaches WBGT / risk scoring
    if not (Ta - 5.0 <= Tg <= Ta + 30.0):
        raise ValueError(
            f"Implausible globe temperature {Tg:.1f} °C for Ta={Ta} °C "
            f"(S={S}, fdb={fdb}, fdif={fdif}, zenith={math.degrees(z):.1f}°)"
        )

    logger.debug("Black globe temperature: %.2f °C", Tg)
    return Tg


# ---------------------------------------------------------
# HEAT INDEX
# ---------------------------------------------------------

def heat_index(temp_c: float, rh: float) -> float:
    """
    Heat Index (apparent temperature) following the US NWS procedure.

    1. Compute the simple Steadman-style formula.
    2. If (simple + T)/2 < 80 °F use it.
    3. Otherwise use the Rothfusz regression, with the NWS low-humidity and
       high-humidity adjustments.

    Args:
        temp_c: Air temperature, °C
        rh: Relative humidity, % (0-100)

    Returns:
        Heat Index in °C, rounded to 2 decimals.

    References:
        NWS Heat Index equation (Rothfusz 1990, built on Steadman 1979).
    """
    temp_c = _check_number("temp_c", temp_c)
    rh = _check_number("rh", rh)

    if not -50 <= temp_c <= 60:
        logger.warning("Temperature %s °C is outside typical range", temp_c)
    if not 0 <= rh <= 100:
        logger.warning("Relative humidity %s%% is outside [0, 100]", rh)

    t_f = temp_c * 9.0 / 5.0 + 32.0

    simple = 0.5 * (t_f + 61.0 + (t_f - 68.0) * 1.2 + rh * 0.094)

    if (simple + t_f) / 2.0 < 80.0:
        hi_f = simple
    else:
        hi_f = (
            -42.379
            + 2.04901523 * t_f
            + 10.14333127 * rh
            - 0.22475541 * t_f * rh
            - 0.00683783 * t_f ** 2
            - 0.05481717 * rh ** 2
            + 0.00122874 * t_f ** 2 * rh
            + 0.00085282 * t_f * rh ** 2
            - 0.00000199 * t_f ** 2 * rh ** 2
        )
        if rh < 13 and 80 <= t_f <= 112:
            hi_f -= ((13 - rh) / 4.0) * math.sqrt((17 - abs(t_f - 95.0)) / 17.0)
        elif rh > 85 and 80 <= t_f <= 87:
            hi_f += ((rh - 85) / 10.0) * ((87 - t_f) / 5.0)

    hi_c = round((hi_f - 32.0) * 5.0 / 9.0, 2)
    logger.debug("Heat index: %s °C", hi_c)
    return hi_c


# ---------------------------------------------------------
# UTCI
# ---------------------------------------------------------

def calculate_utci(Ta, Tmrt, wind_speed, RH):
    """
    Calculate UTCI using pythermalcomfort.

    Inputs:
        Ta         : air temperature in °C
        Tmrt       : mean radiant temperature in °C
        wind_speed : wind speed in km/h
        RH         : relative humidity in %

    Returns:
        (utci_value, stress_category)
    """

    try:
        from pythermalcomfort.models import utci

        # --------------------------------------------------
        # Validate inputs
        # --------------------------------------------------

        Ta = float(Ta)
        Tmrt = float(Tmrt)
        wind_speed = float(wind_speed)
        RH = float(RH)

        if not math.isfinite(Ta):
            raise ValueError(f"Invalid air temperature: {Ta}")

        if not math.isfinite(Tmrt):
            raise ValueError(f"Invalid MRT: {Tmrt}")

        if not math.isfinite(wind_speed):
            raise ValueError(f"Invalid wind speed: {wind_speed}")

        if not math.isfinite(RH):
            raise ValueError(f"Invalid relative humidity: {RH}")

        # RH must be between 0 and 100
        RH = max(0.0, min(100.0, RH))

        # --------------------------------------------------
        # Convert km/h -> m/s
        # --------------------------------------------------

        wind_ms = wind_speed / 3.6

        # UTCI requires at least 0.5 m/s
        wind_ms = max(0.5, min(17.0, wind_ms))

        # --------------------------------------------------
        # Check UTCI applicability limits
        # --------------------------------------------------

        if not (-50 < Ta < 50):
            raise ValueError(
                f"Air temperature {Ta}°C is outside UTCI limits."
            )

        if not (Ta - 30 < Tmrt < Ta + 70):
            raise ValueError(
                f"MRT {Tmrt}°C is outside UTCI limits "
                f"for Ta={Ta}°C."
            )

        # --------------------------------------------------
        # Calculate UTCI
        # --------------------------------------------------
        result = utci(
            tdb=Ta,
            tr=Tmrt,
            v=wind_ms,
            rh=RH,
            units="SI",
            limit_inputs=True,
        )

        # Your installed pythermalcomfort version returns
        # the UTCI value directly as a numpy.float64.
        utci_value = float(result)

        # Determine the stress category ourselves
        if utci_value < -40:
            stress_category = "Extreme cold stress"
        elif utci_value < -27:
            stress_category = "Very strong cold stress"
        elif utci_value < -13:
            stress_category = "Strong cold stress"
        elif utci_value < 0:
            stress_category = "Moderate cold stress"
        elif utci_value < 9:
            stress_category = "No thermal stress"
        elif utci_value < 26:
            stress_category = "Moderate heat stress"
        elif utci_value < 32:
            stress_category = "Strong heat stress"
        elif utci_value < 38:
            stress_category = "Very strong heat stress"
        else:
            stress_category = "Extreme heat stress"
        # --------------------------------------------------
        # Validate result
        # --------------------------------------------------

        if utci_value is None:
            raise ValueError(
                "pythermalcomfort returned None for UTCI."
            )

        utci_value = float(utci_value)

        if not math.isfinite(utci_value):
            raise ValueError(
                f"pythermalcomfort returned invalid UTCI: {utci_value}"
            )

        return round(utci_value, 2), str(stress_category)

    except Exception as e:
        logger.error(
            f"UTCI calculation failed: "
            f"Ta={Ta}, Tmrt={Tmrt}, "
            f"wind={wind_speed} km/h, RH={RH}. "
            f"Error: {e}",
            exc_info=True,
        )

        raise
# ---------------------------------------------------------
# MEAN RADIANT TEMPERATURE
# ---------------------------------------------------------

def calculate_mrt_standard(Tg: float, Ta: float, wind_speed: float) -> float:
    """
    Mean Radiant Temperature from a 150-mm black globe (ISO 7726).

    Uses the larger of the forced- and natural-convection terms.

    Args:
        Tg: Black globe temperature, °C
        Ta: Air temperature, °C
        wind_speed: Wind speed in km/h

    Returns:
        Mean radiant temperature, °C
    """
    Tg = _check_number("Tg", Tg)
    Ta = _check_number("Ta", Ta)
    wind_speed = _check_number("wind_speed", wind_speed)
    if wind_speed < 0:
        raise ValueError(f"Wind speed cannot be negative: {wind_speed}")

    v = max(wind_speed * 1000.0 / 3600.0, MIN_WIND_MS)  # m/s
    dt = Tg - Ta
    D = 0.15      # globe diameter, m
    eps = 0.95    # globe emissivity

    forced = 1.1e8 * (v ** 0.6) / (eps * D ** 0.4)                    # ≈ 2.5e8 * v^0.6
    natural = 0.25e8 / eps * (abs(dt) / D) ** 0.25
    hc_term = max(forced, natural)

    base = (Tg + 273.15) ** 4 + hc_term * dt
    Tmrt = max(base, 0.0) ** 0.25 - 273.15

    logger.debug("Mean radiant temperature: %.2f °C", Tmrt)
    return Tmrt


# ---------------------------------------------------------
# SOLAR ZENITH ANGLE
# ---------------------------------------------------------

def calculate_solar_zenith(
    latitude: float,
    longitude: float,
    timestamp: str,
    timezone: str = "UTC",
) -> float:
    """
    Solar zenith angle (radians) using NREL SPA via pvlib.

    `timestamp` must be expressed in `timezone` (default UTC). If it already
    carries tz info, it is converted to UTC and `timezone` is ignored.

    Args:
        latitude: Decimal degrees, north positive
        longitude: Decimal degrees, east positive
        timestamp: e.g. "2026-09-24 12:41:54"
        timezone: IANA timezone name matching `timestamp`

    Returns:
        Zenith angle in radians (0 = overhead, pi/2 = horizon, >pi/2 = night).

    Raises:
        ValueError: if the timestamp cannot be parsed.
    """
    latitude = _check_number("latitude", latitude)
    longitude = _check_number("longitude", longitude)

    try:
        ts = pd.Timestamp(timestamp)
    except (ValueError, TypeError) as e:
        raise ValueError(
            f"Invalid timestamp {timestamp!r}. Expected 'YYYY-MM-DD HH:MM:SS'. Error: {e}"
        ) from e

    if ts.tzinfo is None:
        ts = ts.tz_localize(timezone)
    else:
        ts = ts.tz_convert("UTC")

    solar_position = pvlib.solarposition.get_solarposition(
        time=pd.DatetimeIndex([ts]),
        latitude=latitude,
        longitude=longitude,
        method="nrel_numpy",
    )

    zenith_deg = float(solar_position["zenith"].iloc[0])
    logger.debug("Solar zenith: %.2f°", zenith_deg)
    return math.radians(zenith_deg)