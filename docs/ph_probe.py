#!/usr/bin/env python3
"""Sonde PocketHome CJ39 en LECTURE SEULE (protocole TLV observé dans pockethome.pcap).
Trame: tag(2) longueur(2) valeur. Réponse: tag|0x8000, longueur|0x4000.
Usage: python3 ph_probe.py --target tcp://IP:4000 [--dry-run] info list elements
"""
import argparse, socket, struct, time

def tlv(tag, val=b""):
    return struct.pack(">HH", tag, len(val)) + val

def ask(host, port, frame, dry):
    print("  ->", frame.hex())
    if dry:
        return b""
    for _ in range(3):  # la CJ39 ignore parfois une requête
        time.sleep(0.3)
        s = socket.create_connection((host, port), 5)
        s.settimeout(3)
        try:
            s.sendall(frame)
            r = s.recv(2048)
            print("  <-", r.hex())
            return r
        except socket.timeout:
            pass
        finally:
            s.close()
    raise SystemExit("pas de réponse")

def value(r):  # réponse mono-TLV -> valeur
    return r[4:4 + (struct.unpack(">H", r[2:4])[0] & 0x3FFF)]

def txt(b):
    return b.decode("latin1").strip()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("cmds", nargs="+", choices=["info", "list", "elements", "refresh", "modes"])
    a = ap.parse_args()
    host, port = a.target.removeprefix("tcp://").rsplit(":", 1)
    port, dry = int(port), a.dry_run
    for c in a.cmds:
        print(c)
        if c == "info":
            for name, tag in (("nom", 0x378C), ("réseau", 0x3716)):
                v = value(ask(host, port, tlv(tag), dry))
                print(f"  {name}: {txt(v)}")
        elif c == "modes":
            v = value(ask(host, port, tlv(0xCC52), dry))
            print(f"  mode été: {'ON' if v == b'A' else 'off'}")
            v = value(ask(host, port, tlv(0x803A), dry))
            print(f"  vacances: octets {v.hex(' ')} (off = 20 23 08 00, on = 00 33 08 00)")
        elif c == "list":
            v = value(ask(host, port, tlv(0x803D, bytes.fromhex("0007")), dry))
            # paires (code élément, adresse): 54 01 | 63 01 | 63 02 ...
            print("  octets:", v.hex(" "))
        elif c in ("elements", "refresh"):
            # mode 00 = lecture, 04 = actualisation forcée (interroge l'élément par radio)
            mode = 0 if c == "elements" else 4
            for addr in range(1, 8):
                v = value(ask(host, port, tlv(0x8050, bytes([0x63, 0x15, addr, mode])), dry))
                if not v:
                    continue
                s1, t, s3 = v[10], v[11], v[12]  # s1 bit0 = sortie active, t = °C, s3 bas = dixièmes
                temp = ((t & 0x7F) + (s3 & 0x0F) / 10) * (-1 if t & 0x80 else 1)
                print(f"  #{addr} {txt(v[17:33])!r}: {temp:.1f} °C sortie={'ON' if s1 & 1 else 'off'} brut={v.hex(' ')}")
            v = value(ask(host, port, tlv(0x8050, bytes([0x54, 0x09, 1, mode])), dry))
            print(f"  PK 1 (sortie chaudière) brut={v.hex(' ')}")

if __name__ == "__main__":
    main()
