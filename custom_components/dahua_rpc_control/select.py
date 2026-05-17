import logging
from datetime import timedelta
from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Poll the camera every 10 seconds to keep the UI in sync
SCAN_INTERVAL = timedelta(seconds=10)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Set up Dahua dropdown selects from a config entry."""
    client = hass.data[DOMAIN][entry.entry_id]
    
    selects = [
        DahuaActiveSceneSelect(client, entry),
        DahuaLightModeSelect(client, entry)
    ]
    
    async_add_entities(selects, update_before_add=True)


async def async_get_profile_info(hass, client):
    """Helper method to fetch the active scene, mode, its true array index, and available scene names."""
    try:
        # 1. Fetch current active mode from VideoInMode
        vim = await hass.async_add_executor_job(client.get_config, "VideoInMode")
        vim_table = vim.get("params", {}).get("table") or vim.get("result", {}).get("table")
        
        current_name = "Normal"
        current_mode = 4  # Default to manual mode
        
        if vim_table:
            target_vim = vim_table[0] if isinstance(vim_table, list) and len(vim_table) > 0 else vim_table if isinstance(vim_table, dict) else {}
            current_name = target_vim.get("ConfigEx", "Normal")
            current_mode = target_vim.get("Mode", 4)

        # 2. Fetch all available scenes from VideoColor
        vc = await hass.async_add_executor_job(client.get_config, "VideoColor")
        vc_table = vc.get("params", {}).get("table") or vc.get("result", {}).get("table")
        
        active_idx = None
        normal_idx = None
        options = []

        if vc_table and len(vc_table) > 0:
            profiles = vc_table[0] if isinstance(vc_table[0], list) else vc_table
            if isinstance(profiles, dict):
                profiles = [profiles]  # Ensure it is iterable
                
            for i, p in enumerate(profiles):
                name = None
                if isinstance(p, dict):
                    name = p.get("ProfileName")
                elif isinstance(p, list) and len(p) > 0:
                    name = p[0].get("ProfileName")

                if name:
                    name_str = str(name).strip()
                    if name_str not in options:
                        options.append(name_str)
                    
                    # Lock in the true array indices based on the name match
                    if name_str.lower() == str(current_name).strip().lower() and active_idx is None:
                        active_idx = i
                        
                    if name_str.lower() == "normal" and normal_idx is None:
                        normal_idx = i

        # 3. Fallback logic if the firmware hides ProfileName
        if not options:
            options = ["Day", "Night", "Normal"]

        # Ensure we always map active_idx accurately
        if active_idx is None:
            try:
                active_idx = next(i for i, opt in enumerate(options) if str(opt).lower() == str(current_name).strip().lower())
            except StopIteration:
                active_idx = 0  # Ultimate fallback
                
        # Ensure we always map normal_idx accurately (Auto mode relies on this)
        if normal_idx is None:
            try:
                normal_idx = next(i for i, opt in enumerate(options) if str(opt).lower() == "normal")
            except StopIteration:
                normal_idx = 2  # Ultimate fallback matching user observation of slot 2
            
        return active_idx, normal_idx, current_name, current_mode, options
        
    except Exception as err:
        _LOGGER.error("Failed to parse VideoColor profile info: %s", err)
        return 0, 2, "Normal", 4, ["Day", "Night", "Normal"]


class DahuaActiveSceneSelect(SelectEntity):
    """Select entity to change the current VideoInMode Scene (Auto/Day/Night/Normal)."""

    def __init__(self, client, entry):
        self._client = client
        self._entry = entry
        self._attr_name = "Active Scene Profile"
        self._attr_unique_id = f"{entry.entry_id}_active_scene"
        self._attr_icon = "mdi:camera-iris"
        self._attr_options = []
        self._attr_current_option = None
        
        # Push this entity to the "Configuration" block
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer="Lorex",
            model="RPC Camera",
        )

    async def async_update(self):
        """Fetch the latest profiles and the currently active one."""
        _, _, current_name, current_mode, options = await async_get_profile_info(self.hass, self._client)
        
        # Always inject 'Auto' at the top of the list
        self._attr_options = ["Auto"] + options
        
        # If Mode is 0, the camera is self-adaptive
        if current_mode == 0:
            self._attr_current_option = "Auto"
        else:
            self._attr_current_option = current_name

    async def async_select_option(self, option: str) -> None:
        """Update the VideoInMode to the newly selected scene or Auto."""
        try:
            vim = await self.hass.async_add_executor_job(self._client.get_config, "VideoInMode")
            table = vim.get("params", {}).get("table") or vim.get("result", {}).get("table")
            
            if table:
                target = table[0] if isinstance(table, list) and len(table) > 0 else table if isinstance(table, dict) else None
                
                if target is not None:
                    if option == "Auto":
                        target["Config"] = [2]
                        target["ConfigEx"] = "Day"
                        target["Mode"] = 0
                        ts_str = "00:00:00-24:00:00 Day"
                    else:
                        target["Config"] = []
                        target["ConfigEx"] = option
                        target["Mode"] = 4  # 4 forces Manual/Profile mode
                        ts_str = f"00:00:00-24:00:00 {option}"
                        
                    target["TimeSectionEX"] = [ts_str]
                    
                    # Overwrite TimeSectionV2 completely to break out of stuck schedules
                    if "TimeSectionV2" in target and isinstance(target["TimeSectionV2"], list):
                        num_days = len(target["TimeSectionV2"])
                        target["TimeSectionV2"] = [[ts_str] for _ in range(num_days)]
                        
                await self.hass.async_add_executor_job(self._client.set_config, "VideoInMode", table)
                self._attr_current_option = option
                self.async_write_ha_state()
                
        except Exception as err:
            _LOGGER.error("Failed to set Active Scene: %s", err)


class DahuaLightModeSelect(SelectEntity):
    """Select entity to choose Dahua lighting mode (targets only the currently active scene)."""

    def __init__(self, client, entry):
        self._client = client
        self._entry = entry
        self._attr_name = "Illumination Mode"
        self._attr_unique_id = f"{entry.entry_id}_light_mode"
        self._attr_icon = "mdi:theme-light-dark"
        self._attr_options = ["InfraredMode", "WhiteMode", "AIMode"]
        self._attr_current_option = None
        
        # Push this entity to the "Configuration" block
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(identifiers={(DOMAIN, self._entry.entry_id)})

    async def async_update(self):
        """Find the active scene index, then read the illumination mode from that specific slot."""
        try:
            active_idx, normal_idx, _, current_mode, _ = await async_get_profile_info(self.hass, self._client)
            
            # If Auto mode (0) is active, override the index to read from the 'Normal' slot
            idx = normal_idx if current_mode == 0 else active_idx
            
            ls = await self.hass.async_add_executor_job(self._client.get_config, "LightingScheme")
            table = ls.get("params", {}).get("table") or ls.get("result", {}).get("table")
            
            if table and isinstance(table, list) and len(table) > 0:
                schemes = table[0]
                if len(schemes) > idx:
                    target = schemes[idx]
                    val = None
                    if isinstance(target, list) and len(target) > 0:
                        val = target[0].get("LightingMode")
                    elif isinstance(target, dict):
                        val = target.get("LightingMode")
                        
                    if val and val in self._attr_options:
                        self._attr_current_option = val
                        
        except Exception as err:
            _LOGGER.error("Failed to update Lighting Mode: %s", err)

    async def async_select_option(self, option: str) -> None:
        """Find the active scene index, and ONLY update the LightingScheme at that slot."""
        try:
            active_idx, normal_idx, _, current_mode, _ = await async_get_profile_info(self.hass, self._client)
            
            # If Auto mode (0) is active, override the index to write to the 'Normal' slot
            idx = normal_idx if current_mode == 0 else active_idx
            
            ls = await self.hass.async_add_executor_job(self._client.get_config, "LightingScheme")
            table = ls.get("params", {}).get("table") or ls.get("result", {}).get("table")
            
            if table and isinstance(table, list) and len(table) > 0:
                schemes = table[0]
                if len(schemes) > idx:
                    target = schemes[idx]
                    
                    # Update ONLY the targeted profile index
                    if isinstance(target, list) and len(target) > 0:
                        target[0]["LightingMode"] = option
                    elif isinstance(target, dict):
                        target["LightingMode"] = option
                        
                await self.hass.async_add_executor_job(self._client.set_config, "LightingScheme", table)
                self._attr_current_option = option
                self.async_write_ha_state()
                
        except Exception as err:
            _LOGGER.error("Failed to set Lighting Mode: %s", err)