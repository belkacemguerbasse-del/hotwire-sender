"""Lien Grbl: port série, parser de status, streamer character-counting.

Le streamer character-counting suit la méthode officielle Grbl: on garde la
somme des longueurs des lignes envoyées mais non encore acquittées par un
`ok` ou `error:`, et on n'envoie la prochaine ligne que si elle tient dans
le buffer RX du firmware (128 octets par défaut).
"""

from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal
import serial
import serial.tools.list_ports

from .grbl_protocol import (
    CMD_CYCLE_START,
    CMD_FEED_HOLD,
    CMD_RESET,
    CMD_STATUS_REPORT,
    GRBL_RX_BUFFER_SIZE,
)

STATUS_RE = re.compile(r"<([^>]+)>")
ALARM_RE = re.compile(r"^ALARM:(\d+)", re.IGNORECASE)
ERROR_RE = re.compile(r"^error:(\d+)", re.IGNORECASE)


@dataclass
class GrblStatus:
    state: str = "Unknown"
    mpos: tuple[float, ...] = field(default_factory=tuple)
    wpos: tuple[float, ...] = field(default_factory=tuple)
    wco: tuple[float, ...] = field(default_factory=tuple)
    feed: float = 0.0
    spindle: float = 0.0
    planner_buf: int = 0
    rx_buf: int = 0
    pins: str = ""
    overrides: tuple[int, int, int] = (100, 100, 100)
    accessory: str = ""
    line: int = 0
    raw: str = ""

    def axis_count(self) -> int:
        return len(self.mpos)


def _parse_floats(s: str) -> tuple[float, ...]:
    out: list[float] = []
    for token in s.split(","):
        try:
            out.append(float(token))
        except ValueError:
            pass
    return tuple(out)


def parse_status_line(line: str) -> Optional[GrblStatus]:
    m = STATUS_RE.search(line)
    if not m:
        return None
    body = m.group(1)
    parts = body.split("|")
    st = GrblStatus(raw=line, state=parts[0])
    for p in parts[1:]:
        if ":" not in p:
            continue
        key, _, value = p.partition(":")
        key = key.strip()
        if key == "MPos":
            st.mpos = _parse_floats(value)
        elif key == "WPos":
            st.wpos = _parse_floats(value)
        elif key == "WCO":
            st.wco = _parse_floats(value)
        elif key == "FS":
            vals = _parse_floats(value)
            if len(vals) >= 1:
                st.feed = vals[0]
            if len(vals) >= 2:
                st.spindle = vals[1]
        elif key == "F":
            vals = _parse_floats(value)
            if vals:
                st.feed = vals[0]
        elif key == "Bf":
            try:
                pl, rx = value.split(",")
                st.planner_buf = int(pl)
                st.rx_buf = int(rx)
            except ValueError:
                pass
        elif key == "Pn":
            st.pins = value
        elif key == "Ov":
            try:
                vals = [int(x) for x in value.split(",")]
                if len(vals) == 3:
                    st.overrides = (vals[0], vals[1], vals[2])
            except ValueError:
                pass
        elif key == "A":
            st.accessory = value
        elif key == "Ln":
            try:
                st.line = int(value)
            except ValueError:
                pass

    # WPos = MPos - WCO if not directly provided.
    if not st.wpos and st.mpos and st.wco and len(st.mpos) == len(st.wco):
        st.wpos = tuple(m - w for m, w in zip(st.mpos, st.wco))
    return st


def list_serial_ports() -> list[tuple[str, str]]:
    return [(p.device, p.description) for p in serial.tools.list_ports.comports()]


class GrblLink(QObject):
    """Lien série Grbl mono-thread.

    Tout tourne sur la boucle Qt principale via deux QTimers :
    - lecture toutes les 15 ms (équivalent ~66 Hz, plus que suffisant)
    - polling status `?` à `status_period_ms`
    - kick périodique tant qu'aucune réponse n'a été reçue
    """

    line_received = Signal(str)
    status_received = Signal(GrblStatus)
    connected = Signal(str)
    disconnected = Signal()
    error_text = Signal(str)
    sent = Signal(str)

    def __init__(self, status_period_ms: int = 200, boot_delay_s: float = 3.0) -> None:
        super().__init__()
        self._ser: Optional[serial.Serial] = None
        self._buffer = bytearray()
        self._pending: deque[int] = deque()
        self._queue: deque[str] = deque()
        self._port = ""
        self._baud = 115200
        self._is_open = False
        self._got_banner = False
        self._kick_attempts = 0
        self._rx_buffer_size = GRBL_RX_BUFFER_SIZE
        self._boot_delay_ms = int(max(500, boot_delay_s * 1000))

        self._read_timer = QTimer(self)
        self._read_timer.setInterval(15)
        self._read_timer.timeout.connect(self._poll)

        self._kick_timer = QTimer(self)
        self._kick_timer.setInterval(500)
        self._kick_timer.timeout.connect(self._kick)

        self._status_timer = QTimer(self)
        self._status_timer.setInterval(status_period_ms)
        self._status_timer.timeout.connect(self._tick_status)

    def set_status_period_ms(self, ms: int) -> None:
        self._status_timer.setInterval(max(50, int(ms)))

    def set_boot_delay_s(self, seconds: float) -> None:
        self._boot_delay_ms = int(max(500, seconds * 1000))

    # ---------- API publique ----------

    def is_open(self) -> bool:
        return self._is_open

    def open(self, port: str, baud: int = 115200) -> None:
        self.close()
        try:
            self._ser = serial.Serial(port, baud, timeout=0, write_timeout=1.0)
            self._port = port
            self._baud = baud
        except serial.SerialException as e:
            self.error_text.emit(f"Ouverture {port} échouée: {e}")
            self._ser = None
            return

        self._buffer.clear()
        self._pending.clear()
        self._queue.clear()
        self._got_banner = False
        self._kick_attempts = 0
        self._is_open = True

        # IMPORTANT : ne RIEN envoyer pendant les 3 premières secondes.
        # Sur Arduino Mega, l'ouverture pulse DTR -> reset puis bootloader
        # stk500v2 tourne ~2 s en attente d'upload. Toute donnée reçue
        # repousse son timeout et l'empêche de céder la main à Grbl.
        # On lit en silence ; le banner Grbl arrivera tout seul après ~2 s.
        self._read_timer.start()
        QTimer.singleShot(self._boot_delay_ms, self._start_kicks_if_silent)
        # Le polling de statut ne commence qu'après détection du banner.

        self.connected.emit(port)

    def _start_kicks_if_silent(self) -> None:
        """Appelé 3 s après l'ouverture. Si Grbl s'est manifesté tout seul,
        on n'a rien à faire. Sinon, on commence à envoyer des '?' poliment."""
        if not self._is_open or self._got_banner:
            return
        self._kick_timer.start()

    def close(self) -> None:
        was_open = self._is_open
        self._is_open = False
        self._read_timer.stop()
        self._kick_timer.stop()
        self._status_timer.stop()
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None
        if was_open:
            self.disconnected.emit()

    def send_line(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        self._queue.append(line)
        self._try_send()

    def send_realtime(self, data: bytes) -> None:
        if self._ser is None:
            return
        try:
            self._ser.write(data)
        except serial.SerialException as e:
            self.error_text.emit(f"Écriture realtime échouée: {e}")

    def reset_streamer(self) -> None:
        self._queue.clear()
        self._pending.clear()
        if self._ser is not None:
            try:
                self._ser.reset_input_buffer()
            except Exception:
                pass
        self._buffer.clear()

    def stop_streaming(self) -> None:
        """Vide UNIQUEMENT la file d'envoi vers le firmware sans toucher
        au port. Utilisé en cas de cascade d'erreurs (firmware en Alarm) :
        on arrête immédiatement de pousser des lignes qui seraient toutes
        rejetées, mais on continue à recevoir les status reports."""
        self._queue.clear()
        self._pending.clear()

    def soft_reset(self) -> None:
        self.send_realtime(CMD_RESET)
        self.reset_streamer()

    def feed_hold(self) -> None:
        self.send_realtime(CMD_FEED_HOLD)

    def cycle_start(self) -> None:
        self.send_realtime(CMD_CYCLE_START)

    def request_status(self) -> None:
        self.send_realtime(CMD_STATUS_REPORT)

    def shutdown(self) -> None:
        self.close()

    # ---------- Boucle interne ----------

    def _tick_status(self) -> None:
        if self._is_open:
            self.send_realtime(CMD_STATUS_REPORT)

    def _kick(self) -> None:
        if self._ser is None or self._got_banner:
            self._kick_timer.stop()
            return
        self._kick_attempts += 1
        if self._kick_attempts == 1:
            self._safe_write(b"\r\n?")
            return
        if self._kick_attempts == 6:
            self.error_text.emit("Pas de réponse après 3 s — tentative de soft-reset (Ctrl-X).")
            self._safe_write(b"\x18")
            return
        if self._kick_attempts >= 12:
            self.error_text.emit(
                "Aucune réponse après 6 s. Vérifie : (1) le port n'est pas ouvert "
                "par un autre logiciel, (2) le baud est bon, (3) le câble fonctionne."
            )
            self._kick_timer.stop()
            return
        self._safe_write(b"?")

    def _safe_write(self, data: bytes) -> None:
        if self._ser is None:
            return
        try:
            self._ser.write(data)
        except serial.SerialException as e:
            self.error_text.emit(f"Écriture échouée: {e}")

    def _poll(self) -> None:
        if self._ser is None or not self._is_open:
            return
        try:
            n = self._ser.in_waiting
            data = self._ser.read(n) if n else b""
        except (serial.SerialException, OSError) as e:
            self.error_text.emit(f"Lecture échouée: {e}")
            self.close()
            return
        if data:
            self._buffer.extend(data)
            while True:
                idx = self._buffer.find(b"\n")
                if idx < 0:
                    break
                raw = bytes(self._buffer[:idx]).decode("ascii", errors="replace").strip()
                del self._buffer[: idx + 1]
                if raw:
                    self._handle_line(raw)
        self._try_send()

    def _handle_line(self, line: str) -> None:
        if not self._got_banner:
            self._got_banner = True
            self._kick_timer.stop()
            # Maintenant Grbl est vivant : on lance le polling de statut.
            if not self._status_timer.isActive():
                self._status_timer.start()
        if line.startswith("<") and line.endswith(">"):
            st = parse_status_line(line)
            if st is not None:
                self.status_received.emit(st)
            self.line_received.emit(line)
            return
        if line.startswith("[OPT:"):
            inner = line[len("[OPT:"):].rstrip("]")
            parts = inner.split(",")
            if len(parts) >= 3:
                try:
                    self._rx_buffer_size = int(parts[2])
                except ValueError:
                    pass
            self.line_received.emit(line)
            return
        if line == "ok" or line.startswith("error:"):
            if self._pending:
                self._pending.popleft()
            self.line_received.emit(line)
            self._try_send()
            return
        self.line_received.emit(line)

    def _try_send(self) -> None:
        if self._ser is None or not self._is_open:
            return
        while self._queue:
            nxt = self._queue[0] + "\n"
            used = sum(self._pending)
            if used + len(nxt) > self._rx_buffer_size:
                return
            try:
                self._ser.write(nxt.encode("ascii", errors="ignore"))
            except serial.SerialException as e:
                self.error_text.emit(f"Écriture échouée: {e}")
                return
            self._pending.append(len(nxt))
            self._queue.popleft()
            self.sent.emit(nxt.rstrip())
