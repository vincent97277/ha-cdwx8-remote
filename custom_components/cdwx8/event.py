"""Publish button presses from raw CDWX8 Bluetooth advertisements."""

from time import monotonic

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_register_advertisement_callback,
)
from homeassistant.components.event import EventDeviceClass, EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import remote_device_info
from .advertisement import press_frames
from .const import BUTTON_EVENTS, CONF_UUID_PREFIX, press_signal

# Captured retransmissions lasted about half a second. Leave room for a second
# scanner delivering the same press later, while allowing the counter to reset.
REPEAT_WINDOW = 2.0
SINGLE_PRESS = "single_press"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the existing shared entity and one entity per physical button."""
    signal = press_signal(entry.entry_id)
    address = entry.data[CONF_ADDRESS]
    decoder = JiuhaoAdvertisementDecoder(
        hass, signal, bytes.fromhex(entry.data[CONF_UUID_PREFIX])
    )
    async_add_entities(
        [JiuhaoRemoteEvent(entry, signal)]
        + [JiuhaoRemoteEvent(entry, signal, button) for button in BUTTON_EVENTS]
    )
    entry.async_on_unload(
        async_register_advertisement_callback(hass, decoder.async_receive, address)
    )


class JiuhaoAdvertisementDecoder:
    """Decode and deduplicate a remote's packets once for all its entities."""

    def __init__(self, hass: HomeAssistant, signal: str, uuid_prefix: bytes) -> None:
        """Initialize the per-remote decoder."""
        self._hass = hass
        self._signal = signal
        self._uuid_prefix = uuid_prefix
        self._recent_sequences: dict[int, float] = {}

    @callback
    def async_receive(self, advertisement: BluetoothServiceInfoBleak) -> None:
        """Decode the current packet and ignore copies of a press."""
        now = monotonic()
        for frame in press_frames(advertisement.raw):
            if not frame.startswith(self._uuid_prefix):
                continue
            sequence, key = frame[6:8]
            previous = self._recent_sequences.get(sequence)
            self._recent_sequences[sequence] = now
            if previous is not None and now - previous < REPEAT_WINDOW:
                continue
            async_dispatcher_send(self._hass, self._signal, BUTTON_EVENTS[key - 1])


class JiuhaoRemoteEvent(EventEntity):
    """Publish presses from the whole remote or one physical button."""

    _attr_has_entity_name = True
    _attr_device_class = EventDeviceClass.BUTTON
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, signal: str, button: str | None = None) -> None:
        """Keep the original unique ID for the shared entity."""
        address = entry.data[CONF_ADDRESS]
        self._signal = signal
        self._button = button
        self._attr_unique_id = f"{address}_{button or 'buttons'}"
        self._attr_event_types = [SINGLE_PRESS] if button else list(BUTTON_EVENTS)
        if button:
            self._attr_name = f"Button {button[-1].upper()}"
        self._attr_device_info = remote_device_info(entry)

    async def async_added_to_hass(self) -> None:
        """Subscribe while this entity is enabled and loaded."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(self.hass, self._signal, self._async_button_pressed)
        )

    @callback
    def _async_button_pressed(self, button: str) -> None:
        """Publish the press on the shared entity and the matching button."""
        if self._button is None:
            self._trigger_event(button)
        elif self._button == button:
            self._trigger_event(SINGLE_PRESS)
        else:
            return
        self.async_write_ha_state()
