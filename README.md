# Sentinel EO Data Explorer

A web application for searching, viewing, and downloading Sentinel-2 satellite imagery from the Copernicus Data Space Ecosystem (CDSE). Draw an area of interest on an interactive map, filter by date range and cloud cover, preview true-color imagery directly on the map, and download high-resolution satellite images as PNG files.

Built as a prototype for **Challenge 1 — Sentinel EO Data Explorer**.

---

## Features

- **Interactive Map** — Leaflet.js map centered on Riyadh with drawing tools for selecting an area of interest (AOI)
- **Catalogue Search** — Queries the CDSE STAC API for Sentinel-2 Level-2A scenes matching your AOI, date/time range, and cloud cover threshold
- **Thumbnail Previews** — Each result card shows a thumbnail, scene ID, mission, instrument, sensing time, and cloud cover percentage
- **Map Overlay** — Click "Visualise" to display the true-color satellite imagery directly on the map via Sentinel Hub WMS
- **Direct Download** — Click "Download" to save a 1024×1024 PNG of the satellite image for your AOI
- **Date & Time Filtering** — Specify both date and time for precise temporal searches

---

## Project Structure

```
sentinel-eo-explorer/
├── backend/
│   ├── main.py            # FastAPI server (search, tile, download endpoints)
│   ├── config.py          # Loads credentials from .env
│   ├── requirements.txt   # Python dependencies
│   ├── .env.example       # Template for credentials (copy to .env)
│   └── .env               # Your actual credentials (DO NOT COMMIT)
├── frontend/
│   ├── index.html         # Main page layout
│   ├── style.css          # Styling
│   └── app.js             # Frontend logic (map, search, display, download)
├── .gitignore
└── README.md
```

---

## Prerequisites

- **Python 3.10+** installed
- **Node.js** (optional, only if you want to use npm-based tools)
- A **CDSE account** — register free at https://dataspace.copernicus.eu
- A **Sentinel Hub OAuth client** and **Configuration** — set up at https://shapps.dataspace.copernicus.eu/dashboard/
- A simple local web server for the frontend (e.g., VS Code Live Server extension, or Python's `http.server`)

---

## Setup Instructions

### 1. Clone the repository

```bash
git clone https://github.com/YOUR-USERNAME/sentinel-eo-explorer.git
cd sentinel-eo-explorer
```

### 2. Set up CDSE credentials

Copy the example environment file and fill in your real credentials:

```bash
cd backend
cp .env.example .env
```

Edit `.env` with your details:

```
CDSE_USERNAME=your-cdse-email@example.com
CDSE_PASSWORD=your-cdse-password
SH_CLIENT_ID=your-sentinel-hub-client-id
SH_CLIENT_SECRET=your-sentinel-hub-client-secret
SH_INSTANCE_ID=your-sentinel-hub-instance-id
```

**Where to get these values:**

| Credential | Where to find it |
|---|---|
| `CDSE_USERNAME` / `CDSE_PASSWORD` | Your Copernicus Data Space account login (https://dataspace.copernicus.eu) |
| `SH_CLIENT_ID` / `SH_CLIENT_SECRET` | Sentinel Hub Dashboard → User Settings → OAuth Clients → create a new client |
| `SH_INSTANCE_ID` | Sentinel Hub Dashboard → Configuration Utility → create a configuration with a TRUE_COLOR layer → copy the Instance ID from the URL |

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Start the backend server

```bash
uvicorn main:app --reload
```

The API will be running at `http://localhost:8000`. You can verify by visiting `http://localhost:8000/api/health` — it should return `{"status": "ok"}`.

### 5. Start the frontend

Open the `frontend/` folder in VS Code and launch it with the Live Server extension (right-click `index.html` → "Open with Live Server").

Or use Python's built-in server:

```bash
cd ../frontend
python -m http.server 5500
```

Then open `http://localhost:5500` in your browser.

---

## How to Use

1. **Draw an AOI** — Use the rectangle or polygon tool (top-left of the map) to draw your area of interest
2. **Set filters** — Choose your start/end date and time, and adjust the max cloud cover slider
3. **Search** — Click "Search Imagery" to query the CDSE catalogue
4. **Browse results** — Scroll through the result cards showing thumbnails, metadata, and cloud cover
5. **Visualise** — Click the "Visualise" button on any card to overlay the satellite imagery on the map
6. **Download** — Click the "Download" button to save a high-resolution PNG of that scene

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/search` | Search CDSE STAC catalogue for Sentinel-2 scenes |
| `GET` | `/api/tile` | Get Sentinel Hub WMS parameters for map overlay |
| `GET` | `/api/download` | Download a satellite image as a PNG file |

---

## Technologies Used

- **Backend:** Python, FastAPI, Uvicorn, Requests
- **Frontend:** HTML, CSS, JavaScript, Leaflet.js, Leaflet Draw
- **APIs:** CDSE STAC API (catalogue search), Sentinel Hub WMS (image rendering)
- **Authentication:** OAuth2 (password grant for STAC, client credentials for Sentinel Hub)

---

## Troubleshooting

**"Search failed" or "Failed to obtain CDSE token"**
→ Check that your `CDSE_USERNAME` and `CDSE_PASSWORD` in `.env` are correct.

**No satellite imagery on the map after clicking Visualise**
→ Make sure you created a Sentinel Hub Configuration with a `TRUE_COLOR` layer in the Dashboard, and that `SH_INSTANCE_ID` in `.env` matches.

**"Tile load error" in the status bar**
→ Your Sentinel Hub OAuth client credentials (`SH_CLIENT_ID` / `SH_CLIENT_SECRET`) may be incorrect. Verify them in the Dashboard.

**Directory listing instead of the app**
→ Make sure you're opening `localhost:5500/frontend/` (not the project root), or launch Live Server from inside the `frontend/` folder.

---

## Security Note

The `.env` file contains sensitive credentials and is excluded from version control via `.gitignore`. Never commit or share this file. Anyone cloning this repository must create their own `.env` from `.env.example` using their own CDSE account.
