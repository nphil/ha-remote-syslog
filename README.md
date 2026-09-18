<img src="icon.png" align="right" width="96" alt="">

# Remote Syslog for Home Assistant

Ship Home Assistant's **own log** to a syslog collector, so it survives a restart.

[![hacs](https://img.shields.io/badge/HACS-custom-41BDF5.svg)](https://hacs.xyz)

## Why

`/config/home-assistant.log` rotates **only at restart** and keeps exactly one
previous copy (`home-assistant.log.1`). There is no size cap and no daily
rotation, so the entire log history is *this run plus the previous one*.

That is fine until you need it. Measured on the install this was written for,
three restarts in a single evening discarded everything logged before them —
and a fault that needs a restart to clear takes its own diagnosis with it. If
you have ever turned on debug logging, reproduced a bug, restarted to apply a
fix, and then wanted to compare the before and after: the before is gone.

Home Assistant has no built-in option for this. The core `syslog` integration
is a *notify* service that writes to the local socket, and `logger:` only sets
levels — it exposes no handler configuration. Add-ons each ship their own logs
(Zigbee2MQTT has a `log_syslog:` block), but Core does not.

This integration attaches a real `logging.handlers.SysLogHandler` to the root
logger. Being handler-based rather than file-based, nothing depends on log
rotation, truncation, or a `tail` process surviving a restart.

## Install

**HACS → three-dot menu → Custom repositories**, add this repository with
category **Integration**, download it, restart Home Assistant, then
**Settings → Devices & Services → Add Integration → Remote Syslog**.

## Settings

Set when adding it:

| | |
|---|---|
| **Host** | Hostname or IP of the collector. |
| **Port** | Usually 514. |
| **Protocol** | UDP is what most collectors listen on by default (rsyslog's `imudp`). TCP never drops a record but the collector must accept it. |

Changeable any time under **Configure**, applied without a restart:

| | |
|---|---|
| **Minimum level** | Default **Warning**. Everything at this level and above is forwarded. |
| **Syslog tag** | Identifies Home Assistant in the collector's logs; the integration's logger name is appended automatically, so a record arrives as `ha-core[homeassistant.components.mqtt]: WARNING ...`. |
| **Facility** | Default `local0`, which keeps Core distinct from add-ons and network gear reporting to the same collector. |
| **Exclude loggers** | One name per line, matched by prefix — `custom_components.foo` covers all of its children. For silencing a known firehose. |
| **Only these loggers** | One per line, also prefix-matched. Empty forwards everything; set it for a narrow capture of specific integrations. |

### On volume

Keep the level at **Warning** for normal use. Debug forwards *everything*: on
the source install a single integration at debug produced **2.4 MB of log in
31 minutes**. Most collectors rotate by size — Unraid's syslog server, for
instance, defaults to 500 MB keeping one file — so a runaway logger can churn
through the ceiling and evict the very history you wanted to keep.

The useful pattern is to leave this at Warning and raise **one** logger when
investigating, via `logger.set_level` or a `logger:` block, then put it back.

## What you get

A service device with two diagnostic sensors:

- **Forwarded records** — count sent since the entry loaded, with `dropped`
  and `last_error` attributes.
- **Last forwarded** — timestamp of the most recent record.

They exist because a log shipper that silently stops is worse than none at
all: the gap only becomes apparent when you need the history. UDP gives no
delivery signal, so these honestly report what *this* end did — a counter that
stops climbing is the signal to go looking.

## Notes

- Records are sent through a `QueueHandler`/`QueueListener` pair, so the socket
  write happens on a background thread and never adds latency to the event
  loop. This is the same approach Core uses for its own file handler.
- `SysLogHandler` sends `<PRI>message` with no timestamp or hostname. That is
  intentional: the collector stamps its receive time and resolves the sender
  itself, so records carry one consistent clock instead of two that can
  disagree.
- The handler detaches on `EVENT_HOMEASSISTANT_STOP`. Home Assistant does not
  unload config entries at shutdown, and records emitted during shutdown are
  exactly the ones worth keeping.
- If the collector is unreachable at startup the entry retries rather than
  failing permanently. A diagnostic aid must never be load-bearing.

### Branding

`brand/` holds the icon at the sizes [home-assistant/brands](https://github.com/home-assistant/brands)
expects (`icon.png` 256×256, `icon@2x.png` 512×512). Until a submission there
is merged, Home Assistant and HACS show a generic placeholder for any custom
integration — that is a limitation of the brands registry, not of this repo.

## License

MIT
