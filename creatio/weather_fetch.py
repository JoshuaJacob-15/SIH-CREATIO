"""
weather_fetch.py — pulls live weather data and keeps it updated automatically
using a background scheduler.

CONCEPT (mapped to what you already know):
    This is like a background thread in Java that wakes up every N minutes,
    does work, and updates a shared variable. Here, APScheduler handles the
    "wake up every N minutes" part, and we store results in a plain Python
    dict acting as an in-memory cache that your API endpoints read from.

WHY NOT just fetch on every request?
    - Weather doesn't change second to second, no need to hit the external
      API that often
    - Faster responses for your demo (reading a dict is instant vs. waiting
      on a network call)
    - Open-Meteo's free tier has a daily call limit (10,000/day) — polling
      every 10 min instead of every request keeps you well under it

pip install apscheduler httpx
"""

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

# -----------------------------
# The in-memory cache. This is a plain dict that gets overwritten
# every time the scheduled job runs. Endpoints read from THIS,
# never call the external API directly.
# -----------------------------
weather_cache: dict = {}


async def fetch_weather_for(lat: float, lon: float) -> dict:
    """Fetch current weather for one location from Open-Meteo."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(url, params=params)
        data = response.json()["current"]
    return {
        "temp_c": data["temperature_2m"],
        "rh_percent": data["relative_humidity_2m"],
        "wind_speed": data["wind_speed_10m"],
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
