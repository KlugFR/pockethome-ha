from __future__ import annotations

import logging
import time
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, SCAN_INTERVAL_SECONDS
from .protocol import PocketHomeClient

_LOGGER = logging.getLogger(__name__)
PROGRAM_TTL = 3600  # les noms de programmes changent rarement


class PocketHomeCoordinator(DataUpdateCoordinator):
    """data = {"rooms": {adresse: Room}, "modes": Modes, "programs": {numéro: nom}}"""

    def __init__(self, hass: HomeAssistant, client: PocketHomeClient) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS))
        self.client = client
        self.rated_power: dict[int, float | None] = {}  # adresse -> W, saisi dans HA (entité RatedPower)
        self._programs: dict[int, tuple[str, float]] = {}  # numéro -> (nom, instant de lecture)

    async def _program_names(self, rooms) -> dict[int, str]:
        now = time.monotonic()
        # noms des programmes des pièces, plus un programme inconnu par cycle (liste du select)
        todo = {r.program for r in rooms} | set(sorted(set(range(1, 23)) - self._programs.keys())[:1])
        for n in todo:
            name, at = self._programs.get(n, (None, 0.0))
            if name is None or now - at > PROGRAM_TTL:
                try:
                    name = (await self.client.program(n)).name
                except (ConnectionError, ValueError):
                    continue  # on garde l'ancien nom
                self._programs[n] = (name, now)
        return {n: v[0] for n, v in self._programs.items()}

    async def _async_update_data(self):
        try:
            rooms = await self.client.rooms()
            modes = await self.client.modes()
            programs = await self._program_names(rooms)
        except (ConnectionError, ValueError) as err:
            raise UpdateFailed(str(err)) from err
        return {"rooms": {r.address: r for r in rooms}, "modes": modes, "programs": programs}

    async def async_refresh_thermostats(self) -> None:
        """Après un changement de mode : actualisation radio, pièce par pièce (les thermostats sinon n'apprennent le mode qu'à leur prochain contact)."""
        try:
            rooms = await self.client.refresh_rooms()
        except (ConnectionError, ValueError) as err:
            _LOGGER.warning("actualisation des thermostats impossible : %s", err)
            return
        data = dict(self.data)
        data["rooms"] = {**data["rooms"], **{r.address: r for r in rooms}}
        self.async_set_updated_data(data)
