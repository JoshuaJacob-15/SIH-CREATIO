"""
config.py - Configuration and environment setup

Handles:
- Numba cache disabling (fixes Windows permission issues)
- Environment variables
- API configuration
"""

import os
import sys

# =========================================================
# NUMBA CACHE FIX (Windows Permission Issue)
# =========================================================
# On Windows, Numba may fail to write to site-packages
# Disable caching to avoid FileNotFoundError
os.environ['NUMBA_CACHE_DIR'] = os.path.join(os.path.expanduser('~'), '.numba_cache')
os.environ['NUMBA_DISABLE_JIT'] = '0'

# Create cache directory if it doesn't exist
numba_cache = os.environ['NUMBA_CACHE_DIR']
if not os.path.exists(numba_cache):
    os.makedirs(numba_cache, exist_ok=True)

# =========================================================
# API CONFIGURATION
# =========================================================

# Open-Meteo API settings
WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"
WEATHER_API_TIMEOUT = 10  # seconds
WEATHER_API_RETRIES = 3

# Server settings
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8000
RELOAD = True

# Weather refresh settings
WEATHER_REFRESH_INTERVAL = 10  # minutes
RISK_CACHE_TTL = 300  # seconds (5 minutes)

# Logging settings
LOG_LEVEL = os.environ.get('LOGLEVEL', 'INFO')

print(f"✓ Config loaded: Numba cache={numba_cache}, API timeout={WEATHER_API_TIMEOUT}s")
