"""Constants and shared helpers for the remote syslog forwarder."""

from __future__ import annotations

import logging
import logging.handlers
import socket

DOMAIN = "ha_syslog"

CONF_PROTOCOL = "protocol"
CONF_LEVEL = "level"
CONF_TAG = "tag"
CONF_FACILITY = "facility"
CONF_EXCLUDE_LOGGERS = "exclude_loggers"
CONF_INCLUDE_LOGGERS = "include_loggers"

PROTOCOL_UDP = "udp"
PROTOCOL_TCP = "tcp"
PROTOCOLS = [PROTOCOL_UDP, PROTOCOL_TCP]

LEVELS = ["debug", "info", "warning", "error", "critical"]

DEFAULT_PORT = 514
# UDP is what most collectors listen on out of the box (rsyslog's imudp), and
# losing the odd datagram matters less than a blocking reconnect would; TCP is
# offered for collectors that require it or when no record may be dropped.
DEFAULT_PROTOCOL = PROTOCOL_UDP
DEFAULT_LEVEL = "warning"
DEFAULT_TAG = "ha-core"
# local0 by default: keeps Core's records distinguishable from add-ons,
# switches and routers reporting to the same collector.
DEFAULT_FACILITY = "local0"

FACILITIES = [
    "user",
    "daemon",
    "syslog",
    "local0",
    "local1",
    "local2",
    "local3",
    "local4",
    "local5",
    "local6",
    "local7",
]

FACILITY = logging.handlers.SysLogHandler.LOG_LOCAL0


def facility_code(name: str) -> int:
    """Return the syslog facility code for a configured name."""
    return logging.handlers.SysLogHandler.facility_names.get(name, FACILITY)


def parse_logger_list(raw: str | list[str] | None) -> list[str]:
    """Normalise a logger list from the options form.

    Accepts newline- or comma-separated text as typed by a human, because the
    form is free text: a selector cannot enumerate logger names.
    """
    if not raw:
        return []
    if isinstance(raw, list):
        items = raw
    else:
        items = raw.replace(",", "\n").splitlines()
    return [item.strip() for item in items if item.strip()]


class LoggerFilter(logging.Filter):
    """Include/exclude records by logger name prefix.

    Prefix matching, so `custom_components.foo` covers every child logger the
    integration uses without listing them. Exclude wins over include: the
    common case is forwarding broadly while silencing one known firehose (on
    the source install, one BLE integration at debug emitted a line per
    notification and would have swamped the collector on its own).
    """

    def __init__(self, include: list[str], exclude: list[str]) -> None:
        super().__init__()
        self._include = tuple(include)
        self._exclude = tuple(exclude)

    def filter(self, record: logging.LogRecord) -> bool:
        name = record.name
        if self._exclude and name.startswith(self._exclude):
            return False
        if self._include:
            return name.startswith(self._include)
        return True


def check_reachable(host: str, port: int, protocol: str) -> None:
    """Raise OSError if the collector cannot be reached.

    TCP is verified by connecting. UDP cannot be verified - nothing answers -
    so this only resolves the name and confirms a socket can be created,
    which still catches the realistic setup mistakes (typo'd hostname, no
    route). A UDP entry therefore always sets up; silence is indistinguishable
    from success at this layer, by design of the protocol.
    """
    if protocol == PROTOCOL_TCP:
        with socket.create_connection((host, port), timeout=5):
            return
    socket.getaddrinfo(host, port, type=socket.SOCK_DGRAM)
    socket.socket(socket.AF_INET, socket.SOCK_DGRAM).close()
