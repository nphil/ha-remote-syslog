"""The forwarder really forwards: set up, emit a log record, see it arrive, unload."""

from __future__ import annotations

import logging
import socket

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.ha_syslog.const import DOMAIN


async def test_setup_forwards_a_record_and_unload_detaches(
    hass: HomeAssistant, socket_enabled: None
) -> None:
    """A warning logged after setup reaches the collector; after unload it no longer does."""
    collector = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    collector.bind(("127.0.0.1", 0))
    collector.settimeout(5)
    port = collector.getsockname()[1]
    root = logging.getLogger()
    handlers_before = list(root.handlers)

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "127.0.0.1", "port": port, "protocol": "udp"},
        title=f"127.0.0.1:{port}",
    )
    entry.add_to_hass(hass)
    try:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED

        logging.getLogger("tests.ha_syslog").warning("hello from the test")
        datagram = await hass.async_add_executor_job(collector.recv, 4096)
        assert b"hello from the test" in datagram
        assert b"ha-core[tests.ha_syslog]" in datagram

        # Two diagnostic sensors hang off one service device.
        sensors = [
            e
            for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        ]
        assert len(sensors) == 2
        devices = dr.async_get(hass).async_get_devices(identifiers={(DOMAIN, entry.entry_id)})
        assert len(devices) == 1
        device = devices[0]
        assert device.entry_type is dr.DeviceEntryType.SERVICE
        assert device.manufacturer == "Remote Syslog"

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.NOT_LOADED
        assert DOMAIN not in hass.data or entry.entry_id not in hass.data[DOMAIN]
    finally:
        collector.close()
    # Every handler this entry added is gone again (pytest's own capture handlers stay).
    assert [h for h in root.handlers if h not in handlers_before] == []
