"""Diagnostic série brut. Bypasse complètement Qt/threads.

Usage:
    python diag_serial.py            (utilise COM4 @ 115200)
    python diag_serial.py COM3 250000

Le script :
1. Liste les ports série visibles.
2. Ouvre celui demandé.
3. Lit tout ce qui arrive pendant 4 secondes (banner attendu).
4. Envoie '?' et lit 1 seconde de plus.
5. Envoie Ctrl-X (soft-reset) et lit 4 secondes de plus.
6. Affiche les octets reçus en hex et en ASCII.
"""

from __future__ import annotations

import sys
import time

import serial
import serial.tools.list_ports


def hexdump(data: bytes) -> str:
    if not data:
        return "(vide)"
    parts = []
    for i in range(0, len(data), 16):
        chunk = data[i : i + 16]
        hexs = " ".join(f"{b:02x}" for b in chunk)
        ascii_ = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        parts.append(f"{i:04x}  {hexs:<48}  {ascii_}")
    return "\n".join(parts)


def list_ports() -> None:
    print("== Ports détectés ==")
    found = list(serial.tools.list_ports.comports())
    if not found:
        print("(aucun)")
    for p in found:
        print(f"  {p.device:8}  {p.description}")
    print()


def read_for(ser: serial.Serial, seconds: float) -> bytes:
    end = time.time() + seconds
    buf = bytearray()
    while time.time() < end:
        n = ser.in_waiting
        if n:
            buf.extend(ser.read(n))
        else:
            time.sleep(0.02)
    return bytes(buf)


def main() -> int:
    port = sys.argv[1] if len(sys.argv) > 1 else "COM4"
    baud = int(sys.argv[2]) if len(sys.argv) > 2 else 115200

    list_ports()
    print(f"== Ouverture {port} @ {baud} ==")
    try:
        ser = serial.Serial(port, baud, timeout=0, write_timeout=1.0)
    except serial.SerialException as e:
        print(f"ERREUR: {e}")
        return 2
    print("Port ouvert. DTR=", ser.dtr, " RTS=", ser.rts)
    print()

    print("== Phase 1 : écoute passive 4s (banner Grbl attendu) ==")
    data = read_for(ser, 4.0)
    print(f"Reçu {len(data)} octets")
    print(hexdump(data))
    print()

    print("== Phase 2 : envoi '?' puis écoute 1.5s ==")
    ser.write(b"\r\n?")
    data = read_for(ser, 1.5)
    print(f"Reçu {len(data)} octets")
    print(hexdump(data))
    print()

    print("== Phase 3 : envoi Ctrl-X (soft-reset) puis écoute 4s ==")
    ser.write(b"\x18")
    data = read_for(ser, 4.0)
    print(f"Reçu {len(data)} octets")
    print(hexdump(data))
    print()

    print("== Phase 4 : envoi '$I\\n' (build info) puis écoute 1.5s ==")
    ser.write(b"$I\n")
    data = read_for(ser, 1.5)
    print(f"Reçu {len(data)} octets")
    print(hexdump(data))
    print()

    ser.close()
    print("Fini.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
