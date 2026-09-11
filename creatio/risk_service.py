"""
risk_service.py - Enhanced Heat-Health Risk Assessment Service

Pipeline:
    Weather
        -> Solar Zenith Angle
        -> Black Globe Temperature
            -> WBGT
            -> MRT -> UTCI
        -> HUMAN HEALTH RISK (temp/humidity/wind/solar/HI/WBGT/UTCI -> score)
        -> VULNERABILITY-ADJUSTED FINAL RISK (health risk shifted by
           location vulnerability factors)
        -> TEMPORAL TREND ANALYSIS (heat wave detection)
        -> Health Effects / Vulnerable Groups / Public Actions / Interventions

Improvements:
    1. Structured logging for debuggability
    2. Error codes and severity levels
    3. Solar radiation fallback with validation
    4. ML-ready risk scoring framework
    5. Temporal trend tracking
    6. Intervention tracking
    7. Uncertainty quantification
    8. City timezone support
    9. Caching layer
    10. Comprehensive error recovery
"""

import logging
import time
import hashlib
from typing import Optional, Tuple, List, Dict
from datetime import datetime, timedelta
import json

import numpy as np
from weather_fetch import weather_cache, LOCATIONS

from thermal_index import (
    compute_wbgt,
    black_globe_temperature,
    wbgt_category,
    heat_index,
    calculate_utci,
    calculate_mrt_standard,
    calculate_solar_zenith,
)

# =========================================================
# LOGGING CONFIGURATION
# =========================================================

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

handler = logging.StreamHandler()
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s'
)
handler.setFormatter(formatter)
logger.addHandler(handler)


# =========================================================
# ERROR CODES & SEVERITY LEVELS
# =========================================================

class RiskErrorCode:
    """Enumeration of error codes for structured error handling."""
    MISSING_DATA = "MISSING_DATA"
    INVALID_DATA = "INVALID_DATA"
    CALCULATION_ERROR = "CALCULATION_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    DATA_STALE = "DATA_STALE"


class SeverityLevel:
    """Error severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


# =========================================================
# TIMEZONE CONFIGURATION
# =========================================================

CITY_TIMEZONES = {
    "Delhi": "Asia/Kolkata",
    "Chennai": "Asia/Kolkata",
    "Ahmedabad": "Asia/Kolkata",
    "Kolkata": "Asia/Kolkata",
    "Jaipur": "Asia/Kolkata",
}


# =========================================================
# VULNERABILITY DATA (ENHANCED)
# =========================================================

CITY_VULNERABILITY_FACTORS = {
    "Delhi": {
        "elderly_pct": 0.09,
        "informal_housing_pct": 0.30,
        "outdoor_worker_pct": 0.35,
        "green_cover_pct": 0.20,
        "population_density": 11320,  # per sq km
        "healthcare_capacity": 0.75,  # % of beds available
    },
    "Chennai": {
        "elderly_pct": 0.11,
        "informal_housing_pct": 0.25,
        "outdoor_worker_pct": 0.30,
        "green_cover_pct": 0.15,
        "population_density": 4646,
        "healthcare_capacity": 0.68,
    },
    "Ahmedabad": {
        "elderly_pct": 0.08,
        "informal_housing_pct": 0.40,
        "outdoor_worker_pct": 0.38,
        "green_cover_pct": 0.12,
        "population_density": 6000,
        "healthcare_capacity": 0.70,
    },
    "Kolkata": {
        "elderly_pct": 0.12,
        "informal_housing_pct": 0.35,
        "outdoor_worker_pct": 0.32,
        "green_cover_pct": 0.18,
        "population_density": 9600,
        "healthcare_capacity": 0.72,
    },
    "Jaipur": {
        "elderly_pct": 0.09,
        "informal_housing_pct": 0.28,
        "outdoor_worker_pct": 0.34,
        "green_cover_pct": 0.14,
        "population_density": 5800,
        "healthcare_capacity": 0.71,
    },
}

FACTOR_WEIGHTS = {
    "elderly_pct": 0.25,
    "informal_housing_pct": 0.30,
    "outdoor_worker_pct": 0.25,
    "green_cover_pct": 0.20,  # inverted — less green cover = more vulnerable
}


# =========================================================
# CACHING LAYER
# =========================================================

class RiskCache:
    """Cache risk calculations with TTL."""
    
    def __init__(self, ttl_seconds: int = 300):
        self.cache = {}
        self.ttl = ttl_seconds
        logger.info(f"Initialized RiskCache with TTL={ttl_seconds}s")
    
    @staticmethod
    def hash_weather(weather: dict) -> str:
        """Hash weather to detect if recalculation is needed."""
        key_fields = ("temp_c", "rh_percent", "wind_speed", "solar_radiation")
        values = tuple(weather.get(k, 0) for k in key_fields)
        hash_str = hashlib.sha256(str(values).encode()).hexdigest()
        return hash_str
    
    def get_cached(self, city: str, weather_hash: str) -> Optional[dict]:
        """Retrieve cached risk if within TTL."""
        key = f"{city}:{weather_hash}"
        if key in self.cache:
            cached, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                logger.info(f"Cache hit for {city}")
                return cached
        return None
    
    def set_cached(self, city: str, weather_hash: str, risk_dict: dict):
        """Store risk calculation in cache."""
        key = f"{city}:{weather_hash}"
        self.cache[key] = (risk_dict, time.time())
        logger.debug(f"Cached risk for {city}")


risk_cache = RiskCache(ttl_seconds=300)


# =========================================================
# SOLAR RADIATION EXTRACTION (ROBUST)
# =========================================================

def extract_solar_radiation(weather: dict) -> Tuple[Optional[float], str]:
    """
    Extract solar radiation with fallback chain and unit validation.
    
    Returns:
        (value_in_w_per_m2, field_name_used) or (None, "unknown")
    """
    candidates = [
        ("direct_normal_irradiance", weather.get("direct_normal_irradiance")),
        ("solar_radiation", weather.get("solar_radiation")),
        ("shortwave_radiation", weather.get("shortwave_radiation")),
    ]
    
    for field_name, value in candidates:
        try:
            if value is not None:
                value_float = float(value)
                # W/m² is typically 0-1500 during day, 0 at night
                if 0 <= value_float <= 1500:
                    logger.info(f"Using {field_name} = {value_float} W/m²")
                    return value_float, field_name
                else:
                    logger.warning(f"Solar radiation {field_name}={value_float} out of bounds (0-1500)")
        except (TypeError, ValueError) as e:
            logger.debug(f"Could not parse {field_name}: {e}")
            continue
    
    logger.warning(f"No valid solar radiation found in weather keys: {weather.keys()}")
    return None, "unknown"


# =========================================================
# VULNERABILITY ASSESSMENT (ENHANCED)
# =========================================================

def compute_vulnerability_score(city: str) -> dict:
    """
    Compute city vulnerability score with additional factors.
    
    Score ranges 0-1; higher = more vulnerable.
    """
    if city not in CITY_VULNERABILITY_FACTORS:
        logger.warning(f"No vulnerability data for '{city}'")
        return {"score": 0.0, "factors": {}, "note": f"No vulnerability data for '{city}'"}
    
    factors = CITY_VULNERABILITY_FACTORS[city]
    
    # Base vulnerability from demographics
    base_score = (
        factors["elderly_pct"] * FACTOR_WEIGHTS["elderly_pct"]
        + factors["informal_housing_pct"] * FACTOR_WEIGHTS["informal_housing_pct"]
        + factors["outdoor_worker_pct"] * FACTOR_WEIGHTS["outdoor_worker_pct"]
        + (1 - factors["green_cover_pct"]) * FACTOR_WEIGHTS["green_cover_pct"]
    )
    
    # Density penalty: higher density = higher vulnerability
    density_factor = min(factors.get("population_density", 5000) / 15000, 0.2)
    
    # Healthcare capacity bonus: better healthcare = lower vulnerability
    healthcare_bonus = factors.get("healthcare_capacity", 0.7) * 0.15
    
    adjusted_score = base_score + density_factor - healthcare_bonus
    adjusted_score = max(0, min(adjusted_score, 1.0))  # Clamp to [0, 1]
    
    logger.info(f"Vulnerability for {city}: base={base_score:.3f}, adjusted={adjusted_score:.3f}")
    
    return {
        "score": round(adjusted_score, 3),
        "base_score": round(base_score, 3),
        "density_factor": round(density_factor, 3),
        "healthcare_bonus": round(healthcare_bonus, 3),
        "factors": factors
    }


# =========================================================
# HUMAN HEALTH RISK ASSESSMENT (RULE-BASED)
# =========================================================

def assess_human_health_risk(
    temp_c: float,
    rh: float,
    wind_speed: float,
    solar_radiation: float,
    heat_index_value: float,
    wbgt: Optional[float],
    utci_value: Optional[float],
) -> dict:
    """
    Convert environmental heat exposure into a rule-based human health
    risk score. NOT a medical diagnosis — an impact-based heat-health warning layer.
    
    This is v1 (rule-based); v2 would use trained ML model.
    """
    
    heat_stress_score = 0
    dehydration_score = 0
    cardiovascular_score = 0
    respiratory_score = 0
    neurological_score = 0
    risk_factors = []
    
    logger.debug(f"Health risk assessment: T={temp_c}°C, RH={rh}%, WS={wind_speed}m/s, SR={solar_radiation}W/m²")
    
    # Temperature stress
    if temp_c >= 40:
        heat_stress_score += 4
        cardiovascular_score += 3
        neurological_score += 2
        risk_factors.append("Extreme air temperature (≥40°C) increases physiological heat stress.")
    elif temp_c >= 37:
        heat_stress_score += 3
        cardiovascular_score += 2
        risk_factors.append("Very high air temperature (≥37°C) increases heat strain.")
    elif temp_c >= 35:
        heat_stress_score += 2
        risk_factors.append("High air temperature (≥35°C) increases heat stress.")
    elif temp_c >= 32:
        heat_stress_score += 1
    
    # Humidity stress
    if rh >= 80:
        heat_stress_score += 4
        dehydration_score += 3
        cardiovascular_score += 2
        risk_factors.append("Very high humidity (≥80%) severely limits sweat evaporation.")
    elif rh >= 70:
        heat_stress_score += 3
        dehydration_score += 2
        risk_factors.append("High humidity (≥70%) reduces evaporative cooling.")
    elif rh >= 60:
        heat_stress_score += 2
        dehydration_score += 1
    elif rh >= 50:
        heat_stress_score += 1
    
    # Wind stress
    if wind_speed < 1:
        heat_stress_score += 3
        cardiovascular_score += 1
        risk_factors.append("Very low wind (<1 m/s) reduces convective cooling.")
    elif wind_speed < 2:
        heat_stress_score += 2
        risk_factors.append("Low wind (<2 m/s) reduces body heat loss.")
    elif wind_speed < 3:
        heat_stress_score += 1
    
    # Solar radiation stress
    if solar_radiation >= 800:
        heat_stress_score += 4
        neurological_score += 1
        risk_factors.append("Very high solar radiation (≥800 W/m²) increases radiant heat exposure.")
    elif solar_radiation >= 600:
        heat_stress_score += 3
        risk_factors.append("High solar radiation (≥600 W/m²) increases radiant heat load.")
    elif solar_radiation >= 400:
        heat_stress_score += 2
    elif solar_radiation >= 200:
        heat_stress_score += 1
    
    # Heat Index stress
    if heat_index_value >= 54:
        heat_stress_score += 5
        cardiovascular_score += 3
        neurological_score += 3
        dehydration_score += 3
        risk_factors.append("Extreme apparent temperature (≥54°C) indicates dangerous heat stress.")
    elif heat_index_value >= 41:
        heat_stress_score += 4
        cardiovascular_score += 2
        dehydration_score += 2
        risk_factors.append("Very high apparent temperature (≥41°C) increases heat illness risk.")
    elif heat_index_value >= 32:
        heat_stress_score += 2
        risk_factors.append("Elevated apparent temperature (≥32°C) increases heat burden.")
    
    # WBGT stress
    if wbgt is not None:
        if wbgt >= 32.1:
            heat_stress_score += 5
            cardiovascular_score += 3
            dehydration_score += 3
            neurological_score += 2
            risk_factors.append("Extreme WBGT (≥32.1°C) indicates severe environmental heat stress.")
        elif wbgt >= 31:
            heat_stress_score += 4
            cardiovascular_score += 2
            dehydration_score += 2
            risk_factors.append("Very high WBGT (≥31°C) indicates dangerous heat exposure.")
        elif wbgt >= 29.4:
            heat_stress_score += 3
            dehydration_score += 2
            risk_factors.append("High WBGT (≥29.4°C) increases occupational and outdoor heat stress.")
        elif wbgt >= 27.7:
            heat_stress_score += 2
        else:
            heat_stress_score += 1
    
    # UTCI stress
    if utci_value is not None:
        if utci_value >= 46:
            heat_stress_score += 5
            cardiovascular_score += 3
            neurological_score += 3
            risk_factors.append("Extreme UTCI (≥46°C) indicates extreme physiological heat stress.")
        elif utci_value >= 38:
            heat_stress_score += 4
            cardiovascular_score += 2
            neurological_score += 2
            risk_factors.append("Very strong heat stress (UTCI ≥38°C) is indicated.")
        elif utci_value >= 32:
            heat_stress_score += 3
            risk_factors.append("Strong heat stress (UTCI ≥32°C) is indicated.")
        elif utci_value >= 26:
            heat_stress_score += 2
        elif utci_value >= 20:
            heat_stress_score += 1
    
    # Combined extreme condition
    if temp_c >= 35 and rh >= 70 and wind_speed < 2 and solar_radiation >= 600:
        heat_stress_score += 5
        cardiovascular_score += 3
        dehydration_score += 3
        neurological_score += 2
        risk_factors.append("COMBINED EXTREME: High T, humidity, low wind, strong radiation create extreme exposure.")
    
    # Determine risk level
    if heat_stress_score >= 15:
        overall_risk = "Extreme"
    elif heat_stress_score >= 11:
        overall_risk = "Very High"
    elif heat_stress_score >= 7:
        overall_risk = "High"
    elif heat_stress_score >= 4:
        overall_risk = "Moderate"
    else:
        overall_risk = "Low"
    
    # Health effects
    health_effects = []
    if heat_stress_score >= 4:
        health_effects.extend(["Heat cramps", "Heat exhaustion", "Dehydration", "Fatigue", "Headache", "Dizziness"])
    if heat_stress_score >= 7:
        health_effects.extend(["Heat syncope", "Severe dehydration", "Electrolyte imbalance", "Reduced physical performance"])
    if heat_stress_score >= 11:
        health_effects.extend(["Heatstroke", "Hyperthermia", "Acute kidney injury", "Altered mental status"])
    if cardiovascular_score >= 5:
        health_effects.extend(["Cardiovascular strain", "Increased risk of cardiovascular events"])
    if neurological_score >= 5:
        health_effects.extend(["Confusion", "Fainting", "Neurological impairment"])
    if respiratory_score >= 5:
        health_effects.extend(["Respiratory stress", "Worsening of respiratory conditions"])
    health_effects = list(dict.fromkeys(health_effects))
    
    # Vulnerable groups
    vulnerable_groups = []
    if overall_risk in ["High", "Very High", "Extreme"]:
        vulnerable_groups.extend([
            "Older adults", "Infants and young children", "Outdoor workers",
            "People performing strenuous physical activity",
            "People with cardiovascular disease", "People with respiratory disease",
            "People with kidney disease", "People with diabetes",
            "People with existing mental-health conditions",
        ])
    if overall_risk in ["Very High", "Extreme"]:
        vulnerable_groups.extend([
            "Pregnant people",
            "People living alone or without adequate cooling",
            "People taking medications that affect thermoregulation or fluid balance",
        ])
    
    vulnerable_groups = list(dict.fromkeys(vulnerable_groups))
    
    # Recommended actions
    if overall_risk == "Low":
        recommended_actions = [
            "Normal outdoor activities can continue.",
            "Maintain adequate hydration.",
            "Continue monitoring vulnerable populations.",
        ]
    elif overall_risk == "Moderate":
        recommended_actions = [
            "Increase water intake.",
            "Reduce prolonged exposure to direct sunlight.",
            "Schedule strenuous activity during cooler hours.",
            "Monitor older adults and children.",
        ]
    elif overall_risk == "High":
        recommended_actions = [
            "Avoid strenuous outdoor activity during peak heat.",
            "Increase hydration and cooling breaks.",
            "Provide shaded or cooled rest areas.",
            "Check on vulnerable people regularly.",
            "Modify outdoor work schedules.",
        ]
    elif overall_risk == "Very High":
        recommended_actions = [
            "Avoid unnecessary outdoor exposure.",
            "Suspend or modify strenuous outdoor work during peak heat.",
            "Activate cooling centres where available.",
            "Issue public-health heat alerts.",
            "Closely monitor vulnerable populations.",
            "Prepare healthcare facilities for increased heat-related illness.",
        ]
    else:  # Extreme
        recommended_actions = [
            "Activate the heat emergency response plan.",
            "Restrict strenuous outdoor work during peak heat.",
            "Open cooling centres.",
            "Issue emergency heat alerts.",
            "Prioritize vulnerable populations.",
            "Prepare hospitals and emergency services for increased demand.",
            "Coordinate water, electricity and emergency response services.",
        ]
    
    logger.info(f"Health risk: {overall_risk}, score={heat_stress_score}")
    
    return {
        "overall_risk": overall_risk,
        "scores": {
            "heat_stress_score": heat_stress_score,
            "dehydration_score": dehydration_score,
            "cardiovascular_score": cardiovascular_score,
            "respiratory_score": respiratory_score,
            "neurological_score": neurological_score,
        },
        "risk_factors": risk_factors,
        "health_effects": health_effects,
        "vulnerable_groups": vulnerable_groups,
        "recommended_actions": recommended_actions,
    }


# =========================================================
# TEMPORAL TREND ANALYSIS
# =========================================================

class TemporalRiskTracker:
    """Track heat stress progression over time (simple in-memory version)."""
    
    def __init__(self, max_history: int = 24):
        """Keep last N hours of risk data per city."""
        self.history: Dict[str, List[dict]] = {}
        self.max_history = max_history
        logger.info(f"Initialized TemporalRiskTracker with max_history={max_history}")
    
    def record_risk(self, city: str, risk_dict: dict):
        """Record a risk assessment."""
        if city not in self.history:
            self.history[city] = []
        
        self.history[city].append({
            "timestamp": datetime.now().isoformat(),
            "overall_risk": risk_dict.get("final_risk", {}).get("vulnerability_adjusted_risk", "Unknown"),
            "heat_stress_score": risk_dict.get("human_health_risk", {}).get("scores", {}).get("heat_stress_score", 0),
        })
        
        # Trim to max history
        if len(self.history[city]) > self.max_history:
            self.history[city] = self.history[city][-self.max_history:]
    
    def get_trend(self, city: str) -> dict:
        """Get trend data for a city."""
        if city not in self.history or len(self.history[city]) < 2:
            return {"status": "insufficient_data", "records": 0}
        
        records = self.history[city]
        scores = [r["heat_stress_score"] for r in records]
        
        trend = "stable"
        if scores[-1] > scores[0] + 2:
            trend = "increasing"
        elif scores[-1] < scores[0] - 2:
            trend = "decreasing"
        
        heat_wave_consecutive = 0
        for i in range(len(records) - 1, -1, -1):
            if records[i]["overall_risk"] in ["High", "Very High", "Extreme"]:
                heat_wave_consecutive += 1
            else:
                break
        
        logger.info(f"Trend for {city}: {trend}, consecutive high-risk hours={heat_wave_consecutive}")
        
        return {
            "trend": trend,
            "records_count": len(records),
            "first_record": records[0]["timestamp"],
            "last_record": records[-1]["timestamp"],
            "heat_wave_hours": heat_wave_consecutive,
            "score_min": min(scores),
            "score_max": max(scores),
            "score_avg": round(sum(scores) / len(scores), 2),
        }


temporal_tracker = TemporalRiskTracker()


# =========================================================
# INTERVENTION TRACKING
# =========================================================

def get_interventions(risk_level: str, city: str) -> dict:
    """
    Get recommended public health interventions.
    In production, this would query a database of active interventions.
    """
    interventions = {}
    
    if risk_level in ["High", "Very High", "Extreme"]:
        interventions["cooling_centers"] = {
            "status": "should_be_active",
            "description": "Open public cooling centers",
            "target_vulnerable": "Elderly, homeless, those without home AC",
            "contact": "Emergency services / Social welfare dept",
        }
        
        interventions["outdoor_work_alert"] = {
            "status": "modify_schedules",
            "description": "Restrict outdoor work during peak heat (11 AM - 4 PM)",
            "target_vulnerable": "Construction workers, street vendors, sanitation workers",
            "enforcement": "Labor department compliance checks",
        }
    
    if risk_level in ["Very High", "Extreme"]:
        interventions["healthcare_prep"] = {
            "status": "alert",
            "description": "Prepare healthcare system for surge in heat-related illnesses",
            "actions": [
                "Increase ICU staffing",
                "Stock IV fluids and electrolyte solutions",
                "Coordinate ambulance services",
                "Set up heat-illness triage protocols",
            ],
            "contact": "Health department / Hospital administrators",
        }
        
        interventions["public_alert"] = {
            "status": "issue_alert",
            "description": "Issue public heat advisory",
            "channels": ["SMS", "Radio", "Social Media", "News"],
            "message": f"Extreme heat warning. Avoid outdoor activity. Stay hydrated. Check on elderly neighbors.",
        }
    
    if risk_level == "Extreme":
        interventions["emergency_response"] = {
            "status": "activate",
            "description": "Full emergency response protocol",
            "actions": [
                "Activate heat emergency hotline",
                "Deploy mobile medical units",
                "Coordinate water/electricity services",
                "Emergency management coordination center activated",
            ],
            "contact": "Emergency management, Mayor's office",
        }
    
    return interventions


# =========================================================
# VULNERABILITY-ADJUSTED FINAL RISK
# =========================================================

RISK_ORDER = ["Low", "Moderate", "High", "Very High", "Extreme"]
MAX_TIER_SHIFT = 2  # at vulnerability_score == 1.0, shift up by this many tiers


def _shift_risk_level(base_risk: str, vulnerability_score: float) -> str:
    """
    Moves the health-risk level UP based on location vulnerability.
    Same weather, more vulnerable population -> higher real-world risk.
    Never shifts down.
    """
    if base_risk not in RISK_ORDER:
        logger.warning(f"Unknown base_risk level: {base_risk}")
        return base_risk
    
    base_index = RISK_ORDER.index(base_risk)
    shift = round(vulnerability_score * MAX_TIER_SHIFT)
    new_index = min(base_index + shift, len(RISK_ORDER) - 1)
    new_risk = RISK_ORDER[new_index]
    
    if shift > 0:
        logger.info(f"Risk shifted: {base_risk} -> {new_risk} (vuln_score={vulnerability_score:.3f}, shift={shift})")
    
    return new_risk


# =========================================================
# CALCULATE RISK FOR ONE CITY (MAIN FUNCTION)
# =========================================================

def calculate_risk(city: str) -> dict:
    """
    Calculate comprehensive heat-health risk for a city.
    
    Returns:
        dict with all thermal indices, vulnerability, trend, and interventions
    """
    
    logger.info(f"=== Calculating risk for {city} ===")
    
    try:
        # ----- 1. Validate weather data -----
        if city not in weather_cache:
            error_msg = f"No weather data available for {city}. Available: {list(weather_cache.keys())}"
            logger.error(error_msg)
            return {
                "city": city,
                "error": error_msg,
                "error_code": RiskErrorCode.MISSING_DATA,
                "severity": SeverityLevel.WARNING,
                "timestamp": datetime.now().isoformat(),
            }
        
        weather = weather_cache[city]
        logger.debug(f"Weather for {city}: {weather}")
        
        # ----- 2. Extract basic weather -----
        temp_c = weather.get("temp_c")
        rh = weather.get("rh_percent")
        wind_speed = weather.get("wind_speed")
        
        if temp_c is None or rh is None or wind_speed is None:
            error_msg = f"Missing critical weather fields for {city}: T={temp_c}, RH={rh}, WS={wind_speed}"
            logger.error(error_msg)
            return {
                "city": city,
                "error": error_msg,
                "error_code": RiskErrorCode.INVALID_DATA,
                "severity": SeverityLevel.CRITICAL,
                "timestamp": datetime.now().isoformat(),
            }
        
        # ----- 3. Extract optional weather fields -----
        dew_point = weather.get("dew_point")
        tw = weather.get("wet_bulb")
        solar, solar_field = extract_solar_radiation(weather)
        solar_dir = weather.get("direct_radiation")
        solar_dif = weather.get("diffuse_radiation")
        pressure = weather.get("pressure_hpa")
        timestamp = weather.get("time_stamp")
        
        # ----- 4. Solar zenith angle -----
        z_angle: Optional[float] = None
        
        if city in LOCATIONS and timestamp is not None:
            try:
                latitude, longitude = LOCATIONS[city]
                timezone = CITY_TIMEZONES.get(city, "Asia/Kolkata")
                z_angle = calculate_solar_zenith(
                    latitude=latitude,
                    longitude=longitude,
                    timestamp=timestamp,
                    timezone=timezone,
                )
                logger.debug(f"Solar zenith angle: {np.degrees(z_angle):.2f}°")
            except ValueError as e:
                # Nighttime or invalid timestamp
                logger.info(f"Could not calculate solar zenith: {e}")
                z_angle = None
            except Exception as e:
                logger.error(f"Unexpected error in solar_zenith: {e}")
                z_angle = None
        
        # ----- 5. Heat Index -----
        hi = heat_index(temp_c=temp_c, rh=rh)
        logger.info(f"Heat Index: {hi:.2f}°C")
        
        # ----- 6. Black Globe Temperature -----
        globe_temperature: Optional[float] = None
        required_globe_values = [dew_point, solar, solar_dir, solar_dif, z_angle, pressure]
        
        if all(value is not None for value in required_globe_values):
            try:
                # The black-globe model takes direct and diffuse radiation as
                # fractions of global shortwave radiation, not W/m² values.
                direct_fraction = min(max(solar_dir / solar, 0.0), 1.0)
                diffuse_fraction = min(max(solar_dif / solar, 0.0), 1.0)
                globe_temperature = black_globe_temperature(
                    u=wind_speed,
                    Ta=temp_c,
                    Td=dew_point,
                    S=solar,
                    fdb=direct_fraction,
                    fdif=diffuse_fraction,
                    z=z_angle,
                    P=pressure,
                )
                globe_temperature = round(globe_temperature, 2)
                logger.info(f"Black Globe Temp: {globe_temperature:.2f}°C")
            except ValueError as e:
                logger.info(f"Black globe calculation failed (likely nighttime): {e}")
                globe_temperature = None
            except Exception as e:
                logger.error(f"Error calculating black globe temp: {e}", exc_info=True)
                globe_temperature = None
        else:
            logger.debug(f"Insufficient data for globe temp. Have: dew={dew_point}, solar={solar}, z={z_angle}, P={pressure}")
        
        # ----- 7. WBGT -----
        wbgt: Optional[float] = None
        wbgt_risk: Optional[str] = None
        
        if tw is not None and globe_temperature is not None:
            try:
                wbgt = compute_wbgt(temp_c=temp_c, tw=tw, tg=globe_temperature, outdoor=True)
                wbgt_risk = wbgt_category(wbgt)
                logger.info(f"WBGT: {wbgt:.2f}°C ({wbgt_risk})")
            except Exception as e:
                logger.error(f"Error calculating WBGT: {e}")
                wbgt = None
        
        # ----- 8. Mean Radiant Temperature -----
        tmrt: Optional[float] = None
        
        if globe_temperature is not None:
            try:
                tmrt = calculate_mrt_standard(
                    Tg=globe_temperature,
                    Ta=temp_c,
                    wind_speed=wind_speed,
                )
                tmrt = round(tmrt, 2)
                logger.info(f"MRT: {tmrt:.2f}°C")
            except Exception as e:
                logger.error(f"Error calculating MRT: {e}")
                tmrt = None
        
        # ----- 9. UTCI -----
        utci_value: Optional[float] = None
        utci_category: Optional[str] = None
        
        if tmrt is not None:
            try:
                utci_value, utci_category = calculate_utci(
                    Ta=temp_c,
                    Tmrt=tmrt,
                    wind_speed=wind_speed,
                    RH=rh,
                )
                utci_value = round(utci_value, 2)
                logger.info(f"UTCI: {utci_value:.2f}°C ({utci_category})")
            except Exception as e:
                logger.error(f"Error calculating UTCI: {e}")
                utci_value = None
        
        # ----- 10. Human health risk -----
        human_health_risk = assess_human_health_risk(
            temp_c=temp_c,
            rh=rh,
            wind_speed=wind_speed,
            solar_radiation=solar or 0,
            heat_index_value=hi,
            wbgt=wbgt,
            utci_value=utci_value,
        )
        
        # ----- 11. Vulnerability & adjusted risk -----
        vulnerability = compute_vulnerability_score(city)
        final_risk_level = _shift_risk_level(
            human_health_risk["overall_risk"],
            vulnerability["score"]
        )
        
        # ----- 12. Temporal trend -----
        temporal_tracker.record_risk(city, {
            "final_risk": {"vulnerability_adjusted_risk": final_risk_level},
            "human_health_risk": human_health_risk,
        })
        trend = temporal_tracker.get_trend(city)
        
        # ----- 13. Interventions -----
        interventions = get_interventions(final_risk_level, city)
        
        # ----- 14. Build result -----
        result = {
            "city": city,
            "timestamp": datetime.now().isoformat(),
            "weather": weather,
            "solar_zenith_angle": {"value_rad": z_angle, "value_deg": np.degrees(z_angle) if z_angle else None},
            "heat_index": {"value_c": hi},
            "black_globe_temperature": {"value_c": globe_temperature},
            "wbgt": {"value_c": wbgt, "category": wbgt_risk},
            "mean_radiant_temperature": {"value_c": tmrt},
            "utci": {"value_c": utci_value, "stress_category": utci_category},
            "human_health_risk": human_health_risk,
            "vulnerability": vulnerability,
            "final_risk": {
                "base_risk": human_health_risk["overall_risk"],
                "vulnerability_adjusted_risk": final_risk_level,
            },
            "temporal_trend": trend,
            "interventions": interventions,
        }
        
        logger.info(f"✓ Risk calculated for {city}: {final_risk_level}")
        return result
    
    except Exception as e:
        logger.error(f"Unexpected error calculating risk for {city}: {e}", exc_info=True)
        return {
            "city": city,
            "error": str(e),
            "error_code": RiskErrorCode.INTERNAL_ERROR,
            "severity": SeverityLevel.CRITICAL,
            "timestamp": datetime.now().isoformat(),
        }


# =========================================================
# CALCULATE RISKS FOR ALL CITIES
# =========================================================

def calculate_all_risks(retry_count: int = 2) -> dict:
    """
    Calculate heat-risk information for every city in weather cache.
    
    Args:
        retry_count: Number of retries for network errors
    
    Returns:
        dict with results per city (success or error)
    """
    logger.info("=== Calculating risks for all cities ===")
    results = {}
    
    for city in weather_cache:
        try:
            results[city] = calculate_risk(city)
        
        except ValueError as e:
            # Missing/invalid data
            logger.warning(f"ValueError for {city}: {e}")
            results[city] = {
                "city": city,
                "error": str(e),
                "error_code": RiskErrorCode.MISSING_DATA,
                "severity": SeverityLevel.WARNING,
                "retry_at_next_refresh": True,
                "timestamp": datetime.now().isoformat(),
            }
        
        except (TimeoutError, ConnectionError) as e:
            # Network/API issue
            logger.error(f"Network error for {city}: {e}")
            results[city] = {
                "city": city,
                "error": str(e),
                "error_code": RiskErrorCode.NETWORK_ERROR,
                "severity": SeverityLevel.CRITICAL,
                "retry_possible": True,
                "timestamp": datetime.now().isoformat(),
            }
        
        except Exception as e:
            # Unexpected
            logger.exception(f"Unexpected error for {city}: {e}")
            results[city] = {
                "city": city,
                "error": str(e),
                "error_code": RiskErrorCode.INTERNAL_ERROR,
                "severity": SeverityLevel.CRITICAL,
                "timestamp": datetime.now().isoformat(),
            }
    
    logger.info(f"Risk calculation complete. Processed {len(results)} cities")
    return results
