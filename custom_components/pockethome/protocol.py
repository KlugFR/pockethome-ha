"""Client TLV pour la centrale PH-CJ39 (TCP 4000). Aucune dépendance Home Assistant.

Lecture seule pour l'instant. Voir pockethome_protocole.md pour le format.
"""
from __future__ import annotations

import asyncio
import struct
from dataclasses import dataclass
from datetime import datetime

PORT = 4000
ROOM_CODE = 0x63  # 'c'
RECORD_LEN = 37
UNUSED_SLOT = 0xBD  # 23:50, valeur de remplissage des plages inutilisées
MAX_SLOTS = 6
PROGRAM_LEN = 102
MIN_SETPOINT, MAX_SETPOINT = 5.0, 30.0  # bornes prudentes, limites réelles de la centrale non vérifiées


def tlv(tag: int, val: bytes = b"") -> bytes:
    return struct.pack(">HH", tag, len(val)) + val


def tlv_value(resp: bytes) -> bytes:
    """Valeur d'une réponse à un seul TLV."""
    if len(resp) < 4:
        raise ValueError("reply too short")
    return resp[4 : 4 + (struct.unpack(">H", resp[2:4])[0] & 0x3FFF)]


@dataclass
class Room:
    address: int
    name: str
    program: int
    auto: bool
    off: bool
    setpoint: float | None  # None si la pièce est éteinte
    temperature: float | None  # None si hors réseau
    output_on: bool
    unreachable: bool
    battery_low: bool
    link: int  # qualité du lien : plus bas = meilleur


def parse_room(v: bytes) -> Room:
    if len(v) < RECORD_LEN or v[0] != ROOM_CODE:
        raise ValueError("invalid room record")
    flags, s1, t, s3 = v[4], v[10], v[11], v[12]
    unreachable = bool(s1 & 0x80)
    off = bool(flags & 0x04)
    temp = ((t & 0x7F) + (s3 & 0x0F) / 10) * (-1 if t & 0x80 else 1)
    return Room(
        address=v[2],
        name=v[17:33].decode("latin1").strip(),
        program=v[3],
        auto=bool(flags & 0x01),
        off=off,
        setpoint=None if off else v[5] / 2,
        temperature=None if unreachable else temp,
        output_on=bool(s1 & 0x01),
        unreachable=unreachable,
        battery_low=bool(s3 & 0x80),
        link=v[36],
    )


def build_write(v: bytes, *, setpoint: float, auto: bool, off: bool, program: int | None = None, name: str | None = None) -> bytes:
    """Valeur d'une écriture 0050 (30 octets), refaite depuis la fiche lue `v`."""
    return (
        bytes([ROOM_CODE, 0x15, v[2], 0x01, v[3] if program is None else program, 0x02 if auto else 0x00, round(setpoint * 2), 0, 0, 0x02 if off else 0, 0, 0])
        + (v[17:33] if name is None else name.encode("latin1").ljust(16, b" "))
        + bytes([v[33], v[14]])
    )


def state_to_mask(st: bytes) -> int:
    """État 803a -> masque d'écriture 003a (bit 0 absence, bit 2 drapeau inconnu `04`, bit 3 vacances)."""
    return (st[0] & 1) | ((st[0] >> 5 & 1) << 2) | ((st[1] >> 4 & 1) << 3)


def encode_date(d: datetime) -> bytes:
    return bytes([d.year - 2000, d.month, d.day, d.hour, d.minute])


def holiday_frame(start: datetime, end: datetime, temp: float, mask: int) -> bytes:
    """Trame groupée envoyée par l'app pour enregistrer la période de vacances."""
    body = tlv(0x000E, encode_date(start) + encode_date(end) + bytes([round(temp * 2)])) + tlv(0x003A, bytes([mask, 3]))
    return b"\x7f\xff" + struct.pack(">H", len(body)) + body


@dataclass
class Program:
    number: int
    name: str
    days: list[list[tuple[str, float]]]  # 7 jours (lundi d'abord) de (début "HH:MM", °C)


def decode_start(b: int) -> str:
    """Octet de début -> "HH:MM" : 8 cases de 10 min par heure (octet = 8 × heure + minutes / 10)."""
    return f"{b // 8:02d}:{b % 8 * 10:02d}"


def encode_start(hhmm: str) -> int:
    h, m = (int(x) for x in hhmm.split(":"))
    if not (0 <= h <= 23 and m in (0, 10, 20, 30, 40, 50)):
        raise ValueError(f"invalid time or not on the 10 min grid: {hhmm}")
    return 8 * h + m // 10


def parse_program(v: bytes) -> Program:
    if len(v) != PROGRAM_LEN:
        raise ValueError("invalid program")
    days = []
    for d in range(7):
        day = v[1 + 12 * d : 13 + 12 * d]
        # Plage inutilisée : 0xBD (programmes écrits par l'app) ou début répété (programmes d'usine :
        # 6 fois 00:00, ou 21:00 en bourrage). On ne garde que les débuts strictement croissants.
        slots, last = [], -1
        for i in range(0, 12, 2):
            if day[i] != UNUSED_SLOT and day[i] > last:
                slots.append((decode_start(day[i]), day[i + 1] / 2))
                last = day[i]
        days.append(slots)
    return Program(v[0], v[-16:].decode("latin1").strip(), days)


def build_program(number: int, name: str, days: list[list[tuple[str, float]]], flag: int = 0) -> bytes:
    """Valeur d'un programme (102 octets). `days` : 7 jours de 1 à 6 plages (début "HH:MM", °C)."""
    if len(days) != 7:
        raise ValueError("7 days expected (Monday first)")
    out = bytearray([number])
    for day in days:
        if not 1 <= len(day) <= MAX_SLOTS:
            raise ValueError(f"1 to {MAX_SLOTS} slots per day")
        starts = [encode_start(h) for h, _ in day]
        if starts != sorted(set(starts)):
            raise ValueError("slot starts must be strictly increasing")
        for (_, t) in day:
            if not MIN_SETPOINT <= t <= MAX_SETPOINT or t * 2 != int(t * 2):
                raise ValueError(f"invalid temperature (5 to 30 °C in 0.5 steps): {t}")
        slots = [(s, round(t * 2)) for s, (_, t) in zip(starts, day)]
        slots += [(UNUSED_SLOT, slots[-1][1])] * (MAX_SLOTS - len(slots))  # remplissage comme l'app
        out += bytes(b for slot in slots for b in slot)
    if len(name.encode("latin1")) > 16:
        raise ValueError("name too long (16 characters)")
    return bytes(out) + bytes([flag]) + name.encode("latin1").ljust(16)


@dataclass
class Modes:
    summer: bool
    holiday: bool
    absence: bool
    absence_temp: float
    holiday_start: str  # "AAAA-MM-JJ HH:MM"
    holiday_end: str
    holiday_temp: float


def _date(b: bytes) -> str:
    return f"{2000 + b[0]:04d}-{b[1]:02d}-{b[2]:02d} {b[3]:02d}:{b[4]:02d}"


def parse_modes(summer: bytes, state: bytes, absence_temp: bytes, period: bytes) -> Modes:
    return Modes(
        summer=summer == b"A",
        holiday=bool(state[1] & 0x10),
        absence=bool(state[0] & 0x01),
        absence_temp=absence_temp[0] / 2,
        holiday_start=_date(period[0:5]),
        holiday_end=_date(period[5:10]),
        holiday_temp=period[10] / 2,
    )


class PocketHomeClient:
    """Une requête à la fois, une connexion par requête (la CJ39 est capricieuse)."""

    def __init__(self, host: str, port: int = PORT) -> None:
        self.host, self.port = host, port
        self._lock = asyncio.Lock()
        self._addresses: list[int] = []  # liste des pièces : stable, lue une fois (la centrale répond parfois à côté)
        self._last_setpoint: dict[int, float] = {}  # pour rallumer une pièce éteinte (consigne lue = 0)

    async def _ask(self, frame: bytes, check=None) -> bytes:
        async with self._lock:
            for _ in range(4):
                await asyncio.sleep(0.3)
                try:
                    r, w = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), 5)
                    try:
                        w.write(frame)
                        await w.drain()
                        data = await asyncio.wait_for(r.read(2048), 3)
                    finally:
                        w.close()
                except (asyncio.TimeoutError, OSError):
                    continue
                if data and (check is None or check(data)):
                    return data
        raise ConnectionError("no valid reply from the central unit")

    async def info(self) -> str:
        """Nom de la centrale (ex. PHWIFI_000481)."""
        return tlv_value(await self._ask(tlv(0x378C))).decode("latin1")

    async def room_addresses(self) -> list[int]:
        if self._addresses:
            return self._addresses
        v = tlv_value(await self._ask(tlv(0x803D, b"\x00\x07")))
        found = sorted(a for c, a in zip(v[0::2], v[1::2]) if c == ROOM_CODE)
        if not found:
            raise ConnectionError("room list empty or invalid")
        self._addresses = found
        return found

    async def _room_raw(self, address: int) -> bytes:
        """Fiche brute en mode 00 (jamais de radio). La réponse doit porter l'adresse demandée."""
        key = bytes([ROOM_CODE, 0x15, address, 0])
        ok = lambda d: tlv_value(d)[:3] == key[:3] and len(tlv_value(d)) >= RECORD_LEN
        return tlv_value(await self._ask(tlv(0x8050, key), ok))

    async def room(self, address: int) -> Room:
        room = parse_room(await self._room_raw(address))
        if room.setpoint is not None:
            self._last_setpoint[address] = room.setpoint
        return room

    async def set_room(self, address: int, *, setpoint: float | None = None, auto: bool | None = None, off: bool | None = None, program: int | None = None, name: str | None = None) -> Room:
        """Écrit consigne, mode auto/manu, éteint/allume une pièce, puis relit pour vérifier."""
        v = await self._room_raw(address)
        cur = parse_room(v)
        if cur.unreachable:
            raise ValueError("room is out of range (no radio link)")
        auto = cur.auto if auto is None else auto
        off = cur.off if off is None else off
        if setpoint is None:
            setpoint = cur.setpoint if cur.setpoint is not None else self._last_setpoint.get(address)
        if setpoint is None:
            raise ValueError("unknown setpoint to turn the room back on")
        if not MIN_SETPOINT <= setpoint <= MAX_SETPOINT:
            raise ValueError(f"setpoint out of range ({MIN_SETPOINT}-{MAX_SETPOINT} °C)")
        if program is not None and not 1 <= program <= 22:
            raise ValueError("program number must be 1 to 22")
        if name is not None:
            name = name.strip()
            if not 1 <= len(name) <= 16:
                raise ValueError("name must be 1 to 16 characters")
            name.encode("latin1")  # UnicodeEncodeError (ValueError) si hors jeu de caractères
        key = bytes([ROOM_CODE, 0x15, address])
        await self._ask(tlv(0x0050, build_write(v, setpoint=setpoint, auto=auto, off=off, program=program, name=name)), lambda d: tlv_value(d)[:3] == key)
        await asyncio.sleep(1)
        new = await self.room(address)
        if new.auto != auto or new.off != off or (not off and new.setpoint != setpoint) or (program is not None and new.program != program) or (name is not None and new.name != name):
            raise ConnectionError(f"write not confirmed by the read-back: {new}")
        return new

    async def rooms(self) -> list[Room]:
        return [await self.room(a) for a in await self.room_addresses()]

    async def _program_raw(self, number: int) -> bytes:
        ok = lambda d: len(tlv_value(d)) == PROGRAM_LEN and tlv_value(d)[0] == number
        return tlv_value(await self._ask(tlv(0x800D, bytes([number])), ok))

    async def program(self, number: int) -> Program:
        return parse_program(await self._program_raw(number))

    async def programs(self) -> list[Program]:
        return [await self.program(n) for n in range(1, 23)]

    async def set_program(self, number: int, days: list[list[tuple[str, float]]], name: str | None = None) -> Program:
        """Écrit un programme entier (comme l'app), puis relit pour vérifier."""
        if not 1 <= number <= 22:
            raise ValueError("program number must be 1 to 22")
        raw = await self._program_raw(number)
        value = build_program(number, raw[-16:].decode("latin1").strip() if name is None else name, days, raw[85])
        await self._ask(tlv(0x000D, value), lambda d: d[:2] == b"\x80\x0d")
        await asyncio.sleep(1)
        new = await self._program_raw(number)
        if new != value:
            raise ConnectionError("program not confirmed by the read-back")
        return parse_program(new)

    async def restore_program_raw(self, number: int, raw: bytes) -> None:
        """Remet un programme octet pour octet (outil de test)."""
        await self._ask(tlv(0x000D, raw), lambda d: d[:2] == b"\x80\x0d")

    async def modes(self) -> Modes:
        summer = tlv_value(await self._ask(tlv(0xCC52)))
        state = tlv_value(await self._ask(tlv(0x803A)))
        absence_temp = tlv_value(await self._ask(tlv(0xD456)))
        period = tlv_value(await self._ask(tlv(0x800E)))
        return parse_modes(summer, state, absence_temp, period)

    # --- écritures des modes (chacune relue pour vérification) ---

    async def _verify(self, label: str, ok) -> Modes:
        await asyncio.sleep(1)
        m = await self.modes()
        if not ok(m):
            raise ConnectionError(f"{label} not confirmed by the read-back: {m}")
        return m

    async def set_summer(self, on: bool) -> Modes:
        await self._ask(tlv(0x4C52, b"A" if on else b"N"), lambda d: d[:2] == b"\xcc\x52")
        return await self._verify("summer mode", lambda m: m.summer == on)

    async def _mask(self) -> int:
        return state_to_mask(tlv_value(await self._ask(tlv(0x803A))))

    async def _write_mask(self, mask: int) -> None:
        await self._ask(tlv(0x003A, bytes([mask, 3])), lambda d: d[:2] == b"\x80\x3a")

    async def set_holiday(self, on: bool) -> Modes:
        mask = await self._mask()
        await self._write_mask(mask | 0x08 if on else mask & ~0x08)
        return await self._verify("holiday mode", lambda m: m.holiday == on)

    async def set_absence(self, on: bool) -> Modes:
        mask = await self._mask()
        await self._write_mask(mask | 0x01 if on else mask & ~0x01)
        return await self._verify("absence mode", lambda m: m.absence == on)

    async def set_absence_temp(self, temp: float) -> Modes:
        if not MIN_SETPOINT <= temp <= MAX_SETPOINT:
            raise ValueError(f"temperature out of range ({MIN_SETPOINT}-{MAX_SETPOINT} °C)")
        await self._ask(tlv(0x5456, bytes([round(temp * 2)])), lambda d: d[:2] == b"\xd4\x56")
        return await self._verify("absence temperature", lambda m: m.absence_temp == round(temp * 2) / 2)

    async def set_holiday_period(self, start: datetime, end: datetime, temp: float) -> Modes:
        if end <= start:
            raise ValueError("the end must be after the start")
        if not MIN_SETPOINT <= temp <= MAX_SETPOINT:
            raise ValueError(f"temperature out of range ({MIN_SETPOINT}-{MAX_SETPOINT} °C)")
        mask = await self._mask()
        await self._ask(holiday_frame(start, end, temp, mask), lambda d: d[:2] == b"\xff\xff")
        want = (start.strftime("%Y-%m-%d %H:%M"), end.strftime("%Y-%m-%d %H:%M"), round(temp * 2) / 2)
        return await self._verify("holiday period", lambda m: (m.holiday_start, m.holiday_end, m.holiday_temp) == want)

    # --- actualisation radio (consomme la pile des thermostats : jamais en automatique) ---

    async def refresh_room(self, address: int) -> Room:
        key = bytes([ROOM_CODE, 0x15, address, 4])
        ok = lambda d: tlv_value(d)[:3] == key[:3] and len(tlv_value(d)) >= RECORD_LEN
        return parse_room(tlv_value(await self._ask(tlv(0x8050, key), ok)))

    async def refresh_rooms(self, spacing: float = 3.0) -> list[Room]:
        """Actualise chaque pièce joignable, une par une."""
        out = []
        for a in await self.room_addresses():
            if (await self.room(a)).unreachable:
                continue  # inutile de solliciter un thermostat hors réseau
            out.append(await self.refresh_room(a))
            await asyncio.sleep(spacing)
        return out
