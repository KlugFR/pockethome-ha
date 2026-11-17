from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .entity import room_device_info


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data["pockethome"][entry.entry_id]
    async_add_entities(ProgramSelect(coordinator, entry, a) for a in coordinator.data["rooms"])


class ProgramSelect(CoordinatorEntity, SelectEntity):
    """Programme appliqué à la pièce (écrit dans la centrale, pas de planning côté HA)."""

    _attr_has_entity_name = True
    _attr_translation_key = "program"

    def __init__(self, coordinator, entry, address):
        super().__init__(coordinator)
        self._address = address
        self._attr_unique_id = f"{entry.entry_id}_{address}_program_select"
        self._attr_device_info = room_device_info(entry, coordinator.data["rooms"][address])

    def _label(self, n: int) -> str:
        name = self.coordinator.data["programs"].get(n)
        return f"{n} · {name}" if name else str(n)

    @property
    def available(self):
        room = (self.coordinator.data or {}).get("rooms", {}).get(self._address)
        return super().available and room is not None and not room.unreachable

    @property
    def options(self):
        return [self._label(n) for n in range(1, 23)]

    @property
    def current_option(self):
        return self._label(self.coordinator.data["rooms"][self._address].program)

    async def async_select_option(self, option: str):
        number = int(option.split(" ")[0])
        try:
            room = await self.coordinator.client.set_room(self._address, program=number)
        except (ConnectionError, ValueError) as err:
            raise HomeAssistantError(str(err)) from err
        self.coordinator.data["rooms"][self._address] = room
        self.coordinator.async_set_updated_data(self.coordinator.data)
