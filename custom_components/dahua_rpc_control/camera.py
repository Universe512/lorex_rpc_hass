import logging
import urllib.request
from urllib.error import HTTPError, URLError

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Set up Dahua camera from a config entry."""
    async_add_entities([DahuaRTSPCamera(entry)], update_before_add=True)

class DahuaRTSPCamera(Camera):
    """Representation of a Dahua/Lorex RTSP Camera."""

    def __init__(self, entry: ConfigEntry):
        """Initialize the camera."""
        super().__init__()
        self._entry = entry
        self._host = entry.data.get(CONF_HOST, "")
        self._username = entry.data.get(CONF_USERNAME, "")
        self._password = entry.data.get(CONF_PASSWORD, "")
        
        # Strip out "http://" and any HTTP ports (like :80) to get the raw IP address
        self._clean_host = self._host.replace("http://", "").replace("https://", "").split(":")[0]
        
        self._attr_name = "Camera Stream"
        self._attr_unique_id = f"{entry.entry_id}_camera_stream"
        
        # Tell Home Assistant this camera supports live streaming
        self._attr_supported_features = CameraEntityFeature.STREAM

    @property
    def device_info(self) -> DeviceInfo:
        """Link this entity back to the camera device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer="Dahua / Amcrest",
            model="RPC Camera/NVR",
        )

    async def stream_source(self) -> str:
        """Return the RTSP source URL for the live stream."""
        # Standard Dahua/Lorex RTSP format (Port 554, channel=1, subtype=0 for Main Stream)
        return f"rtsp://{self._username}:{self._password}@{self._clean_host}:554/cam/realmonitor?channel=1&subtype=0"

    def _fetch_snapshot(self) -> bytes | None:
        """Synchronously fetch a still image from the camera using its snapshot API."""
        try:
            base_url = f"http://{self._clean_host}"
            
            # Set up authentication for the HTTP snapshot endpoint
            passman = urllib.request.HTTPPasswordMgrWithDefaultRealm()
            passman.add_password(None, base_url, self._username, self._password)
            
            # Dahua cameras usually require Digest Auth, but Basic is a great fallback
            auth_handler = urllib.request.HTTPDigestAuthHandler(passman)
            basic_handler = urllib.request.HTTPBasicAuthHandler(passman)
            opener = urllib.request.build_opener(auth_handler, basic_handler)
            
            # The standard Dahua snapshot CGI endpoint (channel=1)
            url = f"{base_url}/cgi-bin/snapshot.cgi?channel=1"
            
            response = opener.open(url, timeout=10)
            return response.read()
            
        except HTTPError as err:
            _LOGGER.error("HTTP error fetching Dahua snapshot: %s %s", err.code, err.reason)
            return None
        except URLError as err:
            _LOGGER.error("URL error fetching Dahua snapshot: %s", err.reason)
            return None
        except Exception as err:
            _LOGGER.error("Failed to fetch Dahua snapshot: %s", err)
            return None

    async def async_camera_image(self, width: int | None = None, height: int | None = None) -> bytes | None:
        """Home Assistant calls this to get a snapshot image for the dashboard card."""
        return await self.hass.async_add_executor_job(self._fetch_snapshot)