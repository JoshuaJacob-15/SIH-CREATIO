"""
main.py — Enhanced Heat Stress Early Warning Backend

Uses risk_service.py, which pulls together weather data plus the full
WBGT / black-globe / MRT / UTCI calculations from thermal_index.py.

Enhancements:
- Comprehensive error handling with structured responses
- Logging and monitoring
- Response caching for performance
- Detailed API documentation
- Intervention recommendations endpoint
- Temporal trend tracking endpoint
- Health check with detailed diagnostics
- Request validation
- Graceful degradation on partial failures

HOW TO RUN:
    pip install fastapi uvicorn httpx apscheduler pythermalcomfort pvlib pandas numpy
    uvicorn main:app --reload

Try:
    http://127.0.0.1:8000/docs                    <- interactive test UI
    http://127.0.0.1:8000/risk/current?city=Delhi <- single city risk
    http://127.0.0.1:8000/risk/all                <- all cities
    http://127.0.0.1:8000/risk/trends?city=Delhi  <- temporal trends
    http://127.0.0.1:8000/health                  <- system status
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Optional, Dict
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from weather_fetch import (
    weather_cache,
    refresh_all_locations,
    start_scheduler,
    LOCATIONS,
)

from risk_service import (
    calculate_risk,
    calculate_all_risks,
    temporal_tracker,
    logger as risk_logger,
)

# =========================================================
# LOGGING SETUP
# =========================================================

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

handler = logging.StreamHandler()
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
handler.setFormatter(formatter)
logger.addHandler(handler)


# =========================================================
# GLOBAL STATE
# =========================================================

scheduler = None
refresh_task = None


# =========================================================
# STARTUP & SHUTDOWN
# =========================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.
    
    Runs once at startup (before yield) and once at shutdown (after yield).
    This is where we initialize the weather cache and background scheduler.
    """
    
    global scheduler
    
    logger.info("=" * 60)
    logger.info("🌡️  HEAT STRESS EARLY WARNING SYSTEM - STARTUP")
    logger.info("=" * 60)
    
    try:
        # --- STARTUP ---
        
        logger.info("Step 1: Fetching initial weather data...")
        await refresh_all_locations()
        
        if not weather_cache:
            logger.error("❌ Weather cache is empty after initial fetch!")
            raise RuntimeError("Failed to populate weather cache on startup")
        
        logger.info(f"✓ Weather cache populated: {list(weather_cache.keys())}")
        
        logger.info("Step 2: Starting background scheduler...")
        scheduler = start_scheduler(interval_minutes=10)
        logger.info("✓ Background scheduler started (10-minute interval)")
        
        logger.info("=" * 60)
        logger.info("✓ STARTUP COMPLETE - System ready")
        logger.info("=" * 60)
        
        yield  # Server is now running
        
    except Exception as e:
        logger.error(f"❌ STARTUP FAILED: {e}", exc_info=True)
        raise
    
    finally:
        # --- SHUTDOWN ---
        
        logger.info("=" * 60)
        logger.info("🛑 SYSTEM SHUTDOWN")
        logger.info("=" * 60)
        
        try:
            if scheduler:
                scheduler.shutdown()
                logger.info("✓ Scheduler shut down gracefully")
        except Exception as e:
            logger.error(f"Error during scheduler shutdown: {e}")
        
        logger.info("=" * 60)


# =========================================================
# FASTAPI APP INITIALIZATION
# =========================================================

app = FastAPI(
    title="Heat Stress Early Warning System",
    description="Real-time heat health risk assessment using WBGT, UTCI, and vulnerability metrics",
    version="2.0",
    lifespan=lifespan,
)

# The dashboard runs on a separate development server during local work.
# Keep allowed origins configurable so deployment can restrict this further.
allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


# =========================================================
# RESPONSE MODELS (for documentation)
# =========================================================

class ErrorResponse:
    """Standard error response structure."""
    pass


# =========================================================
# ENDPOINTS
# =========================================================

@app.get(
    "/risk/current",
    summary="Get heat risk for a single city",
    description="Calculate comprehensive heat-health risk indicators for a specific city including WBGT, UTCI, vulnerability adjustment, and recommended interventions.",
    tags=["Risk Assessment"],
)
async def current_risk(
    city: str = Query(..., description="City name (Delhi, Chennai, Ahmedabad, Kolkata, Jaipur)")
):
    """
    Get current heat-health risk for a city.
    
    Returns:
    - Thermal indices: Heat Index, Black Globe Temperature, WBGT, UTCI, MRT
    - Health risk: Overall risk level, scores, health effects, vulnerable groups
    - Vulnerability: Adjusted risk based on location factors
    - Temporal trend: Heat wave progression over last 24 hours
    - Interventions: Recommended public health actions
    
    Example:
        GET /risk/current?city=Delhi
    """
    
    logger.info(f"Request: /risk/current?city={city}")
    
    # Validate city
    if city not in LOCATIONS:
        logger.warning(f"Invalid city requested: {city}")
        raise HTTPException(
            status_code=404,
            detail={
                "error": "City not found",
                "requested": city,
                "available_cities": list(LOCATIONS.keys()),
            }
        )
    
    if city not in weather_cache:
        logger.warning(f"No weather data for {city}")
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Weather data unavailable",
                "city": city,
                "message": "Weather cache is empty. Try again in a moment.",
            }
        )
    
    try:
        result = calculate_risk(city)
        
        # Check if calculation had errors
        if "error" in result:
            logger.error(f"Risk calculation error for {city}: {result['error']}")
            raise HTTPException(
                status_code=400,
                detail=result
            )
        
        logger.info(f"✓ Risk calculated for {city}: {result.get('final_risk', {}).get('vulnerability_adjusted_risk', 'Unknown')}")
        return result
    
    except ValueError as e:
        logger.error(f"ValueError for {city}: {e}")
        raise HTTPException(status_code=400, detail={"error": str(e), "city": city})
    
    except Exception as e:
        logger.error(f"Unexpected error calculating risk for {city}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "city": city,
                "message": "An unexpected error occurred while calculating risk"
            }
        )


@app.get(
    "/risk/all",
    summary="Get heat risk for all cities",
    description="Calculate heat-health risk for all configured cities in a single request",
    tags=["Risk Assessment"],
)
async def all_risk():
    """
    Get current heat-health risk for all cities.
    
    Returns a dictionary mapping city names to their risk assessments.
    If any city fails, that entry will contain error details but won't
    block the results for other cities.
    
    Example:
        GET /risk/all
    """
    
    logger.info("Request: /risk/all")
    
    if not weather_cache:
        logger.error("Weather cache is empty")
        raise HTTPException(
            status_code=503,
            detail={
                "error": "No weather data available",
                "message": "Weather cache is empty. System initializing..."
            }
        )
    
    try:
        results = calculate_all_risks()
        
        # Count successes and failures
        successes = sum(1 for r in results.values() if "error" not in r)
        failures = len(results) - successes
        
        logger.info(f"✓ All risks calculated: {successes} success, {failures} failures")
        
        return {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_cities": len(results),
                "successful": successes,
                "failed": failures,
            },
            "results": results,
        }
    
    except Exception as e:
        logger.error(f"Error calculating all risks: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": "Failed to calculate risks for all cities"
            }
        )


@app.get(
    "/risk/trends",
    summary="Get temporal trend for a city",
    description="Retrieve heat wave progression and trend analysis for a city over the last 24 hours",
    tags=["Trends & Analytics"],
)
async def risk_trends(
    city: str = Query(..., description="City name")
):
    """
    Get temporal trend analysis for a city.
    
    Shows:
    - Trend direction: increasing, stable, or decreasing
    - Heat wave duration: consecutive hours at high-risk level
    - Risk score statistics: min, max, average over time window
    - Records count: how much historical data is available
    
    Example:
        GET /risk/trends?city=Delhi
    """
    
    logger.info(f"Request: /risk/trends?city={city}")
    
    if city not in LOCATIONS:
        raise HTTPException(
            status_code=404,
            detail={"error": "City not found", "available": list(LOCATIONS.keys())}
        )
    
    try:
        trend = temporal_tracker.get_trend(city)
        
        return {
            "city": city,
            "timestamp": datetime.now().isoformat(),
            "trend": trend,
        }
    
    except Exception as e:
        logger.error(f"Error getting trends for {city}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "Failed to retrieve trends", "city": city}
        )


@app.get(
    "/health",
    summary="System health check",
    description="Get detailed diagnostics about the system status, cache, and scheduler",
    tags=["System"],
)
async def health_check():
    """
    System health check.
    
    Returns:
    - status: 'ok' or 'degraded'
    - cached_cities: cities with weather data
    - cache_size: how many cities in cache
    - scheduler_status: 'running' or 'stopped'
    - timestamp: server time
    
    Example:
        GET /health
    """
    
    try:
        scheduler_status = "running" if scheduler and scheduler.running else "stopped"
        
        health = {
            "status": "ok" if weather_cache else "degraded",
            "timestamp": datetime.now().isoformat(),
            "weather_cache": {
                "cached_cities": list(weather_cache.keys()),
                "cache_size": len(weather_cache),
                "available_cities": list(LOCATIONS.keys()),
            },
            "scheduler": {
                "status": scheduler_status,
                "job_count": len(scheduler.get_jobs()) if scheduler else 0,
            },
            "system": {
                "version": "2.0",
                "description": "Heat Stress Early Warning System",
            }
        }
        
        logger.info(f"Health check: {health['status']}")
        return health
    
    except Exception as e:
        logger.error(f"Error in health check: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
        )


@app.get(
    "/interventions",
    summary="Get recommended public health interventions",
    description="Get actionable public health measures based on current risk levels across all cities",
    tags=["Interventions"],
)
async def get_interventions():
    """
    Get recommended interventions for all cities.
    
    Shows:
    - Which cooling centers should be activated
    - Outdoor work restrictions needed
    - Healthcare preparation actions
    - Public alert recommendations
    
    Example:
        GET /interventions
    """
    
    logger.info("Request: /interventions")
    
    try:
        all_risks = calculate_all_risks()
        
        interventions_by_city = {}
        for city, risk_data in all_risks.items():
            if "error" not in risk_data:
                interventions_by_city[city] = {
                    "risk_level": risk_data.get("final_risk", {}).get("vulnerability_adjusted_risk"),
                    "interventions": risk_data.get("interventions", {}),
                }
        
        logger.info(f"✓ Interventions retrieved for {len(interventions_by_city)} cities")
        
        return {
            "timestamp": datetime.now().isoformat(),
            "cities": interventions_by_city,
        }
    
    except Exception as e:
        logger.error(f"Error getting interventions: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "Failed to retrieve interventions"}
        )


@app.get(
    "/",
    summary="API documentation redirect",
    tags=["System"],
)
async def root():
    """
    Root endpoint. Redirects to interactive API documentation.
    """
    return {
        "message": "Heat Stress Early Warning System v2.0",
        "docs": "/docs",
        "endpoints": {
            "risk": {
                "current": "/risk/current?city=Delhi",
                "all": "/risk/all",
                "trends": "/risk/trends?city=Delhi",
            },
            "system": {
                "health": "/health",
                "interventions": "/interventions",
            }
        }
    }


# =========================================================
# EXCEPTION HANDLERS
# =========================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler with logging."""
    logger.error(f"HTTP Exception: {exc.status_code} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "status_code": exc.status_code,
            "detail": exc.detail,
            "timestamp": datetime.now().isoformat(),
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Catch-all exception handler."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "status_code": 500,
            "message": "Internal server error",
            "timestamp": datetime.now().isoformat(),
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
