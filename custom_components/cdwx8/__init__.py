"""Listen for Jiuhao remote presses through Home Assistant Bluetooth."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, MODEL

PLATFORMS = (Platform.EVENT, Platform.BUTTON)


def remote_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Group the event entities and virtual buttons under the same remote."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.data[CONF_ADDRESS])},
        name=entry.title,
        manufacturer="Jiuhao",
        model=MODEL,
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the remote's events and virtual buttons."""
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the remote's entities and advertisement listener."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
