from __future__ import annotations

import time

from homeassistant.components.sensor import RestoreSensor, SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfPower
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .entity import room_device_info


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data["pockethome"][entry.entry_id]
    async_add_entities(
        cls(coordinator, entry, a) for a in coordinator.data["rooms"] for cls in (ProgramSensor, LinkSensor, PowerSensor, EnergySensor)
    )


class _RoomSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    key = ""

    def __init__(self, coordinator, entry, address):
        super().__init__(coordinator)
        self._address = address
        self._attr_unique_id = f"{entry.entry_id}_{address}_{self.key}"
        self._attr_device_info = room_device_info(entry, coordinator.data["rooms"][address])

    @property
    def _room(self):
        return self.coordinator.data["rooms"][self._address]

    @property
    def available(self):  # pièce absente des données : indisponible plutôt qu'une erreur
        return super().available and self._address in (self.coordinator.data or {}).get("rooms", {})


class ProgramSensor(_RoomSensor):
    key = "program"
    _attr_translation_key = "program"

    @property
    def native_value(self):
        n = self._room.program
        return self.coordinator.data["programs"].get(n, str(n))


class LinkSensor(_RoomSensor):
    """Qualité du lien radio brute : plus bas = meilleur (barres de l'app : WC 46 = 5/5, Dressing 69 = 1/5)."""

    key = "link"
    _attr_translation_key = "link"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        return self._room.link


def _power(coordinator, address):
    """Puissance commandée : celle du radiateur quand la sortie du thermostat est active, sinon 0. None si inconnue."""
    room = coordinator.data["rooms"].get(address)
    rated = coordinator.rated_power.get(address)
    if room is None or room.unreachable or rated is None:
        return None
    return rated if room.output_on else 0


class PowerSensor(_RoomSensor):
    key = "power"
    _attr_translation_key = "power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        return _power(self.coordinator, self._address)


class EnergySensor(_RoomSensor, RestoreSensor):
    """Énergie commandée = puissance intégrée dans le temps (relevé toutes les 60 s : approximation du temps de chauffe)."""

    key = "energy"
    _attr_translation_key = "energy"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 3
    MAX_GAP = 300  # s : au-delà (panne, redémarrage), l'intervalle n'est pas compté

    def __init__(self, *args):
        super().__init__(*args)
        self._kwh = 0.0
        self._last = None  # (instant monotone, W)

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if (last := await self.async_get_last_sensor_data()) is not None and last.native_value is not None:
            self._kwh = float(last.native_value)

    def _handle_coordinator_update(self):
        now, watts = time.monotonic(), _power(self.coordinator, self._address)
        if self._last and now - self._last[0] <= self.MAX_GAP:
            self._kwh += self._last[1] * (now - self._last[0]) / 3_600_000  # la puissance relevée au début de l'intervalle
        self._last = (now, watts or 0) if watts is not None else None
        super()._handle_coordinator_update()

    @property
    def native_value(self):
        return round(self._kwh, 4)
