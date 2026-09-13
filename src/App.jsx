import React, { useState, useMemo, useEffect } from "react";
import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Popup,
  Marker,
} from "react-leaflet";
import L from "leaflet";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { zones as demoZones, forecastByCity, facilities } from "./data";
import { getLiveRiskZones } from "./api";

// ---------------------------------------------------------------------------
// Constants & small reusable pieces
// ---------------------------------------------------------------------------

// Maps each risk level to the color used across badges, map markers, charts.
const colors = {
  Green: "#16a34a",
  Yellow: "#eab308",
  Orange: "#f97316",
  Red: "#dc2626",
};

// Custom Leaflet icon (a hospital emoji) used for healthcare facility markers on the map.
const icon = L.divIcon({
  className: "facility-icon",
  html: "🏥",
  iconSize: [28, 28],
  iconAnchor: [14, 14],
});

// Small colored pill showing a risk level, e.g. "● Orange".
// `children` lets you override the displayed text while keeping the risk's color/class.
function Badge({ risk, children }) {
  return <span className={"badge " + risk.toLowerCase()}>● {children || risk}</span>;
}

// A single stat block: a label, a big value, a unit, and an optional progress bar.
function Metric({ label, value, unit, progress }) {
  return (
    <div className="metric">
      <small>{label}</small>
      <strong>{value}</strong>
      <span>{unit}</span>
      {progress !== undefined && (
        <div className="progress">
          <i style={{ width: progress + "%" }} />
        </div>
      )}
    </div>
  );
}

// Formats a UTCI (Universal Thermal Climate Index) number as "xx.x°C",
// or "Unavailable" if the value is missing/not a number.
function formatUtci(value) {
  return typeof value === "number" && Number.isFinite(value)
    ? `${value.toFixed(1)}°C`
    : "Unavailable";
}

// ---------------------------------------------------------------------------
// Main App component
// ---------------------------------------------------------------------------

function App() {
  // Zones fetched from the live API (empty until the fetch succeeds).
  const [liveZones, setLiveZones] = useState([]);

  // Tracks whether we're still loading, showing live data, or falling back to demo data.
  const [dataStatus, setDataStatus] = useState("loading");
  const [dataError, setDataError] = useState("");

  // Use live data if we have it, otherwise fall back to the bundled demo data.
  const zones = liveZones.length ? liveZones : demoZones;

  // Currently selected city/zone (shown in detail panels, map highlight, etc).
  const [selected, setSelected] = useState(demoZones[1]);

  // Which sidebar tab is active: overview / map / forecast / alerts / analytics.
  const [tab, setTab] = useState("overview");

  // Forecast range toggle (3 or 5 days).
  const [days, setDays] = useState(5);

  // Which data layer is shown on the map: risk / vulnerability / healthcare.
  const [layer, setLayer] = useState("risk");

  // City search box text (used to filter the zone list).
  const [query, setQuery] = useState("");

  // Alert composer state: the message text and whether it was just "sent".
  const [message, setMessage] = useState(
    "Heat alert: Avoid outdoor activity between 12 PM and 4 PM. Stay hydrated and use the nearest cooling centre if needed."
  );
  const [sent, setSent] = useState(false);

  // On mount: fetch live risk zones from the API.
  // If it returns data, switch to "live" mode and default-select Kolkata (or the first city).
  // If it fails or returns nothing, fall back to demo data.
  useEffect(() => {
    const controller = new AbortController();

    getLiveRiskZones(controller.signal)
      .then((results) => {
        if (results.length) {
          setLiveZones(results);
          setSelected(results.find((zone) => zone.name === "Kolkata") || results[0]);
          setDataStatus("live");
        } else {
          setDataStatus("fallback");
        }
      })
      .catch((error) => {
        if (error.name !== "AbortError") {
          setDataError(error.message);
          setDataStatus("fallback");
        }
      });

    // Cleanup: abort the fetch if the component unmounts before it finishes.
    return () => controller.abort();
  }, []);

  // City list filtered by the search box, recalculated only when the query changes.
  const filtered = useMemo(
    () => zones.filter((z) => z.name.toLowerCase().includes(query.toLowerCase())),
    [query]
  );

  // Count how many zones fall into each risk level, e.g. { Green: 3, Orange: 2 }.
  // Used for the analytics bar chart.
  const riskCounts = zones.reduce((acc, z) => {
    acc[z.risk] = (acc[z.risk] || 0) + 1;
    return acc;
  }, {});

  // -------------------------------------------------------------------------
  // Sub-sections (rendered inside App, so they can close over App's state)
  // -------------------------------------------------------------------------

  // The interactive Leaflet map showing every city as a colored circle marker.
  // `full` renders it as a large, standalone panel (used on the "map" tab).
  function MapPanel({ full = false }) {
    return (
      <section className={"card panel map-panel " + (full ? "full-map" : "")}>
        <div className="panel-head">
          <div>
            <h3>Interactive city risk map</h3>
            <p>Click a marker to inspect detailed thermal and vulnerability indicators.</p>
          </div>
          <div className="layer-buttons">
            {["risk", "vulnerability", "healthcare"].map((x) => (
              <button
                className={layer === x ? "layer active" : "layer"}
                onClick={() => setLayer(x)}
                key={x}
              >
                {x}
              </button>
            ))}
          </div>
        </div>

        <div className="map">
          <MapContainer center={[22.5726, 88.3639]} zoom={5} scrollWheelZoom className="leaflet">
            <TileLayer
              attribution="&copy; OpenStreetMap contributors"
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />

            {/* One circle marker per city. Color depends on the active layer. */}
            {zones.map((z) => (
              <CircleMarker
                key={z.id}
                center={[z.lat, z.lng]}
                radius={selected.id === z.id ? 22 : 17}
                pathOptions={{
                  color: "#fff",
                  weight: 3,
                  fillColor:
                    layer === "risk"
                      ? colors[z.risk]
                      : layer === "vulnerability"
                      ? "#8b5cf6"
                      : "#0ea5e9",
                  fillOpacity: 0.8,
                }}
                eventHandlers={{ click: () => setSelected(z) }}
              >
                <Popup>
                  <b>{z.name}</b>
                  <br />
                  MRI: {z.mri}
                  <br />
                  UTCI: {formatUtci(z.utci)}
                  <br />
                  <Badge risk={z.risk}>{z.risk} risk</Badge>
                </Popup>
              </CircleMarker>
            ))}

            {/* On the "healthcare" layer, also show hospital/facility markers. */}
            {layer === "healthcare" &&
              facilities.map((f) => (
                <Marker key={f.name} position={[f.lat, f.lng]} icon={icon}>
                  <Popup>
                    <b>{f.name}</b>
                    <br />
                    {f.type}
                    <br />
                    {f.capacity}
                  </Popup>
                </Marker>
              ))}
          </MapContainer>

          {/* Color legend for the risk levels. */}
          <div className="map-key">
            {Object.keys(colors).map((r) => (
              <span key={r}>
                <i style={{ background: colors[r] }} />
                {r}
              </span>
            ))}
          </div>
        </div>
      </section>
    );
  }

  // Detailed metrics panel for the currently selected city.
  function Details() {
    return (
      <section className="card panel">
        <div className="panel-head">
          <div>
            <h3>{selected.name}</h3>
            <p>Detailed risk assessment</p>
          </div>
          <Badge risk={selected.risk}>
            {selected.risk} · MRI {selected.mri}
          </Badge>
        </div>

        <div className="metrics">
          <Metric
            label="UTCI"
            value={selected.utci === null ? "Unavailable" : selected.utci.toFixed(1)}
            unit={selected.utci === null ? "" : "°C equivalent"}
          />
          <Metric label="Heat Index" value={selected.hi} unit="°C" />
          <Metric label="Humidity" value={selected.humidity + "%"} unit="relative humidity" />
          <Metric label="Wind speed" value={selected.wind} unit="m/s" />
          <Metric
            label="Vulnerable population"
            value={selected.vulnerable + "%"}
            unit="elderly + outdoor workers"
            progress={selected.vulnerable}
          />
          <Metric
            label="Healthcare capacity"
            value={selected.healthcare + "%"}
            unit="available capacity"
            progress={selected.healthcare}
          />
        </div>

        <div className="advisory">
          <b>Recommended action</b>
          <p>{selected.advisory}</p>
        </div>
      </section>
    );
  }

  // 3–5 day forecast cards + a trend line chart (MRI over time) for the selected city.
  function ForecastPanel() {
    const cityForecast = forecastByCity[selected.name] || forecastByCity.Kolkata;

    return (
      <div className="forecast-wrap">
        <div className="panel-head">
          <div>
            <h3>3–5 day heat risk forecast</h3>
            <p>Projected thermal stress and mortality risk for {selected.name}</p>
          </div>

          <div>
            {[5, 3].map((n) => (
              <button
                className={"toggle " + (days === n ? "active" : "")}
                onClick={() => setDays(n)}
                key={n}
              >
                {n} days
              </button>
            ))}
          </div>
        </div>

        {/* One card per forecast day, trimmed to the selected range (3 or 5). */}
        <div className="forecast-grid">
          {cityForecast.slice(0, days).map((f) => (
            <div className="forecast-card" key={f.day}>
              <small>{f.day}</small>
              <strong>{f.temp}°</strong>
              <span>UTCI {f.utci}°C</span>
              <Badge risk={f.risk}>MRI {f.mri}</Badge>
            </div>
          ))}
        </div>

        {/* Line chart of Mortality Risk Index across the forecast period. */}
        <div className="chart">
          <ResponsiveContainer width="100%" height={190}>
            <LineChart data={cityForecast}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="day" />
              <YAxis />
              <Tooltip />
              <Line type="monotone" dataKey="mri" stroke="#f97316" strokeWidth={3} dot={{ r: 4 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    );
  }

  // Alert composer + alert history, for dispatching public health advisories.
  function AlertPanel() {
    return (
      <div className="alert-layout">
        <section className="card panel">
          <div className="panel-head">
            <div>
              <h3>Create public health advisory</h3>
              <p>Dispatch targeted alerts to affected zones.</p>
            </div>
          </div>

          <label>Target zones</label>
          <select>
            <option>All high-risk zones</option>
            {zones.map((z) => (
              <option key={z.id}>{z.name}</option>
            ))}
          </select>

          <label>Message template</label>
          <textarea value={message} onChange={(e) => setMessage(e.target.value)} />

          <label>Delivery channels</label>
          <div className="channels">
            {["SMS", "WhatsApp", "Dashboard"].map((x) => (
              <button key={x} className="channel active">
                {x}
              </button>
            ))}
          </div>

          {/* Demo "send" action: flips a success flag for 3 seconds, no real dispatch. */}
          <button
            className="primary"
            onClick={() => {
              setSent(true);
              setTimeout(() => setSent(false), 3000);
            }}
          >
            {sent ? "✓ Advisory queued" : "Send advisory"}
          </button>
          {sent && <div className="success">Advisory queued successfully (demo).</div>}
        </section>

        {/* Static placeholder history — not wired to real data yet. */}
        <section className="card panel">
          <h3>Alert history</h3>
          <div className="history">
            <div>
              <b>Heat advisory · High-risk zones</b>
              <small>Today, 10:30 AM · SMS + Dashboard</small>
              <Badge risk="Orange">Sent</Badge>
            </div>
            <div>
              <b>Cooling centre preparation</b>
              <small>Yesterday, 4:15 PM · Municipal teams</small>
              <Badge risk="Yellow">Completed</Badge>
            </div>
          </div>
        </section>
      </div>
    );
  }

  // Analytics tab: risk distribution bar chart + a few headline indicators.
  function Analytics() {
    // --- Derived indicators (computed from live/demo `zones`, not hardcoded) ---

    // Highest UTCI reading across all cities right now.
    const validUtcis = zones.map((z) => z.utci).filter((v) => Number.isFinite(v));
    const highestUtci = validUtcis.length ? Math.max(...validUtcis).toFixed(1) + "°C" : "N/A";

    // Cooling centres required: one recommended per high-risk (Orange/Red) city.
    // This is a simple heuristic, not a capacity-planning calculation.
    const highRiskCount = zones.filter((z) => z.risk === "Orange" || z.risk === "Red").length;
    const coolingCentresRequired = highRiskCount;

    // Population exposed: sum of each zone's `population` field, scoped to
    // cities currently at Orange/Red risk. Falls back to "N/A" if the data
    // doesn't include population figures, since we won't fabricate a number.
    const hasPopulationData = zones.some((z) => Number.isFinite(z.population));
    const populationExposed = hasPopulationData
      ? zones
          .filter((z) => z.risk === "Orange" || z.risk === "Red")
          .reduce((sum, z) => sum + (z.population || 0), 0)
      : null;

    // Historical excess mortality: needs a historical dataset we don't currently
    // have in `zones` (e.g. z.excessMortality). Shown as "N/A" until that field exists.
    const hasMortalityData = zones.some((z) => Number.isFinite(z.excessMortality));
    const excessMortality = hasMortalityData
      ? (zones.reduce((sum, z) => sum + (z.excessMortality || 0), 0) / zones.length).toFixed(0) + "%"
      : null;

    // Formats a raw population count as e.g. "6.6L" (lakhs) for compact display.
    function formatPopulation(n) {
      if (n === null) return "N/A";
      return n >= 100000 ? (n / 100000).toFixed(1) + "L" : n.toLocaleString();
    }

    return (
      <div className="analytics-grid">
        <section className="card panel">
          <h3>Risk distribution</h3>
          <p className="muted">Current ward classification</p>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={Object.entries(riskCounts).map(([risk, count]) => ({ risk, count }))}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="risk" />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="count" fill="#f97316" radius={[5, 5, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </section>

        <section className="card panel">
          <h3>City indicators</h3>
          <div className="big-indicator">
            <span>Population exposed</span>
            <b>{formatPopulation(populationExposed)}</b>
          </div>
          <div className="big-indicator">
            <span>Highest UTCI</span>
            <b>{highestUtci}</b>
          </div>
          <div className="big-indicator">
            <span>Historical excess mortality</span>
            <b>{excessMortality ?? "N/A"}</b>
          </div>
          <div className="big-indicator">
            <span>Cooling centres required</span>
            <b>{coolingCentresRequired}</b>
          </div>
        </section>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // Top-level layout: header, sidebar nav, and the active tab's content
  // -------------------------------------------------------------------------

  return (
    <div className="shell">
      {/* Top header: brand, live/demo status, city picker, avatar. */}
      <header className="header">
        <div className="brand">
          <div className="logo">☀</div>
          <div>
            <h1>Heatwave Early Warning System</h1>
            <p>Municipal climate intelligence and response platform</p>
          </div>
        </div>

        <div className="header-right">
          <span className="live">
            <i />
            {dataStatus === "live" ? "Live data" : "Demo data"}
          </span>

          <select
            value={selected.name}
            onChange={(event) => {
              const zone = zones.find((item) => item.name === event.target.value);
              if (zone) setSelected(zone);
            }}
          >
            {zones.map((zone) => (
              <option key={zone.id}>{zone.name}</option>
            ))}
          </select>

          <button className="icon-btn">⚙</button>
          <div className="avatar">AD</div>
        </div>
      </header>

      <div className="layout">
        {/* Left sidebar navigation between the five tabs. */}
        <aside className="sidebar">
          <div className="side-label">MAIN MENU</div>
          {[
            ["overview", "▦", "Overview"],
            ["map", "⌖", "Risk map"],
            ["forecast", "◴", "Forecast"],
            ["alerts", "♢", "Alert centre"],
            ["analytics", "▥", "Analytics"],
          ].map(([id, ic, label]) => (
            <button className={tab === id ? "nav active" : "nav"} onClick={() => setTab(id)} key={id}>
              <span>{ic}</span>
              {label}
            </button>
          ))}

          <div className="side-bottom">
            <div className="side-label">SYSTEM</div>
            <button className="nav">
              <span>?</span>Help & documentation
            </button>
            <button className="nav">
              <span>↪</span>Sign out
            </button>
          </div>
        </aside>

        {/* Main content area: breadcrumb + title, then the active tab. */}
        <main className="content">
          <div className="crumb">
            Dashboard / <b>{tab[0].toUpperCase() + tab.slice(1)}</b>
          </div>

          <div className="title-row">
            <div>
              <h2>
                {tab === "overview"
                  ? "City heat risk overview"
                  : tab === "map"
                  ? "Interactive risk map"
                  : tab === "forecast"
                  ? "Heat risk forecast"
                  : tab === "alerts"
                  ? "Alert centre"
                  : "Risk analytics"}
              </h2>
              <p>Monitor thermal stress, identify vulnerable zones, and coordinate heat action.</p>
              {dataStatus === "loading" && <p className="muted">Loading live heat-risk data…</p>}
              {dataError && <p className="muted">Live service unavailable — showing demonstration data.</p>}
            </div>

            <div className="date-box">
              ▣{" "}
              <span>
                {new Date().toLocaleDateString(undefined, {
                  weekday: "long",
                  day: "numeric",
                  month: "long",
                  year: "numeric",
                })}
              </span>
            </div>
          </div>

          {/* --- Overview tab: stat cards + map + city list + details/forecast --- */}
          {tab === "overview" && (
            <>
              <div className="stats">
                {[
                  ["Current UTCI", formatUtci(selected.utci), "Live reading for " + selected.name, "orange"],
                  ["Mortality Risk Index", selected.mri, selected.risk + " · adjusted risk", "red"],
                  [
                    "High-risk cities",
                    zones.filter((z) => z.risk === "Orange" || z.risk === "Red").length,
                    "Require immediate review",
                    "blue",
                  ],
                  [
                    "Healthcare capacity",
                    selected.healthcare + "%",
                    "Available beds · " + selected.name,
                    "green",
                  ],
                ].map((x) => (
                  <div className={"stat " + x[3]} key={x[0]}>
                    <small>{x[0]}</small>
                    <strong>{x[1]}</strong>
                    <span>{x[2]}</span>
                  </div>
                ))}
              </div>

              <div className="grid">
                <div className="wide">
                  <MapPanel />
                </div>

                <div className="card panel">
                  <div className="panel-head">
                    <div>
                      <h3>City risk summary</h3>
                      <p>Ranked by adjusted heat-health risk</p>
                    </div>
                    <span className="muted">{zones.length} cities</span>
                  </div>

                  <input
                    className="search"
                    placeholder="Search city..."
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                  />

                  <div className="zone-list">
                    {filtered.map((z) => (
                      <button
                        className={"zone-row " + (selected.id === z.id ? "selected" : "")}
                        onClick={() => setSelected(z)}
                        key={z.id}
                      >
                        <span>
                          <b>{z.name}</b>
                          <small>
                            UTCI {formatUtci(z.utci)} · MRI {z.mri}
                          </small>
                        </span>
                        <Badge risk={z.risk}>{z.risk}</Badge>
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="grid lower">
                <Details />
                <ForecastPanel />
              </div>
            </>
          )}

          {/* --- Other tabs: each renders its own dedicated panel --- */}
          {tab === "map" && <MapPanel full />}
          {tab === "forecast" && (
            <div className="card panel">
              <ForecastPanel />
            </div>
          )}
          {tab === "alerts" && <AlertPanel />}
          {tab === "analytics" && <Analytics />}
        </main>
      </div>

      <footer>
        Extreme Heatwave Early Warning System{" "}
        <span>
          {dataStatus === "live"
            ? "Live API data · " + zones.length + " monitored cities"
            : "Demonstration data (API unavailable)"}
        </span>
      </footer>
    </div>
  );
}

export default App;