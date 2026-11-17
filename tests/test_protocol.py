"""Tests du décodage, sur des trames réelles capturées le 17 nov. 2026. Lancer : python3 -m unittest discover tests"""
import asyncio  # noqa: F401  (stdlib avant sys.path : select.py/datetime.py du paquet les masquent)
import pathlib
import sys
import unittest
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "custom_components" / "pockethome"))
import protocol as p  # noqa: E402

# Fiches 8050 (valeur de 37 octets) lues sur la centrale
CUISINE = bytes.fromhex("63150102092c000000000016800026000043756973696e65202020202020202020018a6a51")
PETITE_CHAMBRE = bytes.fromhex("6315030429240000400080000004260000506574697465206368616d6272652020038a6345")
DISQUE = bytes.fromhex("63150402092c0000000012160100 2e000044697371756520202020202020202020048a5f3b".replace(" ", ""))


class Rooms(unittest.TestCase):
    def test_cuisine(self):
        r = p.parse_room(CUISINE)
        self.assertEqual((r.address, r.name, r.program), (1, "Cuisine", 2))
        self.assertEqual((r.temperature, r.setpoint), (22.0, 22.0))
        self.assertTrue(r.auto and r.battery_low)
        self.assertFalse(r.off or r.output_on or r.unreachable)
        self.assertEqual(r.link, 0x51)

    def test_hors_reseau(self):
        r = p.parse_room(PETITE_CHAMBRE)
        self.assertTrue(r.unreachable)
        self.assertIsNone(r.temperature)
        self.assertEqual((r.name, r.program), ("Petite chambre", 4))

    def test_dixiemes_et_sortie(self):
        r = p.parse_room(DISQUE)
        self.assertEqual(r.temperature, 22.1)
        v = bytearray(CUISINE)
        v[10] |= 1  # sortie active
        v[4] |= 4  # pièce éteinte
        r = p.parse_room(bytes(v))
        self.assertTrue(r.output_on and r.off)
        self.assertIsNone(r.setpoint)

    def test_rejette_autre_element(self):
        with self.assertRaises(ValueError):
            p.parse_room(bytes([0x54]) + CUISINE[1:])


class Ecriture(unittest.TestCase):
    """Trames d'écriture capturées sur le WC (capture 9)."""

    @staticmethod
    def wc():
        v = bytearray(37)
        v[0:5] = bytes([0x63, 0x15, 6, 1, 0x09])  # programme 1, auto
        v[14] = 0x26
        v[17:33] = b"WC".ljust(16)
        v[33] = 5
        return bytes(v)

    def test_trames_de_l_app(self):
        off = "631506010102260000020000" + "5743" + "20" * 14 + "0526"
        on = "631506010102260000000000" + "5743" + "20" * 14 + "0526"
        prog2 = "63150601020 22c0000000000".replace(" ", "") + "5743" + "20" * 14 + "0526"
        self.assertEqual(p.build_write(self.wc(), setpoint=19, auto=True, off=True).hex(), off)
        self.assertEqual(p.build_write(self.wc(), setpoint=19, auto=True, off=False).hex(), on)
        v = bytearray(self.wc())
        v[3] = 2
        self.assertEqual(p.build_write(bytes(v), setpoint=22, auto=True, off=False).hex(), prog2)
        manu = p.build_write(self.wc(), setpoint=19, auto=False, off=False)
        self.assertEqual(manu[5], 0x00)  # mode manu = 00

    def test_demi_degres(self):
        self.assertEqual(p.build_write(self.wc(), setpoint=22.5, auto=True, off=False)[6], 45)


class EcritureModes(unittest.TestCase):
    def test_masque_depuis_etat(self):  # (état lu) -> masque que l'app avait écrit
        for etat, mask in (("00330800", 0x08), ("20230800", 0x04), ("20330800", 0x0C), ("21230800", 0x05), ("00230800", 0x00)):
            self.assertEqual(p.state_to_mask(bytes.fromhex(etat)), mask, etat)

    def test_trame_vacances_de_l_app(self):
        f = p.holiday_frame(datetime(2026, 11, 19, 10), datetime(2026, 12, 19, 12), 7.0, 0x0C)
        self.assertEqual(f.hex(), "7fff0015000e000b1a0b130a001a0c130c000e003a00020c03")  # capture 6
        f = p.holiday_frame(datetime(2026, 11, 17, 8), datetime(2026, 11, 19, 12), 15.0, 0x00)
        self.assertEqual(f.hex(), "7fff0015000e000b1a0b11080" + "01a0b130c001e003a00020003")  # capture 6, 1er enregistrement


class Programmes(unittest.TestCase):
    def test_heures(self):  # saisies de l'utilisateur dans l'app
        for hhmm, b in (("06:30", 0x33), ("07:10", 0x39), ("08:00", 0x40), ("09:00", 0x48), ("23:50", 0xBD)):
            self.assertEqual(p.encode_start(hhmm), b)
            self.assertEqual(p.decode_start(b), hhmm)

    def test_aller_retour_programme_test_ha(self):
        days = [[("00:00", 17.0), ("06:30", 21.0), ("08:00", 17.0)], [("00:00", 18.0), ("07:10", 24.0), ("09:00", 17.0)]] + [[("00:00", 19.0)]] * 5
        v = p.build_program(10, "Test HA", days)
        self.assertEqual(len(v), 102)
        self.assertEqual(v[1:13].hex(), "0022332a4022bd22bd22bd22")  # plages inutilisées : 23:50 avec la dernière température
        prog = p.parse_program(v)
        self.assertEqual(prog.days[0], days[0])
        self.assertEqual(prog.days[1], days[1])
        self.assertEqual(prog.name, "Test HA")

    def test_validation(self):
        ok = [[("00:00", 19.0)]] * 7
        for bad in (ok[:6], [[]] + ok[1:], [[("00:05", 19.0)]] + ok[1:], [[("08:00", 19.0), ("07:00", 20.0)]] + ok[1:],
                    [[("00:00", 19.3)]] + ok[1:], [[("00:00", 40.0)]] + ok[1:], [[(f"0{i}:00", 19.0) for i in range(7)]] + ok[1:]):
            with self.assertRaises(ValueError):
                p.build_program(1, "x", bad)


class Programs(unittest.TestCase):
    def test_programme_test_ha(self):
        lundi = bytes.fromhex("0022 332a 4022 bd0a bd0a bd0a".replace(" ", ""))
        mardi = bytes.fromhex("0024 3930 4822 bd0a bd0a bd0a".replace(" ", ""))
        v = bytes([10]) + lundi + mardi + b"\xbd\x26" * 30 + b"\x00" + b"Test HA".ljust(16)
        prog = p.parse_program(v)
        self.assertEqual(prog.name, "Test HA")
        # saisi dans l'app : 0h 17°, 6h30 21°, 8h 17° / 0h 18°, 7h10 24°, 9h 17°
        self.assertEqual(prog.days[0], [("00:00", 17.0), ("06:30", 21.0), ("08:00", 17.0)])
        self.assertEqual(prog.days[1], [("00:00", 18.0), ("07:10", 24.0), ("09:00", 17.0)])
        self.assertEqual(prog.days[2], [])


class Modes(unittest.TestCase):
    def test_modes(self):
        period = bytes.fromhex("1a0b130a001a0c130c000e")
        m = p.parse_modes(b"N", bytes.fromhex("21230800"), b"\x24", period)
        self.assertTrue(m.absence and not m.summer and not m.holiday)
        self.assertEqual(m.absence_temp, 18.0)
        self.assertEqual((m.holiday_start, m.holiday_end, m.holiday_temp), ("2026-11-19 10:00", "2026-12-19 12:00", 7.0))
        self.assertTrue(p.parse_modes(b"A", bytes.fromhex("00330800"), b"\x14", period).holiday)


class Trames(unittest.TestCase):
    def test_tlv(self):
        self.assertEqual(p.tlv(0x8050, bytes.fromhex("63150100")).hex(), "8050000463150100")
        self.assertEqual(p.tlv_value(bytes.fromhex("b78c400d5048574946495f303030343831")), b"PHWIFI_000481")


if __name__ == "__main__":
    unittest.main()


class WriteProgramTest(unittest.TestCase):
    def test_program_replaced_only_when_given(self):
        v = bytes(37)
        v = v[:2] + bytes([3, 2]) + v[4:]  # adresse 3, programme 2
        same = p.build_write(v, setpoint=22, auto=True, off=False)
        other = p.build_write(v, setpoint=22, auto=True, off=False, program=10)
        self.assertEqual(same[4], 2)
        self.assertEqual(other[4], 10)
        self.assertEqual(same[:4] + same[5:], other[:4] + other[5:])


class FactoryProgramTest(unittest.TestCase):
    def test_repeated_starts_are_unused_slots(self):
        raw = bytes([1]) + bytes.fromhex("0026" * 6) + bytes.fromhex("0026" + "a826" * 5) + bytes.fromhex("a826" * 6) * 5 + bytes(16)
        raw = raw[:86] + bytes([0]) + raw[86:]  # drapeau
        raw = raw[:85] + raw[85:86] + b"19".ljust(16, b" ")
        raw = raw.ljust(102, b" ")
        prog = p.parse_program(raw)
        self.assertEqual(prog.days[0], [("00:00", 19.0)])
        self.assertEqual(prog.days[1], [("00:00", 19.0), ("21:00", 19.0)])
        self.assertEqual(prog.days[3], [("21:00", 19.0)])
