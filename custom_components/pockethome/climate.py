"""Une entité climate par pièce : consigne, mode auto/manu, allumé/éteint."""
from __future__ import annotations

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACAction, HVACMode
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .entity import room_device_info
from .protocol import MAX_SETPOINT, MIN_SETPOINT


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data["pockethome"][entry.entry_id]
    async_add_entities(RoomClimate(coordinator, entry, a) for a in coordinator.data["rooms"])


class RoomClimate(CoordinatorEntity, ClimateEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.AUTO, HVACMode.HEAT]  # HEAT = manuel
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
    )
    _attr_min_temp = MIN_SETPOINT
    _attr_max_temp = MAX_SETPOINT
    _attr_target_temperature_step = 0.5
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coordinator, entry, address):
        super().__init__(coordinator)
        self._address = address
        self._attr_unique_id = f"{entry.entry_id}_{address}_climate"
        self._attr_device_info = room_device_info(entry, coordinator.data["rooms"][address])

    @property
    def _room(self):
        return (self.coordinator.data or {}).get("rooms", {}).get(self._address)

    @property
    def available(self):  # hors réseau : pas de température fiable ; pièce absente des données : indisponible
        return super().available and self._room is not None and not self._room.unreachable

    @property
    def native_current_temperature(self):
        return self._room.temperature

    @property
    def native_target_temperature(self):
        return self._room.setpoint

    @property
    def hvac_mode(self):
        r = self._room
        return HVACMode.OFF if r.off else HVACMode.AUTO if r.auto else HVACMode.HEAT

    @property
    def hvac_action(self):
        r = self._room
        return HVACAction.OFF if r.off else HVACAction.HEATING if r.output_on else HVACAction.IDLE

    @property
    def extra_state_attributes(self):
        n = self._room.program
        return {"program": self.coordinator.data["programs"].get(n, str(n))}

    async def _write(self, **kwargs):
        try:
            room = await self.coordinator.client.set_room(self._address, **kwargs)
        except (ConnectionError, ValueError) as err:
            raise HomeAssistantError(str(err)) from err
        self.coordinator.data["rooms"][self._address] = room
        self.coordinator.async_set_updated_data(self.coordinator.data)

    async def async_set_temperature(self, **kwargs):
        if (t := kwargs.get(ATTR_TEMPERATURE)) is not None:
            await self._write(setpoint=t)

    async def async_set_hvac_mode(self, hvac_mode):
        if hvac_mode == HVACMode.OFF:
            await self._write(off=True)
        else:
            await self._write(off=False, auto=hvac_mode == HVACMode.AUTO)
