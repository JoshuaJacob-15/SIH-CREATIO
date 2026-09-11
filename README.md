# Creatio Backend — Heat Stress Early Warning System

Backend service for the **SIH-CREATIO** project. It provides a FastAPI API for real-time heat-stress assessment using meteorological data from Open-Meteo and combines thermal indices with location vulnerability factors to produce actionable heat-health risk information.

## Features

* Fetches weather and solar-radiation data from **Open-Meteo**.
* Calculates **Heat Index**, **Black Globe Temperature**, **WBGT**, **Mean Radiant Temperature (MRT)**, and **UTCI**.
* Calculates a human-health heat-risk score using environmental indicators.
* Applies city-level vulnerability factors to adjust the final risk level.
* Tracks short-term risk trends using an in-memory 24-hour history.
* Provides intervention recommendations such as cooling-centre activation, outdoor-work restrictions, public alerts, and healthcare preparedness.
* Includes request validation, structured logging, caching, retries, and a health-check endpoint.

The current backend is implemented in `main.py`, `risk_service.py`, `thermal_index.py`, `weather_fetch.py`, and `config.py`. The repository currently configures five Indian cities: Delhi, Chennai, Ahmedabad, Kolkata, and Jaipur.

## Architecture

```text
                         ┌────────────────────┐
                         │     Open-Meteo      │
                         │ Weather + Solar    │
                         └─────────┬──────────┘
                                   │
                                   ▼
                         ┌────────────────────┐
                         │  weather_fetch.py  │
                         │ Fetch / cache data │
                         │ Retries / scheduler│
                         └─────────┬──────────┘
                                   │
                                   ▼
                         ┌────────────────────┐
                         │  risk_service.py   │
                         │ Risk orchestration │
                         └─────────┬──────────┘
                                   │
                 ┌─────────────────┼─────────────────┐
                 ▼                 ▼                 ▼
        ┌────────────────┐ ┌───────────────┐ ┌────────────────┐
        │ thermal_index  │ │ Vulnerability │ │ Trend Tracker  │
        │ WBGT / Tg /    │ │ Adjustment    │ │ Last 24 records│
        │ MRT / UTCI / HI│ │               │ │                │
        └───────┬────────┘ └───────┬───────┘ └────────────────┘
                │                  │
                └─────────┬────────┘
                          ▼
                ┌─────────────────────┐
                │ FastAPI (`main.py`) │
                │ REST endpoints       │
                └─────────────────────┘
```

The backend documents the calculation pipeline as:

```text
Weather
  -> Solar Zenith Angle
  -> Black Globe Temperature
      -> WBGT
      -> MRT -> UTCI
  -> Human Health Risk
  -> Vulnerability-Adjusted Risk
  -> Temporal Trend / Interventions
```

## Project Structure

```text
creatio/
├── config.py            # Environment/configuration setup
├── main.py              # FastAPI application and API routes
├── risk_service.py      # Risk scoring, vulnerability, trends, interventions
├── thermal_index.py     # WBGT, Tg, MRT, UTCI, heat index, solar geometry
├── weather_fetch.py     # Open-Meteo client, cache, refresh scheduler
└── requirements.txt     # Python dependencies
```

## Requirements

Recommended Python version for this backend: **Python 3.11.x**.

The repository pins:

* `pythermalcomfort==2.4.0`
* `pvlib==0.9.5`
* `pandas==2.0.3`
* `numpy==1.24.3`
* `fastapi==0.104.1`
* `uvicorn==0.24.0`
* `httpx==0.25.0`
* `apscheduler==3.10.4`
* `python-dateutil==2.8.2`

## Installation

From the `creatio` directory:

### Windows

```powershell
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Linux / macOS

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Run the API

```bash
uvicorn main:app --reload
```

The server runs on:

```text
http://127.0.0.1:8000
```

Interactive Swagger documentation:

```text
http://127.0.0.1:8000/docs
```

OpenAPI schema:

```text
http://127.0.0.1:8000/openapi.json
```

The backend also supports direct startup through `python main.py`, which starts Uvicorn on port 8000.

## API Endpoints

### `GET /`

Returns the backend name, version, and available endpoints.

```text
GET /
```

### `GET /risk/current`

Returns the current heat-health risk assessment for one configured city.

```text
GET /risk/current?city=Delhi
```

The endpoint returns thermal indicators, health-risk information, vulnerability adjustment, trend information, and interventions.

Supported cities:

```text
Delhi
Chennai
Ahmedabad
Kolkata
Jaipur
```

### `GET /risk/all`

Calculates the current risk for all configured cities.

```text
GET /risk/all
```

The response contains an overall timestamp, success/failure counts, and per-city results.

### `GET /risk/trends`

Returns recent heat-risk trend information for a city.

```text
GET /risk/trends?city=Delhi
```

The temporal tracker maintains up to 24 records per city and reports trend direction, score statistics, and consecutive high-risk periods.

### `GET /interventions`

Returns recommended public-health interventions based on current risk levels.

```text
GET /interventions
```

Possible interventions include cooling-centre activation, outdoor-work schedule changes, healthcare preparation, public alerts, and emergency response.

### `GET /health`

Returns service diagnostics including weather-cache status, cached cities, scheduler status, job count, and server timestamp.

```text
GET /health
```

## Data Source

The backend uses the Open-Meteo forecast API:

```text
https://api.open-meteo.com/v1/forecast
```

The weather module requests current values for:

* 2 m air temperature
* 2 m relative humidity
* 10 m wind speed
* 2 m dew point
* surface pressure
* shortwave radiation

It also requests hourly values for wet-bulb temperature, direct radiation, diffuse radiation, and direct normal irradiance.

## Thermal Indices

`thermal_index.py` contains the project's thermal calculations:

* **WBGT** — combines wet-bulb, globe, and air temperature.
* **Black Globe Temperature** — estimates globe temperature from environmental and radiation inputs.
* **Mean Radiant Temperature (MRT)** — estimates radiant conditions from globe temperature.
* **UTCI** — calculated through `pythermalcomfort`.
* **Heat Index** — computes apparent temperature from air temperature and relative humidity.
* **Solar Zenith Angle** — calculated using `pvlib` and the NREL SPA method.

The thermal module explicitly accepts wind speed for UTCI in m/s and calculates solar zenith from a timezone-aware timestamp.

## Risk Assessment

The risk service combines weather and thermal indicators into a human-health risk assessment and then applies location vulnerability factors.

The current vulnerability configuration includes:

* elderly population share
* informal housing share
* outdoor-worker share
* green-cover share
* population density
* healthcare capacity

The vulnerability adjustment can shift the risk upward according to the configured vulnerability score.

## Caching and Refresh

Weather data are maintained in an in-memory cache. During application startup, the backend performs an initial weather refresh and then starts a background scheduler configured for a **10-minute** refresh interval. Risk results use an in-memory cache with a **5-minute TTL**.

## CORS

By default, the application allows:

```text
http://localhost:5173
http://127.0.0.1:5173
```

CORS origins can be overridden through the `CORS_ORIGINS` environment variable.

Example:

```powershell
$env:CORS_ORIGINS="http://localhost:5173,https://your-frontend.example"
uvicorn main:app --reload
```

## Example Request Flow

```text
GET /risk/current?city=Delhi
        │
        ▼
Weather cache
        │
        ▼
Solar position + thermal calculations
        │
        ├── Heat Index
        ├── Black Globe Temperature
        ├── WBGT
        ├── MRT
        └── UTCI
        │
        ▼
Human-health risk score
        │
        ▼
Vulnerability adjustment
        │
        ▼
Trend + recommended interventions
        │
        ▼
JSON response
```

## Development Notes

### Logging

The backend uses Python's `logging` module for startup, weather-fetch, calculation, cache, scheduler, and API diagnostics.

### Error Handling

The API includes structured HTTP errors and a catch-all exception handler. Weather requests use retries with exponential backoff for transient request failures.

### Extending to More Cities

Add the city and coordinates to `LOCATIONS` in `weather_fetch.py`:

```python
LOCATIONS = {
    "Delhi": (28.61, 77.21),
    "Chennai": (13.08, 80.27),
    "Ahmedabad": (23.02, 72.57),
    "Kolkata": (22.57, 88.36),
    "Jaipur": (26.91, 75.79),
    "Mumbai": (19.0760, 72.8777),
}
```

If vulnerability-aware scoring is required, also add the corresponding vulnerability factors and timezone configuration in `risk_service.py`.

## Production Considerations

This backend is currently structured for local development and hackathon demonstration. Before production deployment, consider:

* moving in-memory caches to a shared datastore for multiple server instances;
* replacing development `--reload` mode;
* restricting CORS to the deployed frontend;
* adding authentication and authorization where required;
* persisting trend history rather than keeping it only in process memory;
* adding automated tests and CI checks;
* adding rate limiting and monitoring;

##

## Project

**SIH-CREATIO — Heat Stress Early Warning System**

Repository:
https://github.com/JoshuaJacob-15/SIH-CREATIO
