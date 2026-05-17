import logging
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN
from .dahua_rpc import DahuaRPC

_LOGGER = logging.getLogger(__name__)

# Add "camera" to your existing PLATFORMS list
PLATFORMS = ["switch", "select", "button", "number", "camera"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Dahua RPC Control from a config entry."""
    
    # Initialize our API client
    client = DahuaRPC(
        host=entry.data[CONF_HOST],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
    )

    # Store the client in Home Assistant's global memory so the switches can access it
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = client

    # Tell Home Assistant to load switch.py, select.py, and button.py
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register our custom service for setting the Video Analyse Type
    async def handle_set_video_analyse_type(call: ServiceCall):
        analyse_type = call.data.get("type", "")
        # Loop through all configured cameras and apply the setting
        for client_instance in hass.data[DOMAIN].values():
            await hass.async_add_executor_job(
                client_instance.set_video_analyse_type,
                analyse_type,
            )

    if not hass.services.has_service(DOMAIN, "set_video_analyse_type"):
        hass.services.async_register(
            DOMAIN,
            "set_video_analyse_type",
            handle_set_video_analyse_type,
            schema=vol.Schema({
                vol.Optional("type", default=""): cv.string,
            }),
        )

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry when the user removes the integration."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok