"""
main.py — FastAPI backend for the Sentinel EO Data Explorer.

Endpoints:
  POST /api/search    → Search the CDSE STAC catalogue for Sentinel-2 scenes
  GET  /api/tile      → Return a Sentinel Hub WMS tile URL for a given scene
  GET  /api/download  → Download a high-res satellite image as PNG
  GET  /api/health    → Simple health check
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
import requests
import time

from config import (
    CDSE_USERNAME,
    CDSE_PASSWORD,
    SH_CLIENT_ID,
    SH_CLIENT_SECRET,
    TOKEN_URL,
    STAC_SEARCH_URL,
    SH_WMS_BASE,
)

# ── FastAPI App Setup ─────────────────────────────────────────────────

app = FastAPI(
    title="Sentinel EO Data Explorer API",
    description="Backend for searching and visualizing Sentinel-2 imagery",
    version="1.0.0",
)

# Allow the frontend (served from a different port) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Token Caches ─────────────────────────────────────────────────────
# We cache tokens so we don't request new ones on every call.

# 1) CDSE STAC catalogue token (password grant)
_token_cache = {
    "access_token": None,
    "expires_at": 0,              # Unix timestamp when token expires
}

# 2) Sentinel Hub WMS token (client-credentials grant)
_sh_token_cache = {
    "access_token": None,
    "expires_at": 0,
}


def get_cdse_token() -> str:
    """
    Obtain an OAuth2 access token from CDSE using the password grant.
    Used for the STAC catalogue search.
    The token is cached and refreshed automatically when it expires.
    """
    now = time.time()

    # Return cached token if it's still valid (with 30-second buffer)
    if _token_cache["access_token"] and now < _token_cache["expires_at"] - 30:
        return _token_cache["access_token"]

    # Request a new token
    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": "cdse-public",
            "grant_type": "password",
            "username": CDSE_USERNAME,
            "password": CDSE_PASSWORD,
        },
        timeout=30,
    )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to obtain CDSE token: {response.text}",
        )

    token_data = response.json()
    _token_cache["access_token"] = token_data["access_token"]
    # Token typically expires in 600 seconds (10 minutes)
    _token_cache["expires_at"] = now + token_data.get("expires_in", 600)

    return _token_cache["access_token"]


def get_sh_token() -> str:
    """
    Obtain an OAuth2 access token for Sentinel Hub WMS using the
    client-credentials grant (SH_CLIENT_ID + SH_CLIENT_SECRET).
    This token is REQUIRED for every WMS tile request on CDSE.
    """
    now = time.time()

    if _sh_token_cache["access_token"] and now < _sh_token_cache["expires_at"] - 30:
        return _sh_token_cache["access_token"]

    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": SH_CLIENT_ID,
            "client_secret": SH_CLIENT_SECRET,
            "grant_type": "client_credentials",
        },
        timeout=30,
    )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to obtain Sentinel Hub token: {response.text}",
        )

    token_data = response.json()
    _sh_token_cache["access_token"] = token_data["access_token"]
    _sh_token_cache["expires_at"] = now + token_data.get("expires_in", 600)

    return _sh_token_cache["access_token"]


# ── Request / Response Models ─────────────────────────────────────────

class SearchRequest(BaseModel):
    """
    The search parameters sent by the frontend.

    bbox: [west, south, east, north] in EPSG:4326 (WGS84)
    start_date: ISO 8601 datetime string, e.g. "2024-07-01T00:00:00Z"
    end_date: ISO 8601 datetime string, e.g. "2024-07-31T23:59:59Z"
    max_cloud: Maximum cloud cover percentage (0-100)
    """
    bbox: list[float] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="Bounding box [west, south, east, north]",
    )
    start_date: str = Field(..., description="Start datetime (ISO 8601)")
    end_date: str = Field(..., description="End datetime (ISO 8601)")
    max_cloud: float = Field(
        default=20.0,
        ge=0,
        le=100,
        description="Maximum cloud cover percentage",
    )


class SceneResult(BaseModel):
    """One scene returned by the search."""
    scene_id: str
    datetime: str
    cloud_cover: float
    platform: str
    instrument: str = "MSI"
    file_size_mb: Optional[float] = None
    thumbnail_url: Optional[str] = None
    download_url: Optional[str] = None
    footprint: dict            # GeoJSON geometry


# ── API Endpoints ─────────────────────────────────────────────────────

@app.get("/api/health")
def health_check():
    """Simple health check to verify the server is running."""
    return {"status": "ok"}


@app.post("/api/search", response_model=list[SceneResult])
def search_scenes(req: SearchRequest):
    """
    Search the CDSE STAC catalogue for Sentinel-2 L2A scenes
    matching the given bounding box, date range, and cloud filter.
    """
    token = get_cdse_token()

    # Normalise the datetime strings coming from the frontend.
    # The frontend sends "YYYY-MM-DDTHH:MM" (from datetime-local input).
    # The STAC API expects full ISO 8601 with timezone.
    start_dt = req.start_date
    if not start_dt.endswith("Z") and "+" not in start_dt:
        start_dt = start_dt + ":00Z" if start_dt.count(":") == 1 else start_dt + "Z"
    end_dt = req.end_date
    if not end_dt.endswith("Z") and "+" not in end_dt:
        end_dt = end_dt + ":00Z" if end_dt.count(":") == 1 else end_dt + "Z"

    # Build the STAC search request body
    stac_body = {
        "collections": ["sentinel-2-l2a"],
        "bbox": req.bbox,                        # [west, south, east, north]
        "datetime": f"{start_dt}/{end_dt}",
        "limit": 50,                             # Max results per page
        "filter": {
            "op": "<=",
            "args": [
                {"property": "eo:cloud_cover"},
                req.max_cloud,
            ],
        },
        "filter-lang": "cql2-json",
        # Request the fields we need (including download asset)
        "fields": {
            "include": [
                "id",
                "type",
                "geometry",
                "properties.datetime",
                "properties.eo:cloud_cover",
                "properties.platform",
                "properties.instrument",
                "properties.s2:product_type",
                "assets.thumbnail",
                "assets.product",
            ]
        },
    }

    # Send the search request to the STAC API
    response = requests.post(
        STAC_SEARCH_URL,
        json=stac_body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        timeout=30,
    )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"STAC API error: {response.status_code} - {response.text}",
        )

    data = response.json()

    # Parse each STAC Feature into our clean SceneResult model
    results = []
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        assets = feature.get("assets", {})

        # Extract thumbnail URL if available
        thumb = assets.get("thumbnail", {}).get("href")

        # Extract download URL — try several asset keys the STAC API may use
        product_asset = (
            assets.get("product", {})
            or assets.get("download", {})
            or assets.get("data", {})
        )
        download_href = product_asset.get("href") if product_asset else None

        # Also check the feature's "links" array for a download link
        if not download_href:
            for link in feature.get("links", []):
                if link.get("rel") in ("derived_from", "alternate", "enclosure"):
                    download_href = link.get("href")
                    break

        # Last resort: build the CDSE Zipper download URL from the scene ID.
        # The CDSE OData download endpoint uses the feature's collection+id.
        # This URL will prompt the user to log in to CDSE before downloading.
        if not download_href:
            download_href = (
                f"https://browser.dataspace.copernicus.eu/"
                f"?zoom=10&lat=24.7&lng=46.7"
                f"&themeId=DEFAULT-THEME&datasetId=S2_L2A_CDAS"
                f"&fromTime={props.get('datetime', '')[:10]}T00:00:00.000Z"
                f"&toTime={props.get('datetime', '')[:10]}T23:59:59.999Z"
            )

        # Estimate file size in MB from product asset if available
        file_bytes = (product_asset or {}).get("file:size")
        file_size_mb = round(file_bytes / (1024 * 1024), 0) if file_bytes else None

        results.append(
            SceneResult(
                scene_id=feature.get("id", "unknown"),
                datetime=props.get("datetime", ""),
                cloud_cover=props.get("eo:cloud_cover", -1),
                platform=props.get("platform", "unknown"),
                instrument=props.get("instrument", "MSI"),
                file_size_mb=file_size_mb,
                thumbnail_url=thumb,
                download_url=download_href,
                footprint=feature.get("geometry", {}),
            )
        )

    # Sort by date (most recent first)
    results.sort(key=lambda s: s.datetime, reverse=True)

    return results


@app.get("/api/tile")
def get_tile_url(
    scene_id: str,
    bbox: str,
    date: str,
):
    """
    Build and return a Sentinel Hub WMS URL that the frontend can use
    as a Leaflet TileLayer to display the selected scene on the map.

    Parameters:
      scene_id: The STAC scene ID (for reference / logging)
      bbox: Comma-separated bounding box "west,south,east,north"
      date: Acquisition date "YYYY-MM-DD"
    """
    # Get a fresh Sentinel Hub token — REQUIRED for WMS on CDSE
    sh_token = get_sh_token()

    # Construct the WMS GetMap URL for a preview image
    wms_url = (
        f"{SH_WMS_BASE}"
        f"?SERVICE=WMS"
        f"&REQUEST=GetMap"
        f"&LAYERS=TRUE_COLOR"
        f"&BBOX={bbox}"
        f"&CRS=EPSG:4326"
        f"&WIDTH=512"
        f"&HEIGHT=512"
        f"&FORMAT=image/png"
        f"&TIME={date}/{date}"
        f"&MAXCC=100"
    )

    # Also build a Leaflet-compatible WMS base URL
    leaflet_wms_base = SH_WMS_BASE

    return {
        "scene_id": scene_id,
        "date": date,
        "preview_url": wms_url,
        "wms_base_url": leaflet_wms_base,
        "sh_token": sh_token,           # ← Frontend needs this for auth
        "wms_params": {
            "layers": "TRUE_COLOR",
            "format": "image/png",
            "time": f"{date}/{date}",
            "maxcc": 100,
            "crs": "EPSG:4326",
        },
    }


@app.get("/api/download")
def download_image(
    scene_id: str,
    bbox: str,
    date: str,
    width: int = 1024,
    height: int = 1024,
):
    """
    Fetch a high-resolution satellite image from Sentinel Hub WMS
    and return it as a downloadable PNG file.

    Parameters:
      scene_id: The STAC scene ID (used for the filename)
      bbox: Comma-separated bounding box "west,south,east,north"
      date: Acquisition date "YYYY-MM-DD"
      width: Image width in pixels (default 1024)
      height: Image height in pixels (default 1024)
    """
    sh_token = get_sh_token()

    # Build the WMS GetMap request URL
    wms_url = (
        f"{SH_WMS_BASE}"
        f"?SERVICE=WMS"
        f"&REQUEST=GetMap"
        f"&LAYERS=TRUE_COLOR"
        f"&BBOX={bbox}"
        f"&CRS=EPSG:4326"
        f"&WIDTH={width}"
        f"&HEIGHT={height}"
        f"&FORMAT=image/png"
        f"&TIME={date}/{date}"
        f"&MAXCC=100"
        f"&token={sh_token}"
    )

    # Fetch the image from Sentinel Hub
    try:
        img_response = requests.get(wms_url, timeout=60)
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch image: {e}")

    if img_response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Sentinel Hub returned {img_response.status_code}",
        )

    # Build a clean filename from the scene ID and date
    safe_name = scene_id.replace("/", "_").replace("\\", "_")
    filename = f"{safe_name}_{date}.png"

    # Return the image as a downloadable file
    return Response(
        content=img_response.content,
        media_type="image/png",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


# ── Run with: uvicorn main:app --reload ───────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)