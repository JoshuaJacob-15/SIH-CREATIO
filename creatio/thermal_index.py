"""
thermal_index.py

Contains all heat-stress calculations:
- WBGT
- Black globe temperature
- WBGT risk category
- Heat Index
- UTCI
"""

import math

from pythermalcomfort.models import utci


# ---------------------------------------------------------
# WBGT
# ---------------------------------------------------------

def compute_wbgt(
    temp_c: float,
    tw: float,
    dew_point: float,
    rh: float,
    wind_mh: float,
    solar: float,
    solar_dir: float,
    solar_dif: float,
    z_angle: float,
    pressure: float,
    outdoor: bool,
) -> float:
    """
    Calculate Wet-Bulb Globe Temperature.

    Outdoor:
        WBGT = 0.7 * Tw + 0.2 * Tg + 0.1 * Ta

    Indoor:
        WBGT = 0.7 * Tw + 0.3 * Tg
    """

    # Convert wind speed from m/s to m/hour.
    wind_mh = 1000 * wind_mh

    tg = black_globe_temperature(
        wind_mh,
        temp_c,
        dew_point,
        solar,
        solar_dir,
        solar_dif,
        z_angle,
        pressure,
    )

    if outdoor:
        wbgt = (
            0.7 * tw
            + 0.2 * tg
            + 0.1 * temp_c
        )
    else:
        wbgt = (
            0.7 * tw
            + 0.3 * tg
        )

    return round(wbgt, 2)


# ---------------------------------------------------------
# Black Globe Temperature
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
    Estimate black globe temperature.

    Parameters:
        u: Wind speed in m/hour
        Ta: Air temperature in °C
        Td: Dew point in °C
        S: Solar irradiance in W/m²
        fdb: Direct beam radiation term
        fdif: Diffuse radiation term
        z: Solar zenith angle in radians
        P: Barometric pressure in hPa
    """

    sigma = 5.67e-8
    h = 0.315

    # Atmospheric vapor pressure
    ea = (
        math.exp(
            17.67 * (Td - Ta) / (Td + 243.5)
        )
        * (1.0007 + 0.00000346 * P)
        * 6.112
        * math.exp(
            17.502 * Ta / (240.97 + Ta)
        )
    )

    # Atmospheric thermal emissivity
    epsilon_a = 0.575 * (ea ** (1 / 7))

    # Solar geometry check
    cos_z = math.cos(z)

    if cos_z <= 0:
        raise ValueError(
            "Solar zenith angle must be less than 90 degrees."
        )

    # Calculate B
    B = (
        S
        * (
            fdb / (4 * sigma * cos_z)
            + (1.2 / sigma) * fdif
        )
        + epsilon_a * (Ta ** 4)
    )

    # Calculate C
    C = (
        h * (u ** 0.58)
    ) / (5.3865e-8)

    # Black globe temperature
    Tg = (
        B + C * Ta + 7680000
    ) / (
        C + 256000
    )

    return Tg


# ---------------------------------------------------------
# WBGT Risk Category
# ---------------------------------------------------------

def wbgt_category(wbgt_c: float) -> str:
    """
    Convert WBGT into a category.
    """

    if wbgt_c <= 27.7:
        return "White"

    if wbgt_c <= 29.4:
        return "Green"

    if wbgt_c <= 31.0:
        return "Yellow"

    if wbgt_c <= 32.1:
        return "Red"

    return "Black"


# ---------------------------------------------------------
# Heat Index
# ---------------------------------------------------------

def heat_index(temp_c: float, rh: float) -> float:
    """
    Calculate Heat Index in °C.
    """

    t = temp_c * 9.0 / 5.0 + 32.0

    if t >= 80 and rh >= 40:

        hi_f = (
            -42.379
            + 2.04901523 * t
            + 10.14333127 * rh
            - 0.22475541 * t * rh
            - 0.00683783 * t ** 2
            - 0.05481717 * rh ** 2
            + 0.00122874 * t ** 2 * rh
            + 0.00085282 * t * rh ** 2
            - 0.00000199 * t * 2 * rh * 2
        )

    else:

        hi_f = (
            0.363445176
            + 0.988622465 * t
            + 4.777114035 * rh
            - 0.114037667 * t * rh
            - 8.50208e-4 * t ** 2
            - 2.0716198e-2 * rh ** 2
            + 6.87678e-4 * t ** 2 * rh
            + 2.74954e-4 * t * rh ** 2
        )

    return round(
        (hi_f - 32.0) * 5.0 / 9.0,
        2,
    )


# ---------------------------------------------------------
# UTCI
# ---------------------------------------------------------

def calculate_utci(
    Ta: float,
    Tmrt: float,
    wind_speed: float,
    RH: float,
):
    """
    Calculate Universal Thermal Climate Index.

    Ta:
        Air temperature °C

    Tmrt:
        Mean radiant temperature °C

    wind_speed:
        Wind speed in m/s

    RH:
        Relative humidity %
    """

    result = utci(
        tdb=Ta,
        tr=Tmrt,
        v=wind_speed * 1000/3600,
        rh=RH,
        round_output=False,
    )

    return float(result.utci), result.stress_category