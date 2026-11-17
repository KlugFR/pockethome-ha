"""Températures du mode absence et des vacances."""
from __future__ import annotations

from datetime import datetime

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode, RestoreNumber
from homeassistant.const import EntityCategory, UnitOfPower, UnitOfTemperature
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .entity import hub_device_info, room_device_info
from .protocol import MAX_SETPOINT, MIN_SETPOINT


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data["pockethome"][entry.entry_id]
    async_add_entities([ModeTemp(coordinator, entry, "absence"), ModeTemp(coordinator, entry, "holiday")])
    async_add_entities(RatedPower(coordinator, entry, a) for a in coordinator.data["rooms"])


class RatedPower(RestoreNumber):
    """Puissance électrique du radiateur commandé par ce thermostat. Réglage saisi dans HA, rien à voir avec la centrale :
    il alimente les capteurs de puissance et d'énergie (statistiques)."""

    _attr_has_entity_name = True
    _attr_translation_key = "rated_power"
    _attr_device_class = NumberDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_native_min_value = 0
    _attr_native_max_value = 10000
    _attr_native_step = 10
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, entry, address):
        self._coordinator, self._address = coordinator, address
        self._attr_unique_id = f"{entry.entry_id}_{address}_rated_power"
        self._attr_device_info = room_device_info(entry, coordinator.data["rooms"][address])
        self._attr_native_value = None

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if (last := await self.async_get_last_number_data()) is not None:
            self._attr_native_value = last.native_value
        self._share()

    def _share(self):
        self._coordinator.rated_power[self._address] = self._attr_native_value

    async def async_set_native_value(self, value: float):
        self._attr_native_value = value
        self._share()
        self.async_write_ha_state()
        self._coordinator.async_update_listeners()


class ModeTemp(CoordinatorEntity, NumberEntity):
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = MIN_SETPOINT
    _attr_native_max_value = MAX_SETPOINT
    _attr_native_step = 0.5
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, entry, key):
        super().__init__(coordinator)
        self._key = key
        self._attr_translation_key = f"{key}_temp"
        self._attr_unique_id = f"{entry.entry_id}_temp_{key}"
        self._attr_extra_state_attributes = {"role": f"{key}_temp"}
        self._attr_device_info = hub_device_info(entry)

    @property
    def native_value(self):
        m = self.coordinator.data["modes"]
        return m.absence_temp if self._key == "absence" else m.holiday_temp

    async def async_set_native_value(self, value: float):
        c = self.coordinator.client
        m = self.coordinator.data["modes"]
        try:
            if self._key == "absence":
                modes = await c.set_absence_temp(value)
            else:
                modes = await c.set_holiday_period(datetime.fromisoformat(m.holiday_start), datetime.fromisoformat(m.holiday_end), value)
        except (ConnectionError, ValueError) as err:
            raise HomeAssistantError(str(err)) from err
        data = dict(self.coordinator.data)
        data["modes"] = modes
        self.coordinator.async_set_updated_data(data)
