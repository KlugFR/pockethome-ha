from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


def hub_device_info(entry) -> DeviceInfo:
    return DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name=entry.title, manufacturer="Elektrobock", model="PH-CJ39 WiFi")


def room_device_info(entry, room) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_{room.address}")},
        name=room.name,
        manufacturer="Elektrobock",
        via_device=(DOMAIN, entry.entry_id),
    )
