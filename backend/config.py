import os
from dotenv import load_dotenv

load_dotenv()

CDSE_USERNAME = os.getenv("CDSE_USERNAME", "your-email@example.com")
CDSE_PASSWORD = os.getenv("CDSE_PASSWORD", "your-password")

SH_CLIENT_ID = os.getenv("SH_CLIENT_ID", "your-client-id")
SH_CLIENT_SECRET = os.getenv("SH_CLIENT_SECRET", "your-client-secret")
SH_INSTANCE_ID = os.getenv("SH_INSTANCE_ID", "your-instance-id")

TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu"
    "/auth/realms/CDSE/protocol/openid-connect/token"
)
STAC_SEARCH_URL = "https://stac.dataspace.copernicus.eu/v1/search"
SH_WMS_BASE = f"https://sh.dataspace.copernicus.eu/ogc/wms/{SH_INSTANCE_ID}"