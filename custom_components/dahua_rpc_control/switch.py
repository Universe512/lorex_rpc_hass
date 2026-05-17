import logging
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Set up Dahua switches from a config entry."""
    client = hass.data[DOMAIN][entry.entry_id]
    
    switches = [
        DahuaVideoAnalyseSwitch(client, entry),
        DahuaCoaxialLightSwitch(client, entry),
        DahuaGenericSwitch(client, entry, "MotionDetect", "Basic Motion Detection", "mdi:motion-sensor"),
    ]
    
    # If you added any specific IVS switches (like PersonNight) earlier, 
    # you can paste them back into this list!
    
    async_add_entities(switches, update_before_add=True)


class DahuaCoaxialLightSwitch(SwitchEntity):
    """Switch to manually toggle the camera's white LED using CoaxialControlIO."""
    def __init__(self, client, entry):
        self._client = client
        self._entry = entry
        self._is_on = False
        self._attr_name = "Camera White Light"
        self._attr_icon = "mdi:flashlight"
        self._attr_unique_id = f"{entry.entry_id}_coaxial_white_light"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(identifiers={(DOMAIN, self._entry.entry_id)})

    @property
    def is_on(self):
        return self._is_on

    async def async_turn_on(self, **kwargs):
        try:
            await self.hass.async_add_executor_job(self._client.control_coaxial_io, 3, 1, 2)
            self._is_on = True
            self.async_write_ha_state()
        except Exception as err:
            pass

    async def async_turn_off(self, **kwargs):
        try:
            await self.hass.async_add_executor_job(self._client.control_coaxial_io, 3, 0, 2)
            self._is_on = False
            self.async_write_ha_state()
        except Exception as err:
            pass


class DahuaGenericSwitch(SwitchEntity):
    """A generic class to handle simple Enable/Disable Dahua configs."""
    def __init__(self, client, entry, config_name, attr_name, icon):
        self._client = client
        self._entry = entry
        self._config_name = config_name
        self._attr_name = attr_name
        self._attr_icon = icon
        self._is_on = False
        self._attr_unique_id = f"{entry.entry_id}_{config_name.lower()}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(identifiers={(DOMAIN, self._entry.entry_id)})

    @property
    def is_on(self):
        return self._is_on

    async def async_turn_on(self, **kwargs):
        await self._set_state(True)

    async def async_turn_off(self, **kwargs):
        await self._set_state(False)

    async def _set_state(self, state: bool):
        try:
            current = await self.hass.async_add_executor_job(self._client.get_config, self._config_name)
            table = current.get("params", {}).get("table") or current.get("result", {}).get("table")
            if table:
                if isinstance(table, list) and len(table) > 0:
                    table[0]["Enable"] = state
                elif isinstance(table, dict):
                    table["Enable"] = state
                await self.hass.async_add_executor_job(self._client.set_config, self._config_name, table)
                self._is_on = state
                self.async_write_ha_state()
        except Exception as err:
            pass

    async def async_update(self):
        try:
            current = await self.hass.async_add_executor_job(self._client.get_config, self._config_name)
            table = current.get("params", {}).get("table") or current.get("result", {}).get("table")
            if table:
                if isinstance(table, list) and len(table) > 0:
                    val = table[0].get("Enable", False)
                elif isinstance(table, dict):
                    val = table.get("Enable", False)
                else:
                    val = False
                self._is_on = bool(val)
        except Exception as err:
            pass


class DahuaVideoAnalyseSwitch(SwitchEntity):
    """Representation of the original Video Analyse Switch."""
    def __init__(self, client, entry):
        self._client = client
        self._entry = entry
        self._is_on = False
        self._attr_name = "Video Analyse Type"
        self._attr_icon = "mdi:cctv"
        self._attr_unique_id = f"{entry.entry_id}_video_analyse"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(identifiers={(DOMAIN, self._entry.entry_id)})

    @property
    def is_on(self):
        return self._is_on

    async def async_turn_on(self, **kwargs):
        await self.hass.async_add_executor_job(self._client.set_video_analyse_type, "Normal")
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        await self.hass.async_add_executor_job(self._client.set_video_analyse_type, "")
        self._is_on = False
        self.async_write_ha_state()

    async def async_update(self):
        try:
            state = await self.hass.async_add_executor_job(self._client.get_video_analyse_global)
            table = None
            if isinstance(state, dict):
                if "params" in state and isinstance(state["params"], dict):
                    table = state["params"].get("table")
                if table is None and "result" in state and isinstance(state["result"], dict):
                    table = state["result"].get("table")

            if table and isinstance(table, list) and len(table) > 0:
                scene = table[0].get("Scene", {})
                current_type = scene.get("Type", "")
                self._is_on = (current_type != "")
        except Exception as err:
            pass