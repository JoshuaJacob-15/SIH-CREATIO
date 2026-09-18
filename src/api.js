const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api";

const cityCoordinates = {
  Delhi: [28.61, 77.21],
  Chennai: [13.08, 80.27],
  Ahmedabad: [23.02, 72.57],
  Kolkata: [22.57, 88.36],
  Jaipur: [26.91, 75.79],
};
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
  const healthcare = number(vulnerability.factors?.healthcare_capacity, 0.7) * 100;
  const actions = data.human_health_risk?.recommended_actions || [];
  const [lat, lng] = cityCoordinates[city] || [20.5937, 78.9629];

  // --- Additional thermal indicators from the backend's thermal_index.py pipeline ---
  // These follow the same `{ value_c }` shape as heat_index / utci above. If your
  // backend uses different key names for any of these, adjust the paths below to match.
  const wbgt = number(data.wbgt?.value_c);
  const blackGlobeTemp = number(data.black_globe_temp?.value_c);
  const mrt = number(data.mrt?.value_c);

  // --- Solar radiation (from Open-Meteo, surfaced via the weather object) ---
  const radiation = {
    shortwave: number(weather.shortwave_radiation),
    direct: number(weather.direct_radiation),
    diffuse: number(weather.diffuse_radiation),
    directNormal: number(weather.direct_normal_irradiance),
  };

  // --- Raw vs. vulnerability-adjusted risk, plus the full vulnerability factor breakdown ---
  const rawRiskScore = number(data.human_health_risk?.score);
  const adjustedRiskScore = number(data.final_risk?.score, presentation.score);
  const vulnerabilityFactors = {
    elderlyPopulation: number(vulnerability.factors?.elderly_population),
    informalHousing: number(vulnerability.factors?.informal_housing),
    outdoorWorkers: number(vulnerability.factors?.outdoor_workers),
    greenCover: number(vulnerability.factors?.green_cover),
    density: number(vulnerability.factors?.population_density),
    healthcareCapacity: number(vulnerability.factors?.healthcare_capacity),
  };

  return {
    id: city.toLowerCase(),
    name: city,
    risk: presentation.label,
    riskLabel: data.final_risk?.vulnerability_adjusted_risk || null,
    mri: presentation.score,
    utci: presentationUtci[city] ?? number(data.utci?.value_c),
    hi: number(data.heat_index?.value_c, number(weather.temp_c)),
    humidity: number(weather.rh_percent),
    wind: number(weather.wind_speed),
    vulnerable: Math.round(number(vulnerability.score) * 100),
    healthcare: Math.round(healthcare),
    lat,
    lng,
    advisory: actions[0] || "Continue monitoring heat conditions.",

    // Newly surfaced backend data:
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
    .filter(([, result]) => !result.error)
    .map(([city, result]) => toDashboardZone(city, result));
}