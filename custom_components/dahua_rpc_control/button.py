import logging
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Set up Dahua buttons from a config entry."""
    client = hass.data[DOMAIN][entry.entry_id]
    
    buttons = [
        DahuaSirenButton(client, entry),
        DahuaActivateSirenButton(client, entry),
        DahuaSilenceSirenButton(client, entry),
        DahuaRebootButton(client, entry)
    ]
    
    async_add_entities(buttons, update_before_add=True)


class DahuaSirenButton(ButtonEntity):
    """Button to manually trigger the Siren using the safe CGI GET endpoint."""

    def __init__(self, client, entry):
        self._client = client
        self._entry = entry
        self._attr_name = "Quick Siren Trigger"
        self._attr_icon = "mdi:bullhorn-outline"
        self._attr_unique_id = f"{entry.entry_id}_trigger_siren"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer="Dahua / Amcrest",
            model="RPC Camera/NVR",
        )

    async def async_press(self) -> None:
        """Handle the button press to start the siren using IOState 1."""
        try:
            _LOGGER.info("Triggering Dahua Siren via CGI (ON)")
            await self.hass.async_add_executor_job(
                self._client.control_coaxial_cgi, 1
            )
        except Exception as err:
            _LOGGER.error("Failed to trigger siren: %s", err)


class DahuaActivateSirenButton(ButtonEntity):
    """Smart Button that directly fires the siren safely via the CGI endpoint."""

    def __init__(self, client, entry):
        self._client = client
        self._entry = entry
        self._attr_name = "Activate Siren (Continuous)"
        self._attr_icon = "mdi:alarm-light"
        self._attr_unique_id = f"{entry.entry_id}_activate_siren_continuous"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(identifiers={(DOMAIN, self._entry.entry_id)})

    async def async_press(self) -> None:
        """Handle the button press to start the siren using IOState 1."""
        try:
            _LOGGER.info("Activating Dahua Siren via CGI (ON)")
            await self.hass.async_add_executor_job(
                self._client.control_coaxial_cgi, 1
            )
        except Exception as err:
            _LOGGER.error("Failed to activate continuous siren: %s", err)


class DahuaSilenceSirenButton(ButtonEntity):
    """Button to manually force-stop the siren safely using the CGI IOState 2."""

    def __init__(self, client, entry):
        self._client = client
        self._entry = entry
        self._attr_name = "Silence Siren"
        self._attr_icon = "mdi:bell-off"
        self._attr_unique_id = f"{entry.entry_id}_silence_siren"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(identifiers={(DOMAIN, self._entry.entry_id)})

    async def async_press(self) -> None:
        """Handle the button press to stop the siren using IOState 2."""
        try:
            _LOGGER.info("Silencing Dahua Siren safely via CGI (OFF)")
            await self.hass.async_add_executor_job(
                self._client.control_coaxial_cgi, 2
            )
        except Exception as err:
            _LOGGER.error("Failed to silence siren: %s", err)


class DahuaRebootButton(ButtonEntity):
    """Button to manually reboot the camera."""

    def __init__(self, client, entry):
        self._client = client
        self._entry = entry
        self._attr_name = "Reboot Camera"
        self._attr_icon = "mdi:restart"
        self._attr_unique_id = f"{entry.entry_id}_reboot"
        
        # Push this entity to the "Diagnostics" block in the Home Assistant UI
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(identifiers={(DOMAIN, self._entry.entry_id)})

    async def async_press(self) -> None:
        try:
            _LOGGER.info("Rebooting Dahua Camera")
            def _reboot():
                self._client.ensure_login()
                body = {
                    "method": "magicBox.reboot",
                    "params": None,
                    "id": self._client._next_id(),
                    "session": self._client.session
                }
                return self._client._post("/RPC2", body)

            await self.hass.async_add_executor_job(_reboot)
        except Exception as err:
            _LOGGER.error("Failed to reboot camera: %s", err)