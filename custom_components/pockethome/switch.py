"""Modes globaux de la centrale : été, vacances, absence."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .entity import hub_device_info

MODES = (("summer", "set_summer"), ("holiday", "set_holiday"), ("absence", "set_absence"))


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data["pockethome"][entry.entry_id]
    async_add_entities(ModeSwitch(coordinator, entry, *m) for m in MODES)


class ModeSwitch(CoordinatorEntity, SwitchEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key, setter):
        super().__init__(coordinator)
        self._key, self._setter = key, setter
        self._attr_translation_key = key
        self._attr_extra_state_attributes = {"role": key}  # retrouvé par pockethome-modes-card
        self._attr_unique_id = f"{entry.entry_id}_mode_{key}"
        self._attr_device_info = hub_device_info(entry)

    @property
    def is_on(self):
        return getattr(self.coordinator.data["modes"], self._key)

    async def _set(self, on: bool):
        try:
            modes = await getattr(self.coordinator.client, self._setter)(on)
        except (ConnectionError, ValueError) as err:
            raise HomeAssistantError(str(err)) from err
        data = dict(self.coordinator.data)
        data["modes"] = modes
        self.coordinator.async_set_updated_data(data)
        # les thermostats sur pile n'apprennent le changement qu'à leur prochain contact : on les actualise
        self.coordinator.hass.async_create_task(self.coordinator.async_refresh_thermostats())

    async def async_turn_on(self, **kwargs):
        await self._set(True)

    async def async_turn_off(self, **kwargs):
        await self._set(False)
