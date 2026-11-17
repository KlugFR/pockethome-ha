from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .entity import room_device_info


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data["pockethome"][entry.entry_id]
    ents = [
        Battery(coordinator, entry, a)
        for a, r in coordinator.data["rooms"].items()
        if not r.unreachable  # pas de pile sur les thermostats hors réseau de cette installation
    ]
    ents += [NoSignal(coordinator, entry, a) for a in coordinator.data["rooms"]]
    async_add_entities(ents)


class Battery(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.BATTERY  # on = batterie faible
    # Les accus NiCd/NiMH sont signalés « faibles » dès leur pose : peu utile, donc désactivé à la création.
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator, entry, address):
        super().__init__(coordinator)
        self._address = address
        self._attr_unique_id = f"{entry.entry_id}_{address}_battery"
        self._attr_device_info = room_device_info(entry, coordinator.data["rooms"][address])

    @property
    def available(self):
        return super().available and self._address in (self.coordinator.data or {}).get("rooms", {})

    @property
    def is_on(self):
        return self.coordinator.data["rooms"][self._address].battery_low


class NoSignal(CoordinatorEntity, BinarySensorEntity):
    """La centrale ne reçoit plus le thermostat (LED rouge clignotante de la centrale) : en général, piles vides."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_translation_key = "no_signal"

    def __init__(self, coordinator, entry, address):
        super().__init__(coordinator)
        self._address = address
        self._attr_unique_id = f"{entry.entry_id}_{address}_no_signal"
        self._attr_device_info = room_device_info(entry, coordinator.data["rooms"][address])

    @property
    def available(self):
        return super().available and self._address in (self.coordinator.data or {}).get("rooms", {})

    @property
    def is_on(self):
        return self.coordinator.data["rooms"][self._address].unreachable
