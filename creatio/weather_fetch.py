"""
weather_fetch.py - Enhanced

Fetch weather data from Open-Meteo API with improved error handling,
caching, and background refresh scheduling.

Enhancements:
- Better error messages and logging
- Timeout configuration
- Retry logic
- Data validation
- Structured weather dictionary with documentation
"""

import logging
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import datetime
import asyncio
from typing import Dict, Optional, Tuple

# Setup logging
logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# LOCATION DATA
# ---------------------------------------------------------

LOCATIONS: Dict[str, Tuple[float, float]] = {
    "Delhi": (28.61, 77.21),
    "Chennai": (13.08, 80.27),
    "Ahmedabad": (23.02, 72.57),
    "Kolkata": (22.57, 88.36),
    "Jaipur": (26.91, 75.79),
}

# In-memory weather cache
weather_cache: Dict[str, dict] = {}

# Configuration
WEATHER_API_TIMEOUT = 10  # seconds
WEATHER_API_RETRIES = 3
WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"


# ---------------------------------------------------------
# UTILITY FUNCTIONS
# ---------------------------------------------------------

def get_formatted_timestamp() -> str:
    """
    Get current local date and time as ISO format string.
    
    Returns:
        String in format "YYYY-MM-DD HH:MM:SS"
    """
    current_time = datetime.datetime.now()
    formatted_timestamp = current_time.strftime("%Y-%m-%d %H:%M:%S")
    logger.debug(f"Generated timestamp: {formatted_timestamp}")
    return formatted_timestamp


# ---------------------------------------------------------
# MAIN WEATHER FETCH
# ---------------------------------------------------------

async def fetch_weather_for(lat: float, lon: float, retries: int = WEATHER_API_RETRIES) -> Optional[dict]:
    """
    Fetch current weather for a location from Open-Meteo API.
    
    The Open-Meteo API provides both "current" and "hourly" data:
    - "current" fields come back as single values (one number)
    - "hourly" fields come back as LISTS (one value per hour in forecast window)
    
    Some variables (wet bulb temp, direct/diffuse radiation) are only
    reliably available via "hourly", so we request both and pull index [1]
    from the hourly lists (current hour + 1 for alignment).
    
    Weather dictionary structure:
    {
        "temp_c": float,                          # Air temperature in °C
        "rh_percent": float,                      # Relative humidity in %
        "wind_speed": float,                      # Wind speed in m/s
        "dew_point": float,                       # Dew point in °C
        "pressure_hpa": float,                    # Surface pressure in hPa
        "solar_radiation": float,                 # Shortwave radiation in W/m²
        "wet_bulb": float or None,                # Wet bulb temperature in °C
        "direct_radiation": float or None,        # Direct radiation in W/m²
        "diffuse_radiation": float or None,       # Diffuse radiation in W/m²
        "direct_normal_irradiance": float or None,# Direct normal irradiance in W/m²
        "time_stamp": str,                        # Timestamp in "YYYY-MM-DD HH:MM:SS"
    }
    
    Args:
        lat: Latitude in decimal degrees
        lon: Longitude in decimal degrees
        retries: Number of retry attempts on network failure
    
    Returns:
        Weather dictionary, or None if all retries fail
    
    Raises:
        httpx.RequestError: If all retries are exhausted
    """
    
    logger.info(f"Fetching weather for lat={lat}, lon={lon}")
    
    # Request parameters
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,dew_point_2m,surface_pressure,shortwave_radiation",
        "hourly": "wet_bulb_temperature_2m,direct_radiation,diffuse_radiation,direct_normal_irradiance",
        "forecast_days": 1,
    }
    
    last_error = None
    
    for attempt in range(retries):
        try:
            logger.debug(f"Weather API call attempt {attempt + 1}/{retries}")
            
            async with httpx.AsyncClient(timeout=WEATHER_API_TIMEOUT) as client:
                response = await client.get(WEATHER_API_URL, params=params)
                response.raise_for_status()  # Raise on 4xx/5xx
                payload = response.json()
            
            logger.info(f"✓ Weather data received for lat={lat}, lon={lon}")
            
            # Extract current data
            data = payload.get("current", {})
            hourly = payload.get("hourly", {})
            
            # Extract hourly data (use index 1 for current+1 hour)
            wet_bulb_list = hourly.get("wet_bulb_temperature_2m", [])
            direct_rad_list = hourly.get("direct_radiation", [])
            diffuse_rad_list = hourly.get("diffuse_radiation", [])
            dni_list = hourly.get("direct_normal_irradiance", [])
            
            # Safely get index 1, fallback to None
            wet_bulb = wet_bulb_list[1] if len(wet_bulb_list) > 1 else None
            direct_rad = direct_rad_list[1] if len(direct_rad_list) > 1 else None
            diffuse_rad = diffuse_rad_list[1] if len(diffuse_rad_list) > 1 else None
            dni = dni_list[1] if len(dni_list) > 1 else None
            
            # Validate critical fields
            temp = data.get("temperature_2m")
            rh = data.get("relative_humidity_2m")
            wind = data.get("wind_speed_10m")
            
            if temp is None or rh is None or wind is None:
                raise ValueError(f"Missing critical weather fields: T={temp}, RH={rh}, WS={wind}")
            
            # Build weather dict
            weather_dict = {
                "temp_c": float(temp),
                "rh_percent": float(rh),
                "wind_speed": float(wind),
                "dew_point": float(data.get("dew_point_2m", 0)) if data.get("dew_point_2m") else None,
                "pressure_hpa": float(data.get("surface_pressure", 1013)) if data.get("surface_pressure") else None,
                "solar_radiation": float(data.get("shortwave_radiation", 0)) if data.get("shortwave_radiation") else None,
                "wet_bulb": float(wet_bulb) if wet_bulb is not None else None,
                "direct_radiation": float(direct_rad) if direct_rad is not None else None,
                "diffuse_radiation": float(diffuse_rad) if diffuse_rad is not None else None,
                "direct_normal_irradiance": float(dni) if dni is not None else None,
                "time_stamp": get_formatted_timestamp(),
            }
            
            logger.debug(f"Weather dict: {weather_dict}")
            return weather_dict
        
        except httpx.TimeoutException as e:
            last_error = e
            logger.warning(f"Timeout on attempt {attempt + 1}/{retries}: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                continue
        
        except httpx.RequestError as e:
            last_error = e
            logger.warning(f"Request error on attempt {attempt + 1}/{retries}: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)
                continue
        
        except ValueError as e:
            logger.error(f"Invalid weather data: {e}")
            return None
        
        except Exception as e:
            last_error = e
            logger.error(f"Unexpected error on attempt {attempt + 1}/{retries}: {e}", exc_info=True)
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)
                continue
    
    # All retries exhausted
    logger.error(f"Failed to fetch weather after {retries} retries: {last_error}")
    return None


# ---------------------------------------------------------
# BACKGROUND REFRESH
# ---------------------------------------------------------

async def refresh_all_locations() -> None:
    """
    Refresh weather data for all configured locations.
    
    This function:
    1. Loops through every city in LOCATIONS
    2. Fetches fresh weather from API
    3. Updates weather_cache
    4. Logs failures without crashing
    
    Called periodically by the scheduler in background.
    """
    
    logger.info("=== Starting weather cache refresh ===")
    success_count = 0
    failure_count = 0
    
    for city, (lat, lon) in LOCATIONS.items():
        try:
            logger.debug(f"Refreshing weather for {city}")
            weather_data = await fetch_weather_for(lat, lon)
            
            if weather_data:
                weather_cache[city] = weather_data
                logger.info(f"✓ Updated cache for {city}")
                success_count += 1
            else:
                logger.warning(f"✗ No weather data returned for {city}")
                failure_count += 1
        
        except Exception as e:
            logger.error(f"✗ Failed to refresh weather for {city}: {e}", exc_info=True)
            failure_count += 1
    
    logger.info(f"Weather cache refresh complete: {success_count} success, {failure_count} failures")
    logger.debug(f"Cache state: {list(weather_cache.keys())}")


def start_scheduler(interval_minutes: int = 10) -> AsyncIOScheduler:
    """
    Start background scheduler to periodically refresh weather data.
    
    The scheduler runs refresh_all_locations() in the background without
    blocking the main API from handling requests.
    
    Args:
        interval_minutes: How often to refresh (default 10 minutes)
    
    Returns:
        AsyncIOScheduler instance (can be used to stop/pause the scheduler)
    """
    
    logger.info(f"Starting weather scheduler: refresh every {interval_minutes} minutes")
    
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        refresh_all_locations,
        "interval",
        minutes=interval_minutes,
        id="weather_refresh",
        name="Weather cache refresh",
    )
    
    try:
        scheduler.start()
        logger.info("✓ Scheduler started successfully")
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}", exc_info=True)
        raise
    
    return scheduler
