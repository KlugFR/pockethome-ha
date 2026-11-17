"""Intégration locale PocketHome (centrale PH-CJ39), sans cloud."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
import voluptuous as vol

from .const import DOMAIN
from .coordinator import PocketHomeCoordinator
from .protocol import PocketHomeClient

VERSION = json.loads((Path(__file__).parent / "manifest.json").read_text())["version"]  # cache-buster des cartes
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
SLOT = vol.Schema({vol.Required("start"): str, vol.Required("temperature"): vol.Coerce(float)})
SET_SCHEMA = vol.Schema(
    {
        vol.Required("program"): vol.All(int, vol.Range(min=1, max=22)),
        vol.Optional("name"): str,
        vol.Required("days"): vol.All([[SLOT]], vol.Length(min=7, max=7)),
    }
)
COPY_SCHEMA = vol.Schema(
    {
        vol.Required("program"): vol.All(int, vol.Range(min=1, max=22)),
        vol.Required("from_day"): vol.In(DAYS),
        vol.Required("to_days"): [vol.In(DAYS)],
    }
)

GET_SCHEMA = vol.Schema({vol.Required("program"): vol.All(int, vol.Range(min=1, max=22))})
CARD_URLS = ("/pockethome/pockethome-program-card.js", "/pockethome/pockethome-cards.js")

PLATFORMS = [Platform.CLIMATE, Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH, Platform.NUMBER, Platform.DATETIME, Platform.BUTTON, Platform.SELECT, Platform.TEXT]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = PocketHomeCoordinator(hass, PocketHomeClient(entry.data[CONF_HOST], entry.data[CONF_PORT]))
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _register_services(hass)
    await _register_card(hass)
    await hass.async_add_executor_job(_install_blueprints, hass.config.config_dir)

    @callback
    def _sync_device_names() -> None:
        """Le nom de la centrale suit dans HA ; un nom choisi à la main dans HA (name_by_user) reste prioritaire."""
        registry = dr.async_get(hass)
        for address, room in coordinator.data["rooms"].items():
            device = registry.async_get_device(identifiers={(DOMAIN, f"{entry.entry_id}_{address}")})
            if device and device.name != room.name:
                registry.async_update_device(device.id, name=room.name)

    entry.async_on_unload(coordinator.async_add_listener(_sync_device_names))
    return True


def _install_blueprints(config_dir: str) -> None:
    """Copie les blueprints fournis dans /config/blueprints/automation/pockethome/ (écrase une version différente)."""
    target = Path(config_dir) / "blueprints" / "automation" / DOMAIN
    target.mkdir(parents=True, exist_ok=True)
    for src in (Path(__file__).parent / "blueprints").glob("*.yaml"):
        dst = target / src.name
        if not dst.exists() or dst.read_bytes() != src.read_bytes():
            shutil.copyfile(src, dst)


async def _register_card(hass: HomeAssistant) -> None:
    """Publie le dossier www/ (carte forkée de heating-schedule-card) et la charge dans le tableau de bord."""
    if hass.data.get(DOMAIN + "_card"):
        return
    await hass.http.async_register_static_paths([StaticPathConfig("/pockethome", str(Path(__file__).parent / "www"), False)])
    for url in CARD_URLS:
        add_extra_js_url(hass, url + "?v=" + VERSION)
    hass.data[DOMAIN + "_card"] = True


def _coordinator(hass: HomeAssistant) -> PocketHomeCoordinator:
    return next(iter(hass.data[DOMAIN].values()))


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, "get_programs"):
        return

    def _as_dict(p):
        return {"number": p.number, "name": p.name, "days": [[{"start": s, "temperature": t} for s, t in d] for d in p.days]}

    async def get_program(call: ServiceCall):
        try:
            return _as_dict(await _coordinator(hass).client.program(call.data["program"]))
        except (ConnectionError, ValueError) as err:
            raise HomeAssistantError(str(err)) from err

    async def get_programs(call: ServiceCall):
        try:
            programs = await _coordinator(hass).client.programs()
        except (ConnectionError, ValueError) as err:
            raise HomeAssistantError(str(err)) from err
        return {"programs": [_as_dict(p) for p in programs]}

    async def _write(number, days, name=None):
        coordinator = _coordinator(hass)
        try:
            await coordinator.client.set_program(number, days, name)
        except (ConnectionError, ValueError) as err:
            raise HomeAssistantError(str(err)) from err
        coordinator._programs.pop(number, None)  # le nom est relu au prochain cycle
        await coordinator.async_request_refresh()

    async def set_program(call: ServiceCall):
        days = [[(s["start"], s["temperature"]) for s in day] for day in call.data["days"]]
        await _write(call.data["program"], days, call.data.get("name"))

    async def copy_day(call: ServiceCall):
        prog = await _coordinator(hass).client.program(call.data["program"])
        days = [list(d) for d in prog.days]
        for to in call.data["to_days"]:
            days[DAYS.index(to)] = list(days[DAYS.index(call.data["from_day"])])
        await _write(call.data["program"], days)

    hass.services.async_register(DOMAIN, "get_program", get_program, schema=GET_SCHEMA, supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "get_programs", get_programs, supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "set_program", set_program, schema=SET_SCHEMA)
    hass.services.async_register(DOMAIN, "copy_day", copy_day, schema=COPY_SCHEMA)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            for name in ("get_program", "get_programs", "set_program", "copy_day"):
                hass.services.async_remove(DOMAIN, name)
        return True
    return False
