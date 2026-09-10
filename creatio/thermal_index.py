"""
thermal_index.py - Enhanced

Contains all heat-stress calculations with improved documentation and error handling:
- WBGT (Wet-Bulb Globe Temperature)
- Black globe temperature
- WBGT risk category
- Heat Index
- UTCI (Universal Thermal Climate Index)
- Mean Radiant Temperature
- Solar zenith angle

Enhancements:
- Better logging and error messages
- Input validation with bounds checking
- Unit conversions documented
- Exception handling with meaningful errors
"""

import math
import logging
from typing import Tuple, Optional

from pythermalcomfort.models import utci
import pandas as pd
import pvlib

# Setup logging
logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# WBGT (Wet-Bulb Globe Temperature)
# ---------------------------------------------------------

def compute_wbgt(
    temp_c: float,
    tw: float,
    tg: float,
    outdoor: bool = True,
) -> float:
    """
    Calculate Wet-Bulb Globe Temperature.
    
    WBGT is used to assess heat stress in occupational settings.
    It combines:
    - Wet-bulb temperature (Tw): effect of humidity
    - Globe temperature (Tg): effect of radiation
    - Air temperature (Ta): direct effect
    
    Outdoor formula:
        WBGT = 0.7 * Tw + 0.2 * Tg + 0.1 * Ta
    
    Indoor formula:
        WBGT = 0.7 * Tw + 0.3 * Tg
    
    Args:
        temp_c: Air temperature in °C
        tw: Wet-bulb temperature in °C
        tg: Black globe temperature in °C
        outdoor: True for outdoor, False for indoor
    
    Returns:
        WBGT in °C (rounded to 2 decimals)
    
    Raises:
        ValueError: If inputs are invalid
    """
    
    logger.debug(f"WBGT calc: Ta={temp_c}°C, Tw={tw}°C, Tg={tg}°C, outdoor={outdoor}")
    
    # Input validation
    if not isinstance(temp_c, (int, float)) or not isinstance(tw, (int, float)) or not isinstance(tg, (int, float)):
        raise ValueError(f"WBGT inputs must be numeric. Got: Ta={type(temp_c)}, Tw={type(tw)}, Tg={type(tg)}")
    
    if tw < -50 or tw > 50 or tg < -50 or tg > 80 or temp_c < -50 or temp_c > 60:
        logger.warning(f"WBGT inputs may be out of realistic range: Ta={temp_c}, Tw={tw}, Tg={tg}")
    
    if outdoor:
        wbgt = 0.7 * tw + 0.2 * tg + 0.1 * temp_c
    else:
        wbgt = 0.7 * tw + 0.3 * tg
    
    wbgt = round(wbgt, 2)
    logger.debug(f"WBGT result: {wbgt}°C")
    return wbgt


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
    Estimate black globe temperature using radiation and environmental parameters.
    
    The black globe is a standard 150-mm sphere with emissivity 0.95 that
    absorbs solar radiation and thermal radiation from surroundings.
    
    Parameters:
        u: Wind speed in m/h
        Ta: Air temperature in °C
        Td: Dew point in °C
        S: Solar irradiance (shortwave) in W/m²
        fdb: Direct beam radiation in W/m²
        fdif: Diffuse radiation in W/m²
        z: Solar zenith angle in radians
        P: Barometric pressure in hPa
    
    Returns:
        Black globe temperature in °C
    
    Raises:
        ValueError: If solar zenith angle indicates sun below horizon (nighttime)
    
    References:
        ISO 7726: Ergonomics of the thermal environment — Instruments and methods
        for measuring environmental parameters
    """
    
    logger.debug(f"Globe temp calc: Ta={Ta}°C, Td={Td}°C, S={S}W/m², z={z}rad, P={P}hPa, u={u}m/s")
    
    # Convert wind speed: m/s to m/hour
    u_m_hour = u * 1000
    logger.debug(f"Wind speed: {u} km/hour = {u_m_hour} m/hour")
    
    # Stefan-Boltzmann constant
    sigma = 5.67e-8  # W/(m²·K⁴)
    
    # Heat transfer coefficient for sphere
    h = 0.315
    
    # Calculate atmospheric vapor pressure (hPa)
    ea = (
        math.exp(17.67 * (Td - Ta) / (Td + 243.5))
        * (1.0007 + 0.00000346 * P)
        * 6.112
        * math.exp(17.502 * Ta / (240.97 + Ta))
    )
    
    # Atmospheric thermal emissivity (dimensionless)
    epsilon_a = 0.575 * (ea ** (1.0 / 7.0))
    
    # Solar geometry check: cos(z) > 0 means sun above horizon
    cos_z = math.cos(z)
    
    if cos_z <= 0:
        raise ValueError(
            f"Solar zenith angle {math.degrees(z):.1f}° indicates sun below horizon (nighttime). "
            f"Cannot calculate black globe temperature."
        )
    
    # Calculate intermediate term B (radiation balance)
    B = (
        S * (fdb / (4 * sigma * cos_z) + (1.2 / sigma) * fdif)
        + epsilon_a * ((Ta + 273.15) ** 4)
    )
    
    # Calculate intermediate term C (convection)
    C = (h * (u_m_hour ** 0.58)) / (5.3865e-8)
    
    # Black globe temperature (K⁴ form) -> °C
    Tg_fourth_power = B + C * Ta + 7680000
    denominator = C + 256000
    
    if denominator == 0:
        raise ValueError("Division by zero in black globe temperature calculation")
    
    Tg = Tg_fourth_power / denominator
    
    logger.debug(f"Black globe temperature: {Tg:.2f}°C")
    return Tg


# ---------------------------------------------------------
# WBGT RISK CATEGORY
# ---------------------------------------------------------

def wbgt_category(wbgt_c: float) -> str:
    """
    Convert WBGT into a risk category (color flag system).
    
    Used to guide work-rest ratios and activity restrictions in
    occupational and sports settings.
    
    Categories:
        White (≤27.7°C): Safe for prolonged outdoor activity
        Green (27.7-29.4°C): Caution, increase hydration
        Yellow (29.4-31.0°C): Increase work-rest ratios, reduce activity intensity
        Red (31.0-32.1°C): Significant restrictions, modify outdoor work
        Black (>32.1°C): Extreme risk, suspend outdoor activity
    
    Args:
        wbgt_c: WBGT in °C
    
    Returns:
        Risk category string
    """
    
    logger.debug(f"WBGT category for {wbgt_c}°C")
    
    if wbgt_c <= 27.7:
        return "White"
    elif wbgt_c <= 29.4:
        return "Green"
    elif wbgt_c <= 31.0:
        return "Yellow"
    elif wbgt_c <= 32.1:
        return "Red"
    else:
        return "Black"


# ---------------------------------------------------------
# HEAT INDEX
# ---------------------------------------------------------

def heat_index(temp_c: float, rh: float) -> float:
    """
    Calculate Heat Index (apparent temperature).
    
    The heat index is how hot it "feels" when accounting for humidity.
    Uses empirical formulas from US National Weather Service.
    
    Note: Heat Index is only defined for T ≥ 26.7°C (80°F) and is most
    accurate when RH ≥ 40%.
    
    Args:
        temp_c: Air temperature in °C
        rh: Relative humidity in % (0-100)
    
    Returns:
        Heat Index in °C (rounded to 2 decimals)
    
    References:
        Steadman, R. G. (1979). "The Assessment of Sultriness."
        Journal of Applied Meteorology, 18(7), 861–873.
    """
    
    logger.debug(f"Heat index calc: T={temp_c}°C, RH={rh}%")
    
    # Input validation
    if not -50 <= temp_c <= 60:
        logger.warning(f"Temperature {temp_c}°C is outside typical range")
    if not 0 <= rh <= 100:
        logger.warning(f"Relative humidity {rh}% is outside valid range [0-100]")
    
    # Convert to Fahrenheit
    t_f = temp_c * 9.0 / 5.0 + 32.0
    
    # Apply appropriate formula based on temperature and humidity
    if t_f >= 80 and rh >= 40:
        # High-accuracy formula for typical conditions
        hi_f = (
            -42.379
            + 2.04901523 * t_f
            + 10.14333127 * rh
            - 0.22475541 * t_f * rh
            - 0.00683783 * (t_f ** 2)
            - 0.05481717 * (rh ** 2)
            + 0.00122874 * (t_f ** 2) * rh
            + 0.00085282 * t_f * (rh ** 2)
            - 0.00000199 * (t_f ** 2) * (rh ** 2)
        )
    else:
        # General formula for lower temperature/humidity
        hi_f = (
            0.363445176
            + 0.988622465 * t_f
            + 4.777114035 * rh
            - 0.114037667 * t_f * rh
            - 8.50208e-4 * (t_f ** 2)
            - 2.0716198e-2 * (rh ** 2)
            + 6.87678e-4 * (t_f ** 2) * rh
            + 2.74954e-4 * t_f * (rh ** 2)
        )
    
    # Convert back to Celsius
    hi_c = (hi_f - 32.0) * 5.0 / 9.0
    hi_c = round(hi_c, 2)
    
    logger.debug(f"Heat index: {hi_c}°C")
    return hi_c


# ---------------------------------------------------------
# UTCI (Universal Thermal Climate Index)
# ---------------------------------------------------------

def calculate_utci(
    Ta: float,
    Tmrt: float,
    wind_speed: float,
    RH: float,
) -> Tuple[float, str]:
    """
    Calculate Universal Thermal Climate Index (UTCI).
    
    UTCI is an equivalent temperature that represents the thermal sensation
    a person experiences in any climate. It combines:
    - Air temperature (Ta)
    - Mean radiant temperature (Tmrt)
    - Wind speed
    - Relative humidity (RH)
    
    UTCI is more sophisticated than Heat Index and is designed for
    outdoor environments with varying radiation.
    
    Args:
        Ta: Air temperature in °C
        Tmrt: Mean radiant temperature in °C
        wind_speed: Wind speed in m/s
        RH: Relative humidity in % (0-100)
    
    Returns:
        (utci_value_celsius, stress_category_string)
    
    References:
        Bröde, P., et al. (2012). "The universal thermal climate index UTCI—
        A new biometeorological assessment of the thermal environment."
        International Journal of Climatology, 32(7), 1048-1060.
    """
    
    logger.debug(f"UTCI calc: Ta={Ta}°C, Tmrt={Tmrt}°C, WS={wind_speed}m/s, RH={RH}%")
    
    # Input validation
    if not -50 <= Ta <= 60:
        logger.warning(f"Air temperature {Ta}°C is outside typical range")
    if not -50 <= Tmrt <= 150:
        logger.warning(f"MRT {Tmrt}°C is outside typical range")
    if not 0 <= RH <= 100:
        logger.warning(f"Relative humidity {RH}% is outside valid range")
    if wind_speed < 0:
        logger.warning(f"Wind speed {wind_speed} m/s is negative")
    
    # Call pythermalcomfort library
    result = utci(
        tdb=Ta,
        tr=Tmrt,
        v=wind_speed*1000/3600,  # Converting from km/h to m/s
        rh=RH,
        round_output=False,
    )
    
    utci_value = float(result.utci)
    stress_category = result.stress_category
    
    logger.debug(f"UTCI result: {utci_value:.2f}°C ({stress_category})")
    return round(utci_value, 2), stress_category


# ---------------------------------------------------------
# MEAN RADIANT TEMPERATURE
# ---------------------------------------------------------

def calculate_mrt_standard(
    Tg: float,
    Ta: float,
    wind_speed: float,
) -> float:
    """
    Calculate Mean Radiant Temperature (MRT) for a standard 150-mm black sphere.
    
    MRT represents the radiant heat environment. It combines:
    - Direct solar radiation (absorbed by globe)
    - Diffuse sky radiation (absorbed by globe)
    - Reflected solar radiation from ground
    - Thermal radiation from surroundings
    
    Tg (globe temp) is converted to Tmrt using standard emissivity (0.95)
    and convection coefficients.
    
    Args:
        Tg: Black globe temperature in °C
        Ta: Air temperature in °C
        wind_speed: Wind speed in m/s
    
    Returns:
        Mean radiant temperature in °C
    
    References:
        ISO 7726: Ergonomics of the thermal environment — Instruments and methods
        for measuring environmental parameters
    """
    
    logger.debug(f"MRT calc: Tg={Tg}°C, Ta={Ta}°C, WS={wind_speed}m/s")
    
    # Convert wind speed: km/h to m/s for correlation
    wind_speed_corrected = wind_speed * 1000 / 3600
    
    # Stefan-Boltzmann constant
    sigma = 5.67e-8
    
    # Calculate MRT using the standard formulation
    Tmrt_kelvin_4 = (
        (Tg + 273.15) ** 4
        + 2.5e8 * (wind_speed_corrected ** 0.6) * (Tg - Ta)
    ) ** 0.25
    
    Tmrt = Tmrt_kelvin_4 - 273.15
    
    logger.debug(f"Mean radiant temperature: {Tmrt:.2f}°C")
    return Tmrt


# ---------------------------------------------------------
# SOLAR ZENITH ANGLE
# ---------------------------------------------------------

def calculate_solar_zenith(
    latitude: float,
    longitude: float,
    timestamp: str,
    timezone: str,
) -> float:
    """
    Calculate solar zenith angle using NREL SPA (Solar Position Algorithm).
    
    The zenith angle is the angle between the sun's rays and the vertical.
    - 0° = sun directly overhead (noon, equator)
    - 90° = sun at horizon (sunrise/sunset)
    - >90° = sun below horizon (nighttime)
    
    This is used to calculate black globe temperature and radiation effects.
    
    Args:
        latitude: Latitude in decimal degrees (North = positive, South = negative)
        longitude: Longitude in decimal degrees (East = positive, West = negative)
        timestamp: Date and time string, e.g. "2026-09-09 12:30:00"
        timezone: IANA timezone name, e.g. "Asia/Kolkata"
    
    Returns:
        Solar zenith angle in radians
    
    Raises:
        ValueError: If timestamp is invalid
        Exception: If pvlib calculation fails
    
    References:
        https://midcdmz.nrel.gov/spa/
    """
    
    logger.debug(f"Solar zenith calc: lat={latitude}, lon={longitude}, time={timestamp}, tz={timezone}")
    
    try:
        # Create timezone-aware timestamp
        time = pd.DatetimeIndex([pd.Timestamp(timestamp, tz=timezone)])
        
        # Calculate solar position using NREL SPA
        solar_position = pvlib.solarposition.get_solarposition(
            time=time,
            latitude=latitude,
            longitude=longitude,
            method="nrel_numpy"
        )
        
        # Extract zenith angle (degrees)
        zenith_deg = solar_position["zenith"].iloc[0]
        
        # Convert to radians
        z_rad = math.radians(zenith_deg)
        
        logger.debug(f"Solar zenith: {zenith_deg:.2f}° = {z_rad:.4f} rad")
        return float(z_rad)
    
    except KeyError as e:
        raise ValueError(f"Invalid timestamp format: {timestamp}. Expected 'YYYY-MM-DD HH:MM:SS'. Error: {e}")
    except Exception as e:
        logger.error(f"Error calculating solar zenith: {e}", exc_info=True)
        raise
