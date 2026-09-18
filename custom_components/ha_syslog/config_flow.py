"""Config and options flow for the remote syslog forwarder."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    ConfigEntry,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_EXCLUDE_LOGGERS,
    CONF_FACILITY,
    CONF_INCLUDE_LOGGERS,
    CONF_LEVEL,
    CONF_PROTOCOL,
    CONF_TAG,
    DEFAULT_FACILITY,
    DEFAULT_LEVEL,
    DEFAULT_PORT,
    DEFAULT_PROTOCOL,
    DEFAULT_TAG,
    DOMAIN,
    FACILITIES,
    LEVELS,
    PROTOCOLS,
    check_reachable,
)


def _select(options: list[str], key: str) -> selector.SelectSelector:
    """Dropdown of fixed choices, labelled through the translation key."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options,
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key=key,
        )
    )


def _logger_list_field() -> selector.TextSelector:
    """Free-text, multiline: logger names cannot be enumerated for a picker."""
    return selector.TextSelector(selector.TextSelectorConfig(multiline=True))


class HaSyslogConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ask where to send the log, and verify we can reach it."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the collector's address."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            protocol = user_input[CONF_PROTOCOL]
            # One forwarder per collector: a second entry for the same target
            # would attach a second handler and duplicate every record.
            await self.async_set_unique_id(f"{host}:{port}/{protocol}")
            self._abort_if_unique_id_configured()
            try:
                await self.hass.async_add_executor_job(
                    check_reachable, host, port, protocol
                )
            except OSError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"{host}:{port}",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): selector.TextSelector(),
                    vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=65535)
                    ),
                    vol.Required(
                        CONF_PROTOCOL, default=DEFAULT_PROTOCOL
                    ): _select(PROTOCOLS, CONF_PROTOCOL),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlowWithReload:
        """Return the options flow."""
        return HaSyslogOptionsFlow()


class HaSyslogOptionsFlow(OptionsFlowWithReload):
    """What to forward, how to label it, and what to leave out."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the forwarding options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_LEVEL,
                        default=options.get(CONF_LEVEL, DEFAULT_LEVEL),
                    ): _select(LEVELS, CONF_LEVEL),
                    vol.Required(
                        CONF_TAG, default=options.get(CONF_TAG, DEFAULT_TAG)
                    ): selector.TextSelector(),
                    vol.Required(
                        CONF_FACILITY,
                        default=options.get(CONF_FACILITY, DEFAULT_FACILITY),
                    ): _select(FACILITIES, CONF_FACILITY),
                    vol.Optional(
                        CONF_EXCLUDE_LOGGERS,
                        default=options.get(CONF_EXCLUDE_LOGGERS, ""),
                    ): _logger_list_field(),
                    vol.Optional(
                        CONF_INCLUDE_LOGGERS,
                        default=options.get(CONF_INCLUDE_LOGGERS, ""),
                    ): _logger_list_field(),
                }
            ),
        )
