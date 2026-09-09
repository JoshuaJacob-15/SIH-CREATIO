"""
main.py — Heat Stress Early Warning backend, now with auto-updating weather.

HOW TO RUN:
    pip install fastapi uvicorn httpx apscheduler
    uvicorn main:app --reload

Try:
    http://127.0.0.1:8000/docs             <- interactive test UI, use this a lot
    http://127.0.0.1:8000/risk/current?city=Delhi
    http://127.0.0.1:8000/risk/all         <- risk for every demo city at once
"""

import math
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException

from weather_fetch import (
    weather_cache,
    refresh_all_locations,
    start_scheduler,
    LOCATIONS,
)


# -----------------------------
# This runs once when the server starts, and once when it shuts down.
# "lifespan" is FastAPI's way of doing startup/shutdown logic
# (similar in spirit to an @PostConstruct in Spring Boot).
# -----------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP: do one fetch immediately so the cache isn't empty
    # while we wait for the first scheduled run
    await refresh_all_locations()
    scheduler = start_scheduler()
    yield
    # SHUTDOWN (not critical for a hackathon demo, but good practice)
    scheduler.shutdown()


app = FastAPI(lifespan=lifespan)


# -----------------------------
# Thermal stress calculation — unchanged, pure math, no dependencies
# -----------------------------
def compute_wbgt_simplified(temp_c: float, rh_percent: float) -> float:
    vapor_pressure = (rh_percent / 100) * 6.105 * math.exp(
        17.27 * temp_c / (237.7 + temp_c)
    )
    wbgt = 0.567 * temp_c + 0.393 * vapor_pressure + 3.94
    return round(wbgt, 2)


def classify_risk(wbgt: float) -> str:
    if wbgt < 28:
        return "green"
    elif wbgt < 30:
        return "yellow"
    elif wbgt < 32:
        return "orange"
    elif wbgt < 35:
        return "red"
    return "black"


# -----------------------------
# Endpoints — these now read from weather_cache instead of
# calling the external API directly. Instant response, always
# reflects the most recent scheduled refresh.
# -----------------------------
@app.get("/risk/current")
def current_risk(city: str):
    if city not in weather_cache:
        raise HTTPException(
            status_code=404,
            detail=f"No data for '{city}'. Available: {list(LOCATIONS.keys())}",
        )
    weather = weather_cache[city]
    wbgt = compute_wbgt_simplified(weather["temp_c"], weather["rh_percent"])
    return {
        "city": city,
        "weather": weather,
        "wbgt": wbgt,
        "risk_tier": classify_risk(wbgt),
    }


@app.get("/risk/all")
def all_risk():
    results = {}
    for city, weather in weather_cache.items():
        wbgt = compute_wbgt_simplified(weather["temp_c"], weather["rh_percent"])
        results[city] = {
            "weather": weather,
            "wbgt": wbgt,
            "risk_tier": classify_risk(wbgt),
        }
    return results


@app.get("/health")
def health_check():
    """Quick check that the server + cache are alive — handy for debugging."""
    return {"status": "ok", "cached_cities": list(weather_cache.keys())}
