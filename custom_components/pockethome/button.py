"""Actualisation radio d'une pièce. Elle sollicite la pile du thermostat : délai minimum entre deux appuis."""
from __future__ import annotations

import time

from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .entity import room_device_info

COOLDOWN = 300  # secondes


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data["pockethome"][entry.entry_id]
    async_add_entities(
        RefreshButton(coordinator, entry, a) for a, r in coordinator.data["rooms"].items() if not r.unreachable
    )


class RefreshButton(CoordinatorEntity, ButtonEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "refresh"

    def __init__(self, coordinator, entry, address):
        super().__init__(coordinator)
        self._address = address
        self._last = -COOLDOWN
        self._attr_unique_id = f"{entry.entry_id}_{address}_refresh"
        self._attr_device_info = room_device_info(entry, coordinator.data["rooms"][address])

    async def async_press(self):
        wait = COOLDOWN - (time.monotonic() - self._last)
        if wait > 0:
            raise HomeAssistantError(f"Actualisation déjà faite : encore {int(wait)} s (ménage la pile du thermostat)")
        try:
            room = await self.coordinator.client.refresh_room(self._address)
        except (ConnectionError, ValueError) as err:
            raise HomeAssistantError(str(err)) from err
        self._last = time.monotonic()
        data = dict(self.coordinator.data)
        data["rooms"] = {**data["rooms"], self._address: room}
        self.coordinator.async_set_updated_data(data)
