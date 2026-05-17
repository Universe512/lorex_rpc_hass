import logging
from datetime import timedelta
from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Poll the camera every 10 seconds to keep the UI in sync
SCAN_INTERVAL = timedelta(seconds=10)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Set up Dahua numbers from a config entry."""
    client = hass.data[DOMAIN][entry.entry_id]
    
    numbers = [
        # The quick siren duration
        DahuaConfigNumber(
            client, entry, 
            config_name="Sound", field_name="AlarmSoundDuration", 
            attr_name="Quick Siren Duration", icon="mdi:timer-outline", 
            min_v=1, max_v=300, step=1, unit="s"
        ),
        
        # The master volume control
        DahuaConfigNumber(
            client, entry, 
            config_name="Sound", field_name="AlarmSoundVolume", 
            attr_name="Siren Volume", icon="mdi:volume-high", 
            min_v=0, max_v=100, step=1, unit="%"
        )
    ]
    
    async_add_entities(numbers, update_before_add=True)


class DahuaConfigNumber(NumberEntity):
    """Generic Number entity to configure numerical Dahua API fields."""

    def __init__(self, client, entry, config_name, field_name, attr_name, icon, min_v, max_v, step, unit):
        self._client = client
        self._entry = entry
        self._config_name = config_name
        self._field_name = field_name
        self._attr_name = attr_name
        self._attr_icon = icon
        
        # Clean up unique ID so it doesn't contain periods
        safe_field = field_name.replace(".", "_").lower()
        self._attr_unique_id = f"{entry.entry_id}_{config_name.lower()}_{safe_field}"
        
        # Push this entity to the "Configuration" block in the Home Assistant UI
        self._attr_entity_category = EntityCategory.CONFIG
        
        # Configure slider bounds
        self._attr_native_min_value = min_v
        self._attr_native_max_value = max_v
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit
        self._attr_native_value = min_v  # Fallback

    @property
    def device_info(self) -> DeviceInfo:
        """Link this entity back to the camera device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer="Dahua / Amcrest",
            model="RPC Camera/NVR",
        )

    def _get_val(self, table):
        """Intelligently drill down into nested dictionaries using dot notation."""
        target = table[0] if isinstance(table, list) and len(table) > 0 else table
        for key in self._field_name.split('.'):
            if isinstance(target, dict) and key in target:
                target = target[key]
            else:
                return self._attr_native_min_value
        return target

    def _set_val(self, table, value):
        """Intelligently set a value deep inside a nested dictionary using dot notation."""
        target = table[0] if isinstance(table, list) and len(table) > 0 else table
        keys = self._field_name.split('.')
        
        # Drill down to the second-to-last key
        for key in keys[:-1]:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
            target = target[key]
            
        # Set the final key's value
        target[keys[-1]] = int(value)

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value on the camera."""
        try:
            current = await self.hass.async_add_executor_job(
                self._client.get_config, self._config_name
            )
            table = current.get("params", {}).get("table") or current.get("result", {}).get("table")
            
            if table is not None:
                # Use our dot notation setter
                self._set_val(table, value)
                    
                await self.hass.async_add_executor_job(
                    self._client.set_config, self._config_name, table
                )
                
                # Update the HA state immediately
                self._attr_native_value = float(value)
                self.async_write_ha_state()
        except Exception as err:
            _LOGGER.error("Failed to set %s %s: %s", self._config_name, self._field_name, err)

    async def async_update(self):
        """Fetch current value from the camera."""
        try:
            current = await self.hass.async_add_executor_job(
                self._client.get_config, self._config_name
            )
            table = current.get("params", {}).get("table") or current.get("result", {}).get("table")
            
            if table is not None:
                # Use our dot notation getter
                val = self._get_val(table)
                self._attr_native_value = float(val)
        except Exception as err:
            _LOGGER.error("Failed to update %s %s: %s", self._config_name, self._field_name, err)