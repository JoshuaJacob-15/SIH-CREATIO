

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import datetime
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

def get_formatted_timestamp():
    # Fetch the current local date and time
    current_time = datetime.datetime.now()
    
    # Format the datetime object as a string
    formatted_timestamp = current_time.strftime("%Y-%m-%d %H:%M:%S")
    
    return formatted_timestamp
ts=get_formatted_timestamp()
async def fetch_weather_for(lat: float, lon: float) -> dict:
    """
    Fetch current weather for one location from Open-Meteo.
 
    NOTE on current vs hourly:
    - "current" fields come back as single values (one number).
    - "hourly" fields come back as LISTS (one value per hour in the forecast
      window). Some variables — wet bulb temp, direct/diffuse radiation —
      are only reliably available via "hourly", so we request both and pull
      index [0] from the hourly lists, which is the current hour.
    """
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
        payload = response.json()  # parse ONCE, reuse below
 
    data = payload["current"]
    hourly = payload["hourly"]
 
 
    wet_bulb_list = hourly.get("wet_bulb_temperature_2m")
    direct_rad_list = hourly.get("direct_radiation")
    diffuse_rad_list = hourly.get("diffuse_radiation")
    dni_list = hourly.get("direct_normal_irradiance")
 
    return {
        "temp_c": data["temperature_2m"],
        "rh_percent": data["relative_humidity_2m"],
        "wind_speed": data["wind_speed_10m"],
        "dew_point": data["dew_point_2m"],
        "pressure_hpa": data["surface_pressure"],
        "solar_radiation": data["shortwave_radiation"],
 
        "wet_bulb": wet_bulb_list[1] if wet_bulb_list else None,
        "direct_radiation": direct_rad_list[1] if direct_rad_list else None,
        "diffuse_radiation": diffuse_rad_list[1] if diffuse_rad_list else None,
        "direct_normal_irradiance": dni_list[1] if dni_list else None,
        "time_stamp": ts,
 
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
