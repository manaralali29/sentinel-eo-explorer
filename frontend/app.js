/**
 * app.js — Frontend logic for the Sentinel EO Data Explorer.
 *
 * Responsibilities:
 *   1. Initialize the Leaflet map with drawing tools
 *   2. Capture the drawn AOI bounding box
 *   3. Send search requests to the FastAPI backend
 *   4. Display results with thumbnails in the sidebar
 *   5. Overlay selected scenes onto the map via WMS
 */

// ── Configuration ────────────────────────────────────────────────────
const API_BASE = "http://localhost:8000";   // Your FastAPI backend

// ── State ────────────────────────────────────────────────────────────
let currentBBox = null;           // [west, south, east, north]
let currentOverlay = null;        // Active WMS tile layer on the map
let drawnItems = null;            // Leaflet FeatureGroup for drawn shapes
let footprintLayer = null;        // GeoJSON layer showing scene footprint
let lastSearchResults = [];       // Cache of last search results for onclick

// ── Map Initialization ──────────────────────────────────────────────
// Center the map on Riyadh, Saudi Arabia (adjust to your region)
const map = L.map("map").setView([24.7, 46.7], 8);

// Add the OpenStreetMap base layer
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: "&copy; OpenStreetMap contributors",
  maxZoom: 18,
}).addTo(map);

// ── Drawing Tools (Leaflet Draw) ─────────────────────────────────────
// Create a feature group to store drawn shapes
drawnItems = new L.FeatureGroup();
map.addLayer(drawnItems);

// Add the draw control with only rectangle and polygon enabled
const drawControl = new L.Control.Draw({
  position: "topleft",
  draw: {
    rectangle: {
      shapeOptions: {
        color: "#0077cc",
        weight: 2,
        fillOpacity: 0.1,
      },
    },
    polygon: {
      shapeOptions: {
        color: "#0077cc",
        weight: 2,
        fillOpacity: 0.1,
      },
    },
    // Disable tools we don't need
    polyline: false,
    circle: false,
    circlemarker: false,
    marker: false,
  },
  edit: {
    featureGroup: drawnItems,
    remove: true,
  },
});
map.addControl(drawControl);

// ── Handle Draw Events ───────────────────────────────────────────────

map.on(L.Draw.Event.CREATED, function (event) {
  // Clear any previously drawn shape
  drawnItems.clearLayers();

  // Add the new shape to the map
  const layer = event.layer;
  drawnItems.addLayer(layer);

  // Extract the bounding box from the drawn shape
  const bounds = layer.getBounds();
  currentBBox = [
    bounds.getWest(),   // west  (min longitude)
    bounds.getSouth(),  // south (min latitude)
    bounds.getEast(),   // east  (max longitude)
    bounds.getNorth(),  // north (max latitude)
  ];

  // Enable the search button now that we have an AOI
  document.getElementById("search-btn").disabled = false;
  setStatus("AOI selected. Ready to search.", false);
});

map.on(L.Draw.Event.DELETED, function () {
  currentBBox = null;
  document.getElementById("search-btn").disabled = true;
  setStatus("AOI removed. Draw a new area to search.", false);
});

// ── Search Button Handler ────────────────────────────────────────────

document.getElementById("search-btn").addEventListener("click", async () => {
  if (!currentBBox) {
    setStatus("Please draw an area of interest on the map first.", true);
    return;
  }

  // Gather form values — datetime-local gives "YYYY-MM-DDTHH:MM"
  const startDate = document.getElementById("start-date").value;
  const endDate = document.getElementById("end-date").value;
  const maxCloud = parseFloat(document.getElementById("max-cloud").value);

  // Validate dates
  if (!startDate || !endDate) {
    setStatus("Please select both start and end dates.", true);
    return;
  }

  if (startDate > endDate) {
    setStatus("Start date must be before end date.", true);
    return;
  }

  // Show loading state
  setStatus("Searching CDSE catalogue...", false);
  document.getElementById("search-btn").disabled = true;

  try {
    // Call the FastAPI backend
    const response = await fetch(`${API_BASE}/api/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        bbox: currentBBox,
        start_date: startDate,
        end_date: endDate,
        max_cloud: maxCloud,
      }),
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || "Search failed");
    }

    const scenes = await response.json();
    lastSearchResults = scenes;       // Cache for onclick handlers
    displayResults(scenes);
    setStatus(`Found ${scenes.length} scene(s).`, false);
  } catch (error) {
    setStatus(`Error: ${error.message}`, true);
  } finally {
    document.getElementById("search-btn").disabled = false;
  }
});

// ── Display Results in the Sidebar ───────────────────────────────────

function displayResults(scenes) {
  const container = document.getElementById("results-list");

  // Handle no results
  if (scenes.length === 0) {
    container.innerHTML =
      '<p class="placeholder">No scenes found. Try widening your date range or increasing cloud cover tolerance.</p>';
    return;
  }

  // Build a card for each scene (with thumbnail, metadata, actions)
  container.innerHTML = scenes
    .map((scene, index) => {
      // Sensing time
      const sensingTime = scene.datetime || "N/A";

      // Cloud cover badge colour
      const cloudClass =
        scene.cloud_cover <= 20
          ? "cloud-low"
          : scene.cloud_cover <= 50
          ? "cloud-medium"
          : "cloud-high";

      // File size string
      const sizeStr = scene.file_size_mb
        ? `Size: ${scene.file_size_mb}MB`
        : "";

      // Thumbnail HTML
      const thumbHtml = scene.thumbnail_url
        ? `<img class="card-thumb" src="${scene.thumbnail_url}" alt="Thumbnail" onerror="this.outerHTML='<div class=\\'card-thumb-placeholder\\'>No preview</div>'" />`
        : `<div class="card-thumb-placeholder">No preview</div>`;

      // Download button — fetches a high-res PNG directly from our backend
      const dlDate = scene.datetime ? scene.datetime.split("T")[0] : "";
      const dlParams = new URLSearchParams({
        scene_id: scene.scene_id,
        bbox: currentBBox ? currentBBox.join(",") : "",
        date: dlDate,
      });
      const downloadBtn = `<a class="btn-download" href="${API_BASE}/api/download?${dlParams}" target="_blank" rel="noopener" onclick="event.stopPropagation();" title="Download satellite image as PNG">&#x2B07; Download</a>`;

      return `
        <div class="result-card" onclick="handleCardClick(${index})">
          ${thumbHtml}
          <div class="card-body">
            <div class="card-title">${scene.scene_id}</div>
            <div class="card-meta">
              <strong>Mission:</strong> ${scene.platform.toUpperCase()}
              &nbsp;&nbsp;<strong>Instrument:</strong> ${scene.instrument || "MSI"}
              ${sizeStr ? `&nbsp;&nbsp;<strong>${sizeStr}</strong>` : ""}
              <br/>
              <strong>Sensing time:</strong> ${sensingTime}
            </div>
            <div class="card-tags">
              <button class="btn-visualise" onclick="event.stopPropagation(); handleCardClick(${index})">Visualise</button>
              ${downloadBtn}
              <span class="tag">${scene.platform.toUpperCase()}</span>
              <span class="tag">${scene.instrument || "MSI"}</span>
              <span class="tag ${cloudClass}">${scene.cloud_cover.toFixed(1)}% cloud</span>
            </div>
          </div>
        </div>
      `;
    })
    .join("");
}

// ── Handle Card Click (safe — avoids inline JSON) ───────────────────

function handleCardClick(index) {
  const scene = lastSearchResults[index];
  if (scene) selectScene(scene);
}

// ── Select a Scene & Overlay on Map ──────────────────────────────────

async function selectScene(scene) {
  setStatus(`Loading imagery for ${scene.scene_id}...`, false);

  // Remove any existing overlay
  removeOverlay();

  // Extract the date (YYYY-MM-DD) from the full datetime string
  const acquisitionDate = scene.datetime.split("T")[0];

  try {
    // Ask the backend for the WMS URL parameters
    const params = new URLSearchParams({
      scene_id: scene.scene_id,
      bbox: currentBBox.join(","),
      date: acquisitionDate,
    });

    const response = await fetch(`${API_BASE}/api/tile?${params}`);
    if (!response.ok) throw new Error("Failed to get tile URL");

    const tileData = await response.json();

    // Add the Sentinel Hub WMS layer to the map
    // minZoom 10 prevents the "pixel size exceeds limit" error from
    // Sentinel Hub — S2 data can't be served at very low zoom levels.
    // The "token" parameter authenticates WMS requests on CDSE.
    currentOverlay = L.tileLayer.wms(tileData.wms_base_url, {
      layers: tileData.wms_params.layers,
      format: tileData.wms_params.format,
      time: tileData.wms_params.time,
      maxcc: tileData.wms_params.maxcc,
      token: tileData.sh_token,        // ← OAuth2 token for CDSE auth
      tileSize: 512,
      minZoom: 10,
      transparent: true,
      attribution: "&copy; Copernicus Sentinel Hub",
    });

    // Log tile errors to the status bar so we can debug without F12
    currentOverlay.on("tileerror", function (error) {
      console.error("WMS tile error:", error);
      setStatus("Tile load error — check console (F12) for details.", true);
    });

    currentOverlay.addTo(map);

    // Zoom the map into the drawn AOI so tiles load at a valid resolution
    const aoiBounds = L.latLngBounds(
      [currentBBox[1], currentBBox[0]],   // southwest: [south, west]
      [currentBBox[3], currentBBox[2]]    // northeast: [north, east]
    );
    map.fitBounds(aoiBounds, { maxZoom: 14 });

    // Show the scene footprint as a GeoJSON outline
    if (scene.footprint && scene.footprint.coordinates) {
      footprintLayer = L.geoJSON(scene.footprint, {
        style: {
          color: "#ff6600",
          weight: 2,
          fillOpacity: 0,
          dashArray: "5,5",
        },
      }).addTo(map);
    }

    // Show metadata in the sidebar
    showMetadata(scene);
    setStatus("Imagery loaded.", false);
  } catch (error) {
    setStatus(`Error loading imagery: ${error.message}`, true);
  }
}

// ── Show Metadata Panel ──────────────────────────────────────────────

function showMetadata(scene) {
  const panel = document.getElementById("metadata-panel");
  const tbody = document.querySelector("#metadata-table tbody");

  const dateObj = new Date(scene.datetime);

  tbody.innerHTML = `
    <tr><td>Scene ID</td><td style="word-break:break-all">${scene.scene_id}</td></tr>
    <tr><td>Date</td><td>${dateObj.toLocaleDateString()}</td></tr>
    <tr><td>Time (UTC)</td><td>${dateObj.toLocaleTimeString()}</td></tr>
    <tr><td>Cloud Cover</td><td>${scene.cloud_cover.toFixed(1)}%</td></tr>
    <tr><td>Platform</td><td>${scene.platform}</td></tr>
    <tr><td>Instrument</td><td>${scene.instrument || "MSI"}</td></tr>
    ${scene.file_size_mb ? `<tr><td>File Size</td><td>${scene.file_size_mb} MB</td></tr>` : ""}
    <tr><td>BBox (W,S,E,N)</td><td>${currentBBox.map(c => c.toFixed(3)).join(", ")}</td></tr>
  `;

  panel.style.display = "block";
}

// ── Remove Overlay ───────────────────────────────────────────────────

function removeOverlay() {
  if (currentOverlay) {
    map.removeLayer(currentOverlay);
    currentOverlay = null;
  }
  if (footprintLayer) {
    map.removeLayer(footprintLayer);
    footprintLayer = null;
  }
  document.getElementById("metadata-panel").style.display = "none";
}

document
  .getElementById("clear-overlay-btn")
  .addEventListener("click", removeOverlay);

// ── Utility: Status Message ──────────────────────────────────────────

function setStatus(message, isError) {
  const el = document.getElementById("status-message");
  el.textContent = message;
  el.className = isError ? "error" : "";
}