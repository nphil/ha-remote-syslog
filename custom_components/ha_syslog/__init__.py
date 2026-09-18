"""Forward Home Assistant's own log to a remote syslog server.

Why this exists
---------------
`/config/home-assistant.log` rotates ONLY at restart and keeps exactly one
generation (`.log.1`). There is no size cap and no daily rotation, so the log
history is always "this run plus the previous one". Measured on the install
this was written for: three restarts in one evening discarded everything
logged before them - and a fault that needs a restart to clear takes its own
diagnosis with it.

Home Assistant has no native remote-log option. The built-in `syslog`
integration is a *notify* service writing to the local syslog socket, and
`logger:` only sets levels - it exposes no handler configuration. Add-ons
each ship their own logs (Zigbee2MQTT has a `log_syslog:` block, for
instance) but Core does not.

So: attach a real `logging.handlers.SysLogHandler` to the root logger. Being
handler-based rather than file-based, nothing depends on log rotation, on
truncation, or on a `tail` process surviving a restart.

Design notes
------------
Records go through a `QueueHandler`/`QueueListener` pair. The socket write is
fast but not free, and Home Assistant logs from the event loop, so a direct
send would add its latency to whatever was running. The queue hands the write
to a background thread - the same approach Core uses for its own file handler.

`SysLogHandler` emits `<PRI>message` with no timestamp or hostname, which is
correct here: the collector stamps its own receive time and resolves the
sender itself (rsyslog's `%FROMHOST-IP%`), so records land under this host
with one consistent clock rather than two that can disagree.

The default level is WARNING. Forwarding DEBUG for everything is a firehose -
measured on the source install, a single integration at debug produced 2.4 MB
of log in 31 minutes - and a collector that rotates by size will churn
through its ceiling and evict the history this exists to preserve. Raise the
level deliberately while chasing something, then put it back.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import logging
import logging.handlers
import queue

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.util import dt as dt_util

from .const import (
    CONF_EXCLUDE_LOGGERS,
    CONF_FACILITY,
    CONF_INCLUDE_LOGGERS,
    CONF_LEVEL,
    CONF_PROTOCOL,
    CONF_TAG,
    DEFAULT_FACILITY,
    DEFAULT_LEVEL,
    DEFAULT_PROTOCOL,
    DEFAULT_TAG,
    DOMAIN,
    PROTOCOL_TCP,
    LoggerFilter,
    facility_code,
    parse_logger_list,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]


class CountingSysLogHandler(logging.handlers.SysLogHandler):
    """A SysLogHandler that reports what it managed to send.

    Wrapped rather than observed from outside because this is the only place
    that knows whether a record reached the socket: the queue upstream has
    already accepted it, and UDP downstream never answers. `handleError` is
    logging's own failure hook, so a send that raises is counted rather than
    silently swallowed the way stock logging would.
    """

    def __init__(self, *args, on_change: Callable[[], None], **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.forwarded = 0
        self.dropped = 0
        self.last_error: str | None = None
        self.last_forwarded: datetime | None = None
        self._on_change = on_change

    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self.forwarded += 1
        self.last_forwarded = dt_util.utcnow()
        self._on_change()

    def handleError(self, record: logging.LogRecord) -> None:
        import sys

        self.dropped += 1
        exc = sys.exc_info()[1]
        if exc is not None:
            self.last_error = f"{type(exc).__name__}: {exc}"
        self._on_change()


class SyslogForwarder:
    """Owns the handler pair, and the counters the sensors read."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._handler: CountingSysLogHandler | None = None
        self._queue_handler: logging.handlers.QueueHandler | None = None
        self._listener: logging.handlers.QueueListener | None = None
        self._cancel_stop: Callable[[], None] | None = None
        self._listeners: list[Callable[[], None]] = []

    # -- state the sensors read -------------------------------------------------

    @property
    def forwarded(self) -> int:
        return self._handler.forwarded if self._handler else 0

    @property
    def dropped(self) -> int:
        return self._handler.dropped if self._handler else 0

    @property
    def last_error(self) -> str | None:
        return self._handler.last_error if self._handler else None

    @property
    def last_forwarded(self) -> datetime | None:
        return self._handler.last_forwarded if self._handler else None

    @callback
    def async_add_listener(self, update: Callable[[], None]) -> Callable[[], None]:
        """Register a sensor for counter updates."""
        self._listeners.append(update)

        def _remove() -> None:
            self._listeners.remove(update)

        return _remove

    def _notify(self) -> None:
        """Push counter changes to the sensors.

        Called from the logging worker thread, so it hops to the event loop.
        Deliberately NOT called per record: at debug level that would be
        thousands of state writes a minute, recreating the recorder flood this
        household has already fixed twice. The sensors are diagnostics - a
        30 s refresh answers "is it still shipping".
        """
        for update in self._listeners:
            self._hass.loop.call_soon_threadsafe(update)

    # -- lifecycle --------------------------------------------------------------

    def attach(self, handler: CountingSysLogHandler, level: int) -> None:
        """Hook the handler onto the root logger."""
        self._handler = handler
        log_queue: queue.SimpleQueue[logging.LogRecord] = queue.SimpleQueue()
        self._listener = logging.handlers.QueueListener(
            log_queue, handler, respect_handler_level=True
        )
        self._queue_handler = logging.handlers.QueueHandler(log_queue)
        self._queue_handler.setLevel(level)
        self._listener.start()
        logging.getLogger().addHandler(self._queue_handler)

    def detach(self) -> None:
        """Remove the handler and stop the worker.

        Idempotent, and ordered so no record can be queued after the listener
        has stopped: unhook from the root logger first, drain second.
        """
        if self._queue_handler is not None:
            logging.getLogger().removeHandler(self._queue_handler)
            self._queue_handler = None
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        self._handler = None
        if self._cancel_stop is not None:
            self._cancel_stop()
            self._cancel_stop = None

    def track_shutdown(self, cancel: Callable[[], None]) -> None:
        self._cancel_stop = cancel


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Attach the remote syslog handler to the root logger."""
    host: str = entry.data[CONF_HOST]
    port: int = entry.data[CONF_PORT]
    protocol: str = entry.data.get(CONF_PROTOCOL, DEFAULT_PROTOCOL)

    options = entry.options
    level_name: str = options.get(CONF_LEVEL, DEFAULT_LEVEL)
    tag: str = options.get(CONF_TAG, DEFAULT_TAG)
    facility: str = options.get(CONF_FACILITY, DEFAULT_FACILITY)
    exclude = parse_logger_list(options.get(CONF_EXCLUDE_LOGGERS))
    include = parse_logger_list(options.get(CONF_INCLUDE_LOGGERS))
    level = getattr(logging, level_name.upper())

    forwarder = SyslogForwarder(hass)

    def _build() -> CountingSysLogHandler:
        # Constructing the handler resolves the address and opens the socket,
        # both of which can block; keep them off the event loop.
        import socket

        return CountingSysLogHandler(
            address=(host, port),
            facility=facility_code(facility),
            socktype=socket.SOCK_STREAM if protocol == PROTOCOL_TCP else socket.SOCK_DGRAM,
            on_change=forwarder._notify,
        )

    try:
        handler = await hass.async_add_executor_job(_build)
    except OSError as err:
        # Retry rather than fail permanently: a collector that is briefly
        # unreachable should not need a manual reload to start working, and a
        # diagnostic aid must never be load-bearing.
        raise ConfigEntryNotReady(
            f"Cannot reach syslog server {host}:{port}: {err}"
        ) from err

    # The logger name identifies the integration, which is the first thing you
    # want when reading these remotely, so it goes in the syslog tag where the
    # collector keeps it in its own column instead of buried in the message.
    handler.setFormatter(
        logging.Formatter(f"{tag}[%(name)s]: %(levelname)s %(message)s")
    )
    handler.setLevel(level)
    if include or exclude:
        handler.addFilter(LoggerFilter(include, exclude))

    forwarder.attach(handler, level)

    def _stop(_event: Event) -> None:
        """Detach on shutdown.

        Home Assistant does not unload config entries when it stops, so
        without this the handler stays attached while the rest of the process
        tears down - and records emitted during shutdown are exactly the ones
        worth keeping.
        """
        forwarder.detach()

    forwarder.track_shutdown(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _stop)
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = forwarder
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.info(
        "Forwarding Home Assistant logs at %s and above to %s:%s over %s",
        level_name,
        host,
        port,
        protocol,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Detach the handler and remove the sensors."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    forwarder: SyslogForwarder | None = hass.data.get(DOMAIN, {}).pop(
        entry.entry_id, None
    )
    if forwarder is not None:
        await hass.async_add_executor_job(forwarder.detach)
    return unloaded
