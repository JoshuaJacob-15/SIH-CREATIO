"""
main.py — Heat Stress Early Warning backend.

Uses risk_service.py, which pulls together weather data plus the full
WBGT / black-globe / MRT / UTCI calculations from thermal_index.py.

HOW TO RUN:
    pip install fastapi uvicorn httpx apscheduler pythermalcomfort pvlib pandas
    uvicorn main:app --reload

Try:
    http://127.0.0.1:8000/docs             <- interactive test UI, use this a lot
    http://127.0.0.1:8000/risk/current?city=Delhi
    http://127.0.0.1:8000/risk/all         <- risk for every demo city at once
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException

from weather_fetch import (
    weather_cache,
    refresh_all_locations,
    start_scheduler,
    LOCATIONS,
)

from risk_service import (
    calculate_risk,
    calculate_all_risks,
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
# Endpoints — these read from weather_cache and hand off to
# risk_service.py for the actual WBGT / black-globe / MRT / UTCI math.
# -----------------------------
@app.get("/risk/current")
def current_risk(city: str):
    if city not in weather_cache:
        raise HTTPException(
            status_code=404,
            detail=f"No data for '{city}'. Available: {list(LOCATIONS.keys())}",
        )
    try:
        return calculate_risk(city)
    except ValueError as e:
        # calculate_risk also validates city presence; keep this as a
        # belt-and-suspenders guard in case the cache changes mid-request.
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/risk/all")
def all_risk():
    return calculate_all_risks()


@app.get("/health")
def health_check():
    """Quick check that the server + cache are alive — handy for debugging."""
    return {"status": "ok", "cached_cities": list(weather_cache.keys())}