"""Provide buttons that simulate presses from one CDWX8 remote in HA."""

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import remote_device_info
from .const import BUTTON_EVENTS, press_signal


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add one virtual button per physical key."""
    async_add_entities(JiuhaoVirtualButton(entry, button) for button in BUTTON_EVENTS)


class JiuhaoVirtualButton(ButtonEntity):
    """Send the same local press signal as the physical key."""

    _attr_has_entity_name = True
    _attr_translation_key = "press_button"

    def __init__(self, entry: ConfigEntry, button: str) -> None:
        """Link the button to this remote's device and press signal."""
        self._signal = press_signal(entry.entry_id)
        self._button = button
        self._attr_unique_id = f"{entry.data[CONF_ADDRESS]}_press_{button[-1]}"
        self._attr_translation_placeholders = {"key": button[-1].upper()}
        self._attr_device_info = remote_device_info(entry)

    async def async_press(self) -> None:
        """Simulate a key press inside Home Assistant."""
        async_dispatcher_send(self.hass, self._signal, self._button)
