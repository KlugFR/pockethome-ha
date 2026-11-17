"""Début et fin des vacances."""
from __future__ import annotations

from datetime import datetime

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .entity import hub_device_info


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data["pockethome"][entry.entry_id]
    async_add_entities([HolidayDate(coordinator, entry, "start"), HolidayDate(coordinator, entry, "end")])


class HolidayDate(CoordinatorEntity, DateTimeEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, which):
        super().__init__(coordinator)
        self._which = which
        self._attr_translation_key = f"holiday_{which}"
        self._attr_unique_id = f"{entry.entry_id}_holiday_{which}"
        self._attr_extra_state_attributes = {"role": f"holiday_{which}"}
        self._attr_device_info = hub_device_info(entry)

    @property
    def native_value(self):
        m = self.coordinator.data["modes"]
        s = m.holiday_start if self._which == "start" else m.holiday_end
        return datetime.fromisoformat(s).replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)

    async def async_set_value(self, value: datetime):
        m = self.coordinator.data["modes"]
        new = dt_util.as_local(value).replace(tzinfo=None, second=0, microsecond=0)
        start, end = datetime.fromisoformat(m.holiday_start), datetime.fromisoformat(m.holiday_end)
        start, end = (new, end) if self._which == "start" else (start, new)
        try:
            modes = await self.coordinator.client.set_holiday_period(start, end, m.holiday_temp)
        except (ConnectionError, ValueError) as err:
            raise HomeAssistantError(str(err)) from err
        data = dict(self.coordinator.data)
        data["modes"] = modes
        self.coordinator.async_set_updated_data(data)
