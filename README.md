# Heatwave Early Warning System — Frontend V2

## Run
npm install
npm run dev

## Included
- Responsive municipal dashboard
- Sidebar navigation
- Leaflet map with risk, vulnerability and healthcare layers
- Zone selection and detailed metrics
- 3–5 day forecast with chart
- Analytics chart
- Alert centre
- Mock data and backend-ready structure

## Replace mock data
Edit `src/data.js` and connect your backend endpoints:
GET /api/thermal-stress
POST /api/forecast
POST /api/alert-dispatch
GET /api/dashboard-data

All current values are illustrative mock data.