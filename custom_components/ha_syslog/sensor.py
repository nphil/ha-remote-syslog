"""Diagnostic sensors: proof the forwarder is actually forwarding.

A log shipper that silently stops is worse than no log shipper, because the
gap only becomes apparent when the history is needed and is not there. UDP
gives no delivery signal at all, so the honest thing to report is what this
end did: how many records it handed to the socket, and when the last one
went. A counter that stops climbing is the signal to go looking.
"""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the diagnostic sensors."""
    forwarder = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [ForwardedRecordsSensor(entry, forwarder), LastForwardedSensor(entry, forwarder)]
    )


class HaSyslogEntity(SensorEntity):
    """Shared identity: one service device per configured collector."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: ConfigEntry, forwarder) -> None:
        self._entry = entry
        self._forwarder = forwarder
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Syslog {entry.title}",
            manufacturer="Remote Syslog",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to the forwarder's own updates."""
        self.async_on_remove(self._forwarder.async_add_listener(self._handle_update))

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class ForwardedRecordsSensor(HaSyslogEntity):
    """How many log records have been sent since this entry loaded."""

    _attr_translation_key = "forwarded_records"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = "records"

    def __init__(self, entry: ConfigEntry, forwarder) -> None:
        super().__init__(entry, forwarder)
        self._attr_unique_id = f"{entry.entry_id}_forwarded_records"

    @property
    def native_value(self) -> int:
        return self._forwarder.forwarded

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        return {
            "dropped": self._forwarder.dropped,
            "last_error": self._forwarder.last_error,
        }


class LastForwardedSensor(HaSyslogEntity):
    """When the most recent record was sent."""

    _attr_translation_key = "last_forwarded"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, entry: ConfigEntry, forwarder) -> None:
        super().__init__(entry, forwarder)
        self._attr_unique_id = f"{entry.entry_id}_last_forwarded"

    @property
    def native_value(self):
        return self._forwarder.last_forwarded
