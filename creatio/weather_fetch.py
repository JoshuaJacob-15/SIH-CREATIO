

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# -----------------------------
# Your demo locations, hardcoded for now (city name -> lat/lon)
# -----------------------------
LOCATIONS = {
    "Delhi": (28.61, 77.21),
    "Chennai": (13.08, 80.27),
    "Ahmedabad": (23.02, 72.57),
    "Kolkata": (22.57, 88.36),
    "Jaipur": (26.91, 75.79),
}


weather_cache: dict = {}
async def fetch_weather_for(lat: float, lon: float) -> dict:
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,dew_point_2m,surface_pressure,shortwave_radiation",
        "hourly": "wet_bulb_temperature_2m,direct_radiation,diffuse_radiation,direct_normal_irradiance",
        "forecast_days": 1,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(url, params=params)
        payload = response.json()  
 
    data = payload["current"]
    hourly = payload["hourly"]

    return {
        "temp_c": data["temperature_2m"],
        "rh_percent": data["relative_humidity_2m"],
        "wind_speed": data["wind_speed_10m"],
        "dew_point": data["dew_point_2m"],
        "pressure_hpa": data["surface_pressure"],
        "solar_radiation": data["shortwave_radiation"],
 
        # hourly fields — index 0 = current hour
        "wet_bulb": hourly["wet_bulb_temperature_2m"][0],
        "direct_radiation": hourly["direct_radiation"][0],
        "diffuse_radiation": hourly["diffuse_radiation"][0],
        "direct_normal_irradiance": hourly["direct_normal_irradiance"][0],
 
    }
 
 


async def refresh_all_locations():
    """
    This is the function that runs on a timer.
    It loops through every demo city, fetches fresh weather,
    and overwrites the cache. If you print here, you'll see it
    firing in your terminal every N minutes.
    """
    print("Refreshing weather cache...")
    for city, (lat, lon) in LOCATIONS.items():
        try:
            weather_cache[city] = await fetch_weather_for(lat, lon)
        except Exception as e:
            # Don't let one failed city crash the whole refresh
            print(f"Failed to fetch weather for {city}: {e}")
    print("Weather cache updated:", weather_cache)


def start_scheduler():
    """
    Call this once when the app starts. It schedules refresh_all_locations
    to run immediately, then every 10 minutes forever, in the background,
    without blocking your API from handling requests.
    """
    scheduler = AsyncIOScheduler()
    scheduler.add_job(refresh_all_locations, "interval", minutes=10)
    scheduler.start()
    return scheduler
