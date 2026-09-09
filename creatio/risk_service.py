"""
risk_service.py

Combines:
    - Weather data from weather_fetch.py
    - WBGT calculation from thermal_index.py
    - Heat Index calculation
    - UTCI calculation

This file contains the application's heat-risk business logic.

main.py should call this service instead of performing
the calculations itself.
"""

from typing import Optional

from weather_fetch import weather_cache, LOCATIONS

from services.thermal_index import (
    compute_wbgt,
    wbgt_category,
    heat_index,
    calculate_utci,
)


def calculate_risk(city: str) -> dict:
    """
    Calculate all available heat-stress indicators for a city.

    Parameters
    ----------
    city : str
        City name as stored in weather_cache.

    Returns
    -------
    dict
        Combined weather and heat-risk information.
    """

    # ---------------------------------------------------------
    # 1. Check whether weather data exists
    # ---------------------------------------------------------

    if city not in weather_cache:
        raise ValueError(
            f"No weather data available for '{city}'. "
            f"Available cities: {list(weather_cache.keys())}"
        )

    weather = weather_cache[city]

    # ---------------------------------------------------------
    # 2. Extract basic weather values
    # ---------------------------------------------------------

    temp_c = weather["temp_c"]
    rh = weather["rh_percent"]
    wind_speed = weather["wind_speed_ms"]

    # ---------------------------------------------------------
    # 3. Extract additional weather values
    #
    # These will exist after weather_fetch.py is updated.
    # ---------------------------------------------------------

    dew_point = weather.get("dew_point_c")
    tw = weather.get("wet_bulb_c")
    solar = weather.get("solar_w_m2")
    solar_dir = weather.get("direct_radiation_w_m2")
    solar_dif = weather.get("diffuse_radiation_w_m2")
    pressure = weather.get("pressure_hpa")

    # Solar zenith angle is not currently supplied by
    # weather_fetch.py.
    z_angle = weather.get("solar_zenith_rad")

    # ---------------------------------------------------------
    # 4. Calculate Heat Index
    # ---------------------------------------------------------

    hi = heat_index(
        temp_c=temp_c,
        rh=rh,
    )

    # ---------------------------------------------------------
    # 5. Calculate UTCI
    #
    # UTCI requires mean radiant temperature (Tmrt).
    #
    # We do NOT have a reliable Tmrt yet, so don't silently
    # substitute air temperature.
    # ---------------------------------------------------------

    utci_value: Optional[float] = None
    utci_category: Optional[str] = None

    tmrt = weather.get("mean_radiant_temperature_c")

    if tmrt is not None:
        utci_value, utci_category = calculate_utci(
            Ta=temp_c,
            Tmrt=tmrt,
            wind_speed=wind_speed,
            RH=rh,
        )

    # ---------------------------------------------------------
    # 6. Calculate WBGT
    #
    # The full WBGT calculation needs:
    #     wet bulb temperature
    #     dew point
    #     solar radiation
    #     direct radiation
    #     diffuse radiation
    #     solar zenith angle
    #     pressure
    #
    # If any of these are unavailable, WBGT is left as None.
    # ---------------------------------------------------------

    wbgt = None
    wbgt_risk = None

    required_wbgt_values = [
        tw,
        dew_point,
        solar,
        solar_dir,
        solar_dif,
        z_angle,
        pressure,
    ]

    if all(value is not None for value in required_wbgt_values):

        wbgt = compute_wbgt(
            temp_c=temp_c,
            tw=tw,
            dew_point=dew_point,
            rh=rh,
            wind_mh=wind_speed,
            solar=solar,
            solar_dir=solar_dir,
            solar_dif=solar_dif,
            z_angle=z_angle,
            pressure=pressure,
            outdoor=True,
        )

        wbgt_risk = wbgt_category(wbgt)

    # ---------------------------------------------------------
    # 7. Return combined result
    # ---------------------------------------------------------

    result = {
        "city": city,

        "weather": weather,

        "heat_index": {
            "value_c": hi,
        },

        "wbgt": {
            "value_c": wbgt,
            "category": wbgt_risk,
        },

        "utci": {
            "value_c": utci_value,
            "stress_category": utci_category,
        },
    }

    return result


def calculate_all_risks() -> dict:
    """
    Calculate heat-risk information for every city
    currently present in the weather cache.
    """

    results = {}

    for city in weather_cache:
        try:
            results[city] = calculate_risk(city)

        except Exception as e:
            results[city] = {
                "city": city,
                "error": str(e),
            }

    return results