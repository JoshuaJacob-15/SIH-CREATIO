# Heat Stress Early Warning System - Setup & Running Guide

## 📁 Directory Structure

```
SIH-CREATIO/
├── creatio/                    # Main Python backend
│   ├── config.py               # ← NEW: Environment setup & Numba fix
│   ├── main.py                 # FastAPI server (v2.0)
│   ├── risk_service.py         # Risk calculation engine (v2.0)
│   ├── thermal_index.py        # Heat stress formulas (v2.0)
│   ├── weather_fetch.py        # Weather API integration (v2.0 FIXED)
│   └── requirements.txt        # Python dependencies
├── src/                        # Frontend (React/Vue)
├── dist/                       # Built frontend
├── index.html                  # Landing page
├── package.json                # Node.js dependencies
├── README.md                   # Project overview
├── IMPROVEMENTS_V2.md          # Enhancement documentation
└── SETUP_GUIDE.md              # This file
```

---

## 🚀 Quick Start (Windows/macOS/Linux)

### Step 1: Navigate to Backend Directory
```bash
cd creatio
```

### Step 2: Install Python Dependencies
```bash
pip install -r requirements.txt
```

**What gets installed:**
- `pythermalcomfort` - Thermal index calculations
- `pvlib` - Solar position algorithms
- `pandas` - Data manipulation
- `numpy` - Numerical computing
- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `httpx` - Async HTTP client
- `apscheduler` - Background task scheduling

### Step 3: Start the Server
```bash
python -m uvicorn main:app --reload
```

**Expected output:**
```
✓ Config loaded: Numba cache=...
2026-09-10 16:50:00 - main - INFO - ============================================================
2026-09-10 16:50:00 - main - INFO - 🌡️  HEAT STRESS EARLY WARNING SYSTEM - STARTUP
2026-09-10 16:50:00 - main - INFO - ============================================================
2026-09-10 16:50:02 - main - INFO - ✓ Weather cache populated: ['Delhi', 'Chennai', 'Ahmedabad', 'Kolkata', 'Jaipur']
2026-09-10 16:50:02 - main - INFO - ✓ Background scheduler started (10-minute interval)
2026-09-10 16:50:02 - main - INFO - ✓ STARTUP COMPLETE - System ready
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

### Step 4: Test the API

**Interactive documentation:**
```
http://127.0.0.1:8000/docs
```

**Get risk for Delhi:**
```bash
curl http://127.0.0.1:8000/risk/current?city=Delhi
```

**Get all cities:**
```bash
curl http://127.0.0.1:8000/risk/all
```

---

## ⚠️ Common Errors & Fixes

### Error 1: "Could not import module main"

**Problem:**
```
ERROR:    Error loading ASGI app. Could not import module "main".
```

**Cause:** Running from wrong directory

**Fix:**
```bash
# ❌ Wrong
python -m uvicorn main:app --reload

# ✅ Correct
cd creatio
python -m uvicorn main:app --reload
```

---

### Error 2: "ModuleNotFoundError: No module named 'weather_fetch'"

**Problem:**
```
ModuleNotFoundError: No module named 'weather_fetch'
```

**Cause:** Missing dependencies or wrong directory

**Fix:**
```bash
# Make sure you're in creatio/ directory
cd creatio

# Install dependencies
pip install -r requirements.txt

# Try again
python -m uvicorn main:app --reload
```

---

### Error 3: "FileNotFoundError: [Errno 2] No such file or directory" (Numba caching)

**Problem:**
```
FileNotFoundError: [Errno 2] No such file or directory: 
'C:\\Users\\...\\site-packages\\pythermalcomfort\\models\\__pycache__\\...'
```

**Cause:** Numba tried to write cache to site-packages (permission denied on Windows)

**Fix:** ✅ ALREADY FIXED in v2.0!
- Created `config.py` that redirects Numba cache
- `main.py` imports `config.py` FIRST
- No more permission errors

If still happening:
```bash
# Reinstall dependencies
pip install --upgrade -r requirements.txt

# Clear Python cache
find . -type d -name __pycache__ -exec rm -r {} +

# Try again
python -m uvicorn main:app --reload
```

---

### Error 4: "No weather data available" or "Weather cache is empty"

**Problem:**
```json
{"error": "No weather data available", "message": "Weather cache is empty"}
```

**Cause:** API not called yet, or network issue

**Fix:** 
1. System fetches weather on startup automatically
2. Wait 5-10 seconds for console to show:
   ```
   ✓ Weather cache populated: ['Delhi', 'Chennai', 'Ahmedabad', 'Kolkata', 'Jaipur']
   ```
3. If still empty after 10 seconds, check internet connection:
   ```bash
   curl https://api.open-meteo.com/v1/forecast?latitude=28.61&longitude=77.21&current=temperature_2m
   ```

---

### Error 5: "Timeout Error from Open-Meteo API"

**Problem:**
```
TimeoutException: Request timed out
```

**Cause:** Network issue or API is slow

**Fix:** 
1. System automatically retries with exponential backoff
2. If persistent, increase timeout in `config.py`:
   ```python
   WEATHER_API_TIMEOUT = 20  # Increase from 10
   ```
3. Check if API is down: https://open-meteo.com/

---

## 📝 Development Workflow

### Run with Debug Logging

Show detailed logs for each calculation step:
```bash
python -m uvicorn main:app --reload --log-level debug
```

### View Specific Logs

Example - see only main.py logs:
```bash
python -m uvicorn main:app --reload 2>&1 | grep "main"
```

### Test Individual Endpoints

```bash
# Single city (detailed response)
curl http://127.0.0.1:8000/risk/current?city=Delhi | python -m json.tool

# All cities (summary)
curl http://127.0.0.1:8000/risk/all | python -m json.tool

# Temporal trends
curl http://127.0.0.1:8000/risk/trends?city=Delhi | python -m json.tool

# Public health interventions
curl http://127.0.0.1:8000/interventions | python -m json.tool

# System health
curl http://127.0.0.1:8000/health | python -m json.tool
```

---

## 🔧 Configuration

### Weather Refresh Interval

Edit `weather_fetch.py`, search for `start_scheduler`:
```python
# Default: 10 minutes
start_scheduler(interval_minutes=10)

# Change to 5 minutes
start_scheduler(interval_minutes=5)
```

### Cache Duration

Edit `risk_service.py`, search for `RiskCache`:
```python
# Default: 300 seconds (5 minutes)
risk_cache = RiskCache(ttl_seconds=300)

# Change to 60 seconds
risk_cache = RiskCache(ttl_seconds=60)
```

### API Timeout

Edit `config.py`:
```python
# Default: 10 seconds
WEATHER_API_TIMEOUT = 10

# Change to 20 seconds
WEATHER_API_TIMEOUT = 20
```

### Add New City

1. Edit `weather_fetch.py`:
```python
LOCATIONS = {
    "Delhi": (28.61, 77.21),
    "Chennai": (13.08, 80.27),
    "Ahmedabad": (23.02, 72.57),
    "Kolkata": (22.57, 88.36),
    "Jaipur": (26.91, 75.79),
    "Mumbai": (19.08, 72.88),  # ← Add new city
}
```

2. Edit `risk_service.py`:
```python
CITY_TIMEZONES = {
    "Delhi": "Asia/Kolkata",
    "Chennai": "Asia/Kolkata",
    "Ahmedabad": "Asia/Kolkata",
    "Kolkata": "Asia/Kolkata",
    "Jaipur": "Asia/Kolkata",
    "Mumbai": "Asia/Kolkata",  # ← Add timezone
}

CITY_VULNERABILITY_FACTORS = {
    "Delhi": {...},
    "Mumbai": {  # ← Add vulnerability data
        "elderly_pct": 0.10,
        "informal_housing_pct": 0.32,
        "outdoor_worker_pct": 0.36,
        "green_cover_pct": 0.19,
        "population_density": 20961,
        "healthcare_capacity": 0.75,
    },
}
```

---

## 📊 API Reference

### GET /risk/current?city=X
Single city risk assessment with all thermal indices

**Response fields:**
- `city` - City name
- `timestamp` - ISO timestamp
- `weather` - Current weather data
- `heat_index` - Apparent temperature
- `black_globe_temperature` - Radiation effect
- `wbgt` - Wet-bulb globe temperature
- `utci` - Universal thermal climate index
- `mean_radiant_temperature` - Radiant heat
- `human_health_risk` - Health impact assessment
- `vulnerability` - Location vulnerability score
- `final_risk` - Adjusted risk level
- `temporal_trend` - Heat wave progression
- `interventions` - Public health actions

---

### GET /risk/all
All cities risk assessment in one request

**Returns:**
- `timestamp` - Request time
- `summary` - Success/failure counts
- `results` - City-by-city data (same structure as /risk/current)

---

### GET /risk/trends?city=X
Temporal trend analysis

**Returns:**
- `trend` - "increasing", "stable", or "decreasing"
- `heat_wave_hours` - Consecutive high-risk hours
- `score_min/max/avg` - Risk score statistics
- `records_count` - Historical data available

---

### GET /health
System diagnostics

**Returns:**
- `status` - "ok" or "degraded"
- `weather_cache` - Cached cities
- `scheduler` - Background job status
- `system` - Version info

---

### GET /interventions
Public health actions

**Returns:**
- `cooling_centers` - Should be activated?
- `outdoor_work_alert` - Work restrictions
- `healthcare_prep` - Hospital preparation
- `public_alert` - SMS/media alerts

---

### GET /docs
Interactive Swagger UI for testing all endpoints

---

## 🧪 Manual Testing

### Test Individual Modules

```python
# In Python REPL (in creatio/ directory)

# Test weather fetch
from weather_fetch import weather_cache, fetch_weather_for
import asyncio
result = asyncio.run(fetch_weather_for(28.61, 77.21))
print(result)

# Test risk calculation
from risk_service import calculate_risk
result = calculate_risk("Delhi")
print(result)

# Test thermal indices
from thermal_index import heat_index
hi = heat_index(temp_c=35, rh=70)
print(f"Heat Index: {hi}°C")
```

---

## 🐛 Debugging Tips

### Check Server Logs

Look at the console running `uvicorn`. Logs show:
- Request arrivals
- Calculation steps
- Error details
- Performance metrics

### Enable Full Traceback

If you get a 500 error, look at server console for:
```
ERROR:     Exception in ASGI app
Traceback (most recent call last):
  File "...", line XXX, in ...
    ...
```

### Verify Weather Cache

Open browser to:
```
http://127.0.0.1:8000/health
```

Should show 5 cached cities with `"status": "ok"`

### Check Scheduler

In `/health` response, look for:
```json
"scheduler": {
  "status": "running",
  "job_count": 1
}
```

---

## ✅ Verification Checklist

Before considering setup complete:

- [ ] Python 3.8+ installed
- [ ] Inside `creatio/` directory
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] Internet connection working
- [ ] Port 8000 not in use
- [ ] Server starts without errors
- [ ] No Numba caching errors (FileNotFoundError)
- [ ] `/health` endpoint returns `status: ok`
- [ ] `/risk/current?city=Delhi` returns weather data
- [ ] `/docs` shows interactive Swagger UI
- [ ] Browser refresh still works (not crashed)

---

## 🆘 Still Having Issues?

### 1. Check Python version:
```bash
python --version  # Should be 3.8 or higher
```

### 2. Reinstall dependencies:
```bash
pip install --upgrade -r requirements.txt
```

### 3. Clear Python cache:
```bash
# Windows
del /s /q __pycache__

# macOS/Linux
find . -type d -name __pycache__ -exec rm -r {} +
```

### 4. Check if Open-Meteo API is accessible:
```bash
curl https://api.open-meteo.com/v1/forecast?latitude=28.61&longitude=77.21&current=temperature_2m
```

Should return JSON with weather data.

### 5. Try with explicit Python path:
```bash
C:\Python311\Scripts\uvicorn.exe main:app --reload
```

---

## 📚 Documentation Files

- **IMPROVEMENTS_V2.md** - Detailed enhancement summary
- **SETUP_GUIDE.md** - This file
- **API /docs** - Interactive Swagger UI (http://127.0.0.1:8000/docs)
- **Code docstrings** - Each function has comprehensive docstring

---

## 🎯 Next Steps

1. ✅ Start the server
2. ✅ Test endpoints via /docs
3. ✅ Verify weather data is being fetched
4. ✅ Check trends across cities
5. ✅ Review intervention recommendations

---

**Version**: 2.0  
**Last Updated**: 2026-09-10  
**Status**: ✅ Production Ready  
**Platforms**: Windows ✅ macOS ✅ Linux ✅
