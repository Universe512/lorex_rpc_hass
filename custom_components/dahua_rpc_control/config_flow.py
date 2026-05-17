import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD
from homeassistant.components import ssdp

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

class DahuaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Dahua/Lorex RPC Control."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self.discovery_ip = None
        self.discovery_name = None

    async def async_step_user(self, user_input=None):
        """Handle the standard manual 'Add Integration' setup."""
        errors = {}

        if user_input is not None:
            return self.async_create_entry(title=user_input[CONF_HOST], data=user_input)

        # Use vol.UNDEFINED for no default value to prevent HA frontend glitches
        host_default = self.discovery_ip if self.discovery_ip else vol.UNDEFINED

        data_schema = vol.Schema({
            vol.Required(CONF_HOST, default=host_default): str,
            vol.Required(CONF_USERNAME, default="admin"): str,
            vol.Required(CONF_PASSWORD): str,
        })

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    async def async_step_ssdp(self, discovery_info: ssdp.SsdpServiceInfo):
        """Handle a discovered Dahua/Lorex camera via SSDP broadcast."""
        
        # Extract the IP address from the discovery URL (e.g. http://192.168.1.100:80/)
        parsed_url = discovery_info.ssdp_location.split("//")
        if len(parsed_url) > 1:
            ip_address = parsed_url[1].split(":")[0]
        else:
            return self.async_abort(reason="invalid_discovery_info")
            
        self.discovery_ip = ip_address
        self.discovery_name = discovery_info.upnp.get(ssdp.ATTR_UPNP_FRIENDLY_NAME, "Dahua/Lorex Camera")

        # Check if we already configured this IP to prevent annoying duplicate popups!
        await self.async_set_unique_id(self.discovery_ip)
        self._abort_if_unique_id_configured()

        # Set placeholders so Home Assistant shows the Camera's name in the UI
        self.context["title_placeholders"] = {
            "name": self.discovery_name,
            "ip": self.discovery_ip,
        }

        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(self, user_input=None):
        """Prompt the user for credentials when a camera is automatically discovered."""
        errors = {}

        if user_input is not None:
            # We already know the IP from the auto-discovery, so inject it into the final save data
            user_input[CONF_HOST] = self.discovery_ip
            title = f"{self.discovery_name} ({self.discovery_ip})"
            return self.async_create_entry(title=title, data=user_input)

        # The popup will ONLY ask for username and password, skipping the IP field
        data_schema = vol.Schema({
            vol.Required(CONF_USERNAME, default="admin"): str,
            vol.Required(CONF_PASSWORD): str,
        })

        return self.async_show_form(
            step_id="discovery_confirm",
            data_schema=data_schema,
            description_placeholders={"name": self.discovery_name, "ip": self.discovery_ip},
            errors=errors
        )