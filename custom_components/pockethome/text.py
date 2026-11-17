from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .entity import room_device_info


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data["pockethome"][entry.entry_id]
    async_add_entities(RoomName(coordinator, entry, a) for a in coordinator.data["rooms"])


class RoomName(CoordinatorEntity, TextEntity):
    """Nom de la pièce tel que la centrale (et l'app) l'affiche : 16 caractères au plus."""

    _attr_has_entity_name = True
    _attr_translation_key = "room_name"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min = 1
    _attr_native_max = 16

    def __init__(self, coordinator, entry, address):
        super().__init__(coordinator)
        self._address = address
        self._attr_unique_id = f"{entry.entry_id}_{address}_room_name"
        self._attr_device_info = room_device_info(entry, coordinator.data["rooms"][address])

    @property
    def available(self):
        room = (self.coordinator.data or {}).get("rooms", {}).get(self._address)
        return super().available and room is not None and not room.unreachable

    @property
    def native_value(self):
        return self.coordinator.data["rooms"][self._address].name

    async def async_set_value(self, value: str):
        try:
            room = await self.coordinator.client.set_room(self._address, name=value)
        except (ConnectionError, ValueError) as err:
            raise HomeAssistantError(str(err)) from err
        self.coordinator.data["rooms"][self._address] = room
        self.coordinator.async_set_updated_data(self.coordinator.data)
