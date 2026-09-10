"""
risk_service.py

Combines:
    - Weather data from weather_fetch.py
    - Black Globe Temperature
    - WBGT calculation
    - Heat Index calculation
    - Mean Radiant Temperature
    - UTCI calculation
"""

from typing import Optional

from weather_fetch import weather_cache

from services.thermal_index import (
    compute_wbgt,
    black_globe_temperature,
    wbgt_category,
    heat_index,
    calculate_utci,
    calculate_mrt_standard,
)


def calculate_risk(city: str) -> dict:
    """
    Calculate all heat-stress indicators for a city.
    """

    # ---------------------------------------------------------
    # 1. Check weather data
    # ---------------------------------------------------------

    if city not in weather_cache:
        raise ValueError(
            f"No weather data available for '{city}'. "
            f"Available cities: {list(weather_cache.keys())}"
        )

    weather = weather_cache[city]

    # ---------------------------------------------------------
    # 2. Basic weather values
    # ---------------------------------------------------------

    temp_c = weather["temp_c"]
    rh = weather["rh_percent"]
    wind_speed = weather["wind_speed"]

    # ---------------------------------------------------------
    # 3. Additional weather values
    # ---------------------------------------------------------

    dew_point = weather.get("dew_point")
    tw = weather.get("wet_bulb")

    solar = weather.get("direct_normal_irradiance")
    solar_dir = weather.get("direct_radiation")
    solar_dif = weather.get("diffuse_radiation")

    pressure = weather.get("pressure_hpa")
    z_angle = weather.get("solar_zenith_rad")

    # ---------------------------------------------------------
    # 4. Heat Index
    # ---------------------------------------------------------

    hi = heat_index(
        temp_c=temp_c,
        rh=rh,
    )

    # ---------------------------------------------------------
    # 5. Black Globe Temperature
    #
    # Tg is required for:
    #     - WBGT
    #     - Mean Radiant Temperature
    #     - UTCI
    # ---------------------------------------------------------

    globe_temperature: Optional[float] = None

    required_globe_values = [
        dew_point,
        solar,
        solar_dir,
        solar_dif,
        z_angle,
        pressure,
    ]

    if all(value is not None for value in required_globe_values):

        globe_temperature = black_globe_temperature(
            u=wind_speed,
            Ta=temp_c,
            Td=dew_point,
            S=solar,
            fdb=solar_dir,
            fdif=solar_dif,
            z=z_angle,
            P=pressure,
        )

        globe_temperature = round(globe_temperature, 2)

    # ---------------------------------------------------------
    # 6. WBGT
    #
    # Outdoor WBGT:
    #
    # WBGT = 0.7 Tw + 0.2 Tg + 0.1 Ta
    #
    # Therefore both wet-bulb temperature and
    # black-globe temperature are required.
    # ---------------------------------------------------------

    wbgt: Optional[float] = None
    wbgt_risk: Optional[str] = None

    if tw is not None and globe_temperature is not None:

        wbgt = compute_wbgt(
            temp_c=temp_c,
            tw=tw,
            tg=globe_temperature,
            outdoor=True,
        )

        wbgt_risk = wbgt_category(wbgt)

    # ---------------------------------------------------------
    # 7. Mean Radiant Temperature
    #
    # Tmrt is calculated from:
    #     - Black globe temperature
    #     - Air temperature
    #     - Wind speed
    #
    # Tmrt is then used by UTCI.
    # ---------------------------------------------------------

    tmrt: Optional[float] = None

    if globe_temperature is not None:

        tmrt = calculate_mrt_standard(
            Tg=globe_temperature,
            Ta=temp_c,
            wind_speed=wind_speed,
        )

        tmrt = round(tmrt, 2)

    # ---------------------------------------------------------
    # 8. UTCI
    #
    # UTCI requires:
    #     Ta
    #     Tmrt
    #     Wind speed
    #     Relative humidity
    # ---------------------------------------------------------

    utci_value: Optional[float] = None
    utci_category: Optional[str] = None

    if tmrt is not None:

        utci_value, utci_category = calculate_utci(
            Ta=temp_c,
            Tmrt=tmrt,
            wind_speed=wind_speed,
            RH=rh,
        )

        utci_value = round(utci_value, 2)

    # ---------------------------------------------------------
    # 9. Final result
    # ---------------------------------------------------------

    return {
        "city": city,

        "weather": weather,

        "heat_index": {
            "value_c": hi,
        },

        "black_globe_temperature": {
            "value_c": globe_temperature,
        },

        "wbgt": {
            "value_c": wbgt,
            "category": wbgt_risk,
        },

        "mean_radiant_temperature": {
            "value_c": tmrt,
        },

        "utci": {
            "value_c": utci_value,
            "stress_category": utci_category,
        },
    }


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
