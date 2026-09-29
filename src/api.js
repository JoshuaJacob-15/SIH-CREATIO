const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api";

const cityCoordinates = {
  Delhi: [28.61, 77.21],
  Chennai: [13.08, 80.27],
  Ahmedabad: [23.02, 72.57],
  Kolkata: [22.57, 88.36],
  Jaipur: [26.91, 75.79],
};

// Fallback demo values, used ONLY when the backend sends no UTCI.
// Remove this once thermal_index.py returns real UTCI values.
const presentationUtci = {
  Delhi: 43.8,
  Chennai: 39.6,
  Ahmedabad: 45.2,
  Kolkata: 41.7,
  Jaipur: 44.1,
};

const riskPresentation = {
  Low: { label: "Green", score: 20 },
  Moderate: { label: "Yellow", score: 45 },
  High: { label: "Orange", score: 70 },
  "Very High": { label: "Red", score: 85 },
  Extreme: { label: "Red", score: 95 },
};

const number = (value, fallback = null) =>
  value !== null &&
  value !== undefined &&
  value !== "" &&
  Number.isFinite(Number(value))
    ? Number(value)
    : fallback;

/** Convert the backend's city-risk response into the dashboard's display model. */
export function toDashboardZone(city, data) {
  const presentation = riskPresentation[data.final_risk?.vulnerability_adjusted_risk] || {
    label: "Green",
    score: 0,
  };
  const weather = data.weather || {};
  const vulnerability = data.vulnerability || {};
  const factors = vulnerability.factors || {};
  const healthcare = number(factors.healthcare_capacity, 0.7) * 100;
  const actions = data.human_health_risk?.recommended_actions || [];
  const [lat, lng] = cityCoordinates[city] || [20.5937, 78.9629];

  // Thermal indicators (backend keys: wbgt, black_globe_temperature, mean_radiant_temperature, utci)
  const wbgt = number(data.wbgt?.value_c);
  const blackGlobeTemp = number(data.black_globe_temperature?.value_c);
  const mrt = number(data.mean_radiant_temperature?.value_c);
  const liveUtci = number(data.utci?.value_c);

  // Solar radiation (backend sends solar_radiation, not shortwave_radiation)
  const radiation = {
    shortwave: number(weather.solar_radiation),
    direct: number(weather.direct_radiation),
    diffuse: number(weather.diffuse_radiation),
    directNormal: number(weather.direct_normal_irradiance),
  };

  // The backend has no single numeric health-risk score, so add up its 5 sub-scores.
  const rawRiskScore = Object.values(data.human_health_risk?.scores || {}).reduce(
    (sum, s) => sum + (number(s, 0)),
    0
  );
  // The backend has no numeric final score either, so use the level-based one.
  const adjustedRiskScore = presentation.score;

  // Backend factor keys end in _pct (population_density and healthcare_capacity have no suffix).
  const vulnerabilityFactors = {
    elderlyPopulation: number(factors.elderly_pct),
    informalHousing: number(factors.informal_housing_pct),
    outdoorWorkers: number(factors.outdoor_worker_pct),
    greenCover: number(factors.green_cover_pct),
    density: number(factors.population_density),
    healthcareCapacity: number(factors.healthcare_capacity),
  };

  return {
    id: city.toLowerCase(),
    name: city,
    risk: presentation.label,
    riskLabel: data.final_risk?.vulnerability_adjusted_risk || null,
    mri: presentation.score,
    utci: liveUtci ?? presentationUtci[city] ?? null,
    hi: number(data.heat_index?.value_c, number(weather.temp_c)),
    humidity: number(weather.rh_percent),
    wind: number(weather.wind_speed),
    vulnerable: Math.round(number(vulnerability.score, 0) * 100),
    healthcare: Math.round(healthcare),
    lat,
    lng,
    advisory: actions[0] || "Continue monitoring heat conditions.",

    wbgt,
    blackGlobeTemp,
    mrt,
    radiation,
    rawRiskScore,
    adjustedRiskScore,
    vulnerabilityFactors,
    recommendedActions: actions,
  };
}

export async function getLiveRiskZones(signal) {
  const response = await fetch(`${API_BASE_URL}/risk/all`, { signal });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail?.message || body.message || "Unable to load live risk data.");
  }
  const payload = await response.json();
  return Object.entries(payload.results || {})
    .filter(([city, result]) => !result.error && cityCoordinates[city]) // skips cities with no map coordinates (e.g. New York)
    .map(([city, result]) => toDashboardZone(city, result));
}