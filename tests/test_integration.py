"""Exercise the CDWX8 integration against Home Assistant without hardware."""

import asyncio
from pathlib import Path
import shutil
import sys
from types import ModuleType
from unittest.mock import Mock

from bleak.backends.device import BLEDevice
from bluetooth_data_tools import parse_advertisement_data_bytes
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_get_advertisement_callback,
)
from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
import pytest

DOMAIN = "cdwx8"
# Synthetic addresses and payloads with the CDWX8 wire format.
ADDRESS = "02:00:11:22:33:44"
PREFIX = "01 01 11 22 33 44"
BUTTON_A = bytes.fromhex("020106110701011122334449011011121314151617")
BUTTON_B = bytes.fromhex("02010611070101112233444A022021222324252627")
IDLE = bytes.fromhex(
    "0201060F1695FE305A038A004433221100020812096364647A2E72656D6F74652E6364777838"
)


@pytest.fixture(autouse=True)
def custom_integration(hass, tmp_path, enable_custom_integrations, monkeypatch):
    """Install the repository copy in an isolated HA config directory."""
    source = Path(__file__).resolve().parents[1]
    destination = tmp_path / "custom_components"
    shutil.copytree(source / "custom_components", destination)
    hass.config.config_dir = str(tmp_path)
    package = ModuleType("custom_components")
    package.__path__ = [str(destination)]
    monkeypatch.setitem(sys.modules, "custom_components", package)
    monkeypatch.setattr(
        "bluetooth_adapters.systems.linux.LinuxAdapters.history", property(lambda _: {})
    )


def advertisement(raw: bytes | None, address: str = ADDRESS) -> BluetoothServiceInfoBleak:
    """Include the historical UUID even in an idle or raw-less packet."""
    name, uuids, _, _, _ = parse_advertisement_data_bytes(raw or b"")
    return BluetoothServiceInfoBleak(
        name=name or address,
        address=address,
        rssi=-40,
        manufacturer_data={},
        service_data={},
        service_uuids=uuids or ["27262524-2322-2120-024a-443322110101"],
        source="test_proxy",
        device=BLEDevice(address, "cddz.remote.cdwx8", {}),
        advertisement=None,
        connectable=False,
        time=1.0,
        tx_power=None,
        raw=raw,
    )


async def test_manual_and_duplicate_setup(hass, mock_bluetooth):
    """Validate inputs and prevent the same remote from being installed twice."""
    form = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert form["type"] == FlowResultType.MENU
    form = await hass.config_entries.flow.async_configure(
        form["flow_id"], {"next_step_id": "manual"}
    )
    invalid = await hass.config_entries.flow.async_configure(
        form["flow_id"], {"address": "invalid", "uuid_prefix": "123"}
    )
    assert invalid["errors"] == {
        "address": "invalid_address",
        "uuid_prefix": "invalid_prefix",
    }
    result = await hass.config_entries.flow.async_configure(
        form["flow_id"], {"address": ADDRESS.lower(), "uuid_prefix": PREFIX}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == ADDRESS
    assert result["data"] == {"address": ADDRESS, "uuid_prefix": "010111223344"}
    duplicate = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_BLUETOOTH},
        data=advertisement(IDLE),
    )
    assert duplicate["reason"] == "already_configured"


async def test_discovered_remote_publishes_only_fresh_presses(
    hass, mock_bluetooth, monkeypatch
):
    """Route fresh presses to both event entities and remove the listener on unload."""
    from custom_components.cdwx8 import event

    unregister = Mock()
    register = Mock(return_value=unregister)
    monkeypatch.setattr(event, "async_register_advertisement_callback", register)
    clock = Mock(return_value=1.0)
    monkeypatch.setattr(event, "monotonic", clock)

    form = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=advertisement(BUTTON_A)
    )
    assert form["type"] == FlowResultType.FORM
    assert form["step_id"] == "confirm"
    result = await hass.config_entries.flow.async_configure(form["flow_id"], {})
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    register.assert_called_once()
    registered_hass, receive, address = register.call_args.args
    assert registered_hass is hass
    assert address == ADDRESS
    registry = er.async_get(hass)
    shared_entity = registry.async_get_entity_id("event", DOMAIN, f"{ADDRESS}_buttons")
    button_entities = {
        button: registry.async_get_entity_id("event", DOMAIN, f"{ADDRESS}_{button}")
        for button in ("button_a", "button_b", "button_c", "button_d")
    }
    all_entities = {shared_entity, *button_entities.values()}
    assert all_entities == set(hass.states.async_entity_ids("event"))
    states = {entity_id: hass.states.get(entity_id) for entity_id in all_entities}
    assert all(state.state == "unknown" for state in states.values())

    for raw, expected in (
        (BUTTON_A, "button_a"),
        (BUTTON_B, "button_b"),
        (BUTTON_B[:11] + b"\x4B\x03" + BUTTON_B[13:], "button_c"),
        (BUTTON_B[:11] + b"\x4C\x04" + BUTTON_B[13:], "button_d"),
    ):
        receive(advertisement(raw))
        button_entity = button_entities[expected]
        states[shared_entity] = hass.states.get(shared_entity)
        states[button_entity] = hass.states.get(button_entity)
        assert states[shared_entity].attributes["event_type"] == expected
        assert states[button_entity].attributes["event_type"] == "single_press"
        assert {entity_id: hass.states.get(entity_id) for entity_id in all_entities} == states

    for raw in (
        BUTTON_A,
        IDLE,
        None,
        BUTTON_B[:8],
        BUTTON_B[:12] + b"\x05" + BUTTON_B[13:],
    ):
        receive(advertisement(raw))
        assert {entity_id: hass.states.get(entity_id) for entity_id in all_entities} == states

    for now in (2.5, 4.0):
        clock.return_value = now
        receive(advertisement(BUTTON_A))
        assert {entity_id: hass.states.get(entity_id) for entity_id in all_entities} == states

    clock.return_value = 10.0
    receive(advertisement(BUTTON_A))
    assert hass.states.get(shared_entity).attributes["event_type"] == "button_a"
    button_a_entity = button_entities["button_a"]
    assert hass.states.get(button_a_entity).state != states[button_a_entity].state
    assert await hass.config_entries.async_unload(result["result"].entry_id)
    unregister.assert_called_once_with()


async def test_idle_discovery_waits_for_the_selected_remote(hass, mock_bluetooth):
    """A named idle packet starts discovery and the next key supplies the prefix."""
    form = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=advertisement(IDLE)
    )
    assert form["step_id"] == "bluetooth_ready"
    flow_id = form["flow_id"]
    progress = await hass.config_entries.flow.async_configure(flow_id, {})
    assert progress["type"] == FlowResultType.SHOW_PROGRESS
    await asyncio.sleep(0)
    receive = async_get_advertisement_callback(hass)
    receive(advertisement(BUTTON_A, "02:00:11:22:33:45"))
    receive(advertisement(IDLE))
    assert (await hass.config_entries.flow.async_configure(flow_id))["step_id"] == "scan"
    receive(advertisement(BUTTON_A))
    await hass.async_block_till_done()
    confirmation = await hass.config_entries.flow.async_configure(flow_id)
    assert confirmation["step_id"] == "confirm"
    result = await hass.config_entries.flow.async_configure(flow_id, {})
    assert result["data"] == {"address": ADDRESS, "uuid_prefix": "010111223344"}


async def test_scan_timeout_allows_retry(hass, mock_bluetooth, monkeypatch):
    """Offer a new scan or manual setup after the listening window."""
    from custom_components.cdwx8 import config_flow

    monkeypatch.setattr(config_flow, "SCAN_TIMEOUT", 0)
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    flow_id = flow["flow_id"]
    await hass.config_entries.flow.async_configure(flow_id, {"next_step_id": "scan"})
    await hass.async_block_till_done()
    timeout = await hass.config_entries.flow.async_configure(flow_id)
    assert timeout["step_id"] == "scan_timeout"
    assert timeout["menu_options"] == ["scan", "manual"]


async def test_virtual_and_physical_presses_are_independent(hass, mock_bluetooth, monkeypatch):
    """Two remotes have separate controls, events, and sequence histories."""
    from custom_components.cdwx8 import event

    second_address = "02:00:11:22:33:45"
    second_prefix = "01 01 11 22 33 45"
    register = Mock(side_effect=lambda *_: Mock())
    monkeypatch.setattr(event, "async_register_advertisement_callback", register)
    for address, prefix, raw in (
        (ADDRESS, PREFIX, BUTTON_A),
        (second_address, second_prefix, BUTTON_A[:10] + b"\x45" + BUTTON_A[11:]),
    ):
        menu = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        flow_id = menu["flow_id"]
        progress = await hass.config_entries.flow.async_configure(flow_id, {"next_step_id": "scan"})
        assert progress["type"] == FlowResultType.SHOW_PROGRESS
        await asyncio.sleep(0)
        receive = async_get_advertisement_callback(hass)
        receive(advertisement(None, address))
        receive(advertisement(BUTTON_A, "02:00:11:22:33:99"))
        assert (await hass.config_entries.flow.async_configure(flow_id))["step_id"] == "scan"
        receive(advertisement(raw, address))
        await hass.async_block_till_done()
        confirmation = await hass.config_entries.flow.async_configure(flow_id)
        assert confirmation["description_placeholders"] == {"address": address}
        result = await hass.config_entries.flow.async_configure(flow_id, {})
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"] == {"address": address, "uuid_prefix": bytes.fromhex(prefix).hex()}
    await hass.async_block_till_done()

    listeners = {call.args[2]: call.args[1] for call in register.call_args_list}
    assert set(listeners) == {ADDRESS, second_address}
    registry = er.async_get(hass)
    devices = dr.async_get(hass)
    shared = {
        address: registry.async_get_entity_id("event", DOMAIN, f"{address}_buttons")
        for address in listeners
    }
    assert len(set(shared.values())) == 2
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": [
                {
                    "triggers": [
                        {
                            "trigger": "event.received",
                            "target": {"entity_id": shared[ADDRESS]},
                            "options": {"event_type": ["button_a"]},
                        },
                    ],
                    "actions": [{"event": "cdwx8_test_action"}],
                },
            ],
        },
    )
    actions = []
    hass.bus.async_listen("cdwx8_test_action", actions.append)
    await hass.async_block_till_done()

    for address in listeners:
        device_id = registry.async_get(shared[address]).device_id
        assert devices.async_get(device_id).identifiers == {(DOMAIN, address)}
        other_address = second_address if address == ADDRESS else ADDRESS
        other_state = hass.states.get(shared[other_address])
        for key in "abcd":
            virtual = registry.async_get_entity_id("button", DOMAIN, f"{address}_press_{key}")
            assert registry.async_get(virtual).device_id == device_id
            await hass.services.async_call(
                "button", "press", {"entity_id": virtual}, blocking=True
            )
            event_type = f"button_{key}"
            single = registry.async_get_entity_id("event", DOMAIN, f"{address}_{event_type}")
            assert hass.states.get(shared[address]).attributes["event_type"] == event_type
            assert hass.states.get(single).attributes["event_type"] == "single_press"
            assert hass.states.get(shared[other_address]) == other_state

    await hass.async_block_till_done()
    assert len(actions) == 1
    for address, raw in (
        (ADDRESS, BUTTON_A),
        (second_address, BUTTON_A[:10] + b"\x45" + BUTTON_A[11:]),
    ):
        listeners[address](advertisement(raw, address))
        assert hass.states.get(shared[address]).attributes["event_type"] == "button_a"
    await hass.async_block_till_done()
    assert len(actions) == 2
