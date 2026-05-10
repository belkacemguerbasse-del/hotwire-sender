"""Simulateur de G-code en temps réel (sans envoyer au firmware).

Lit un programme G-code, calcule la durée estimée de chaque mouvement
(distance / feed rate), et fait avancer un curseur virtuel à la vitesse
configurée. Émet `position_updated((X, Y, Z, A))` à ~30 Hz pour qu'une
vue 3D puisse animer le fil.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from PySide6.QtCore import QObject, QTimer, Signal


# Feed rate par défaut pour les G0 quand le firmware n'a pas de F dispo
DEFAULT_RAPID_MM_MIN = 1500.0
# Si une ligne G1 n'a pas encore vu de F, on assume cette valeur
DEFAULT_FEED_MM_MIN = 200.0


@dataclass
class _SimSegment:
    line_no: int
    start: tuple[float, float, float, float]   # (X, Y, Z, A)
    end: tuple[float, float, float, float]
    duration_s: float
    rapid: bool


class GcodeSimulator(QObject):
    position_updated = Signal(tuple)        # (X, Y, Z, A)
    progress_changed = Signal(float)        # 0..100
    elapsed_changed = Signal(float, float)  # elapsed_s, total_s
    state_changed = Signal(str)             # 'idle' | 'playing' | 'paused' | 'finished'
    line_index_changed = Signal(int)        # numéro de ligne courant (1-based)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._segments: list[_SimSegment] = []
        self._total_s = 0.0
        self._sim_time = 0.0     # temps simulé écoulé
        self._wall_last = 0.0    # dernier tick wall-clock (secondes)
        self._speed = 5.0
        self._state = "idle"

        self._timer = QTimer(self)
        self._timer.setInterval(33)   # ~30 fps
        self._timer.timeout.connect(self._tick)

    # ---------- API publique ----------

    def load(self, lines: list[str], rapid_mm_min: float = DEFAULT_RAPID_MM_MIN) -> None:
        """Parse le G-code et précompute les segments avec leur durée."""
        from gcode.parser import parse_program

        self.stop()
        result = parse_program("\n".join(lines))
        moves = result.moves

        self._segments.clear()
        self._total_s = 0.0
        if not moves:
            self.state_changed.emit("idle")
            self.elapsed_changed.emit(0.0, 0.0)
            self.progress_changed.emit(0.0)
            return

        # Position de départ : on suppose (0, 0, 0, 0). Pour être plus juste
        # on prendrait la position courante du firmware mais en simulation
        # c'est OK.
        prev = (0.0, 0.0, 0.0, 0.0)
        for m in moves:
            end = (m.pos["X"], m.pos["Y"], m.pos["Z"], m.pos["A"])
            dist = _dist4(prev, end)
            if m.rapid:
                feed = rapid_mm_min
            else:
                feed = m.feed if m.feed > 0 else DEFAULT_FEED_MM_MIN
            # feed en mm/min → durée en s = dist / (feed/60)
            duration = dist / (feed / 60.0) if feed > 0 else 0.0
            self._segments.append(_SimSegment(
                line_no=m.line_no, start=prev, end=end,
                duration_s=duration, rapid=m.rapid,
            ))
            self._total_s += duration
            prev = end

        self._sim_time = 0.0
        self.elapsed_changed.emit(0.0, self._total_s)
        self.progress_changed.emit(0.0)
        self.position_updated.emit(self._segments[0].start)
        self._set_state("idle")

    def play(self) -> None:
        if not self._segments:
            return
        if self._state == "finished":
            self._sim_time = 0.0
        self._wall_last = time.monotonic()
        self._timer.start()
        self._set_state("playing")

    def pause(self) -> None:
        self._timer.stop()
        if self._state == "playing":
            self._set_state("paused")

    def stop(self) -> None:
        self._timer.stop()
        self._sim_time = 0.0
        if self._segments:
            self.position_updated.emit(self._segments[0].start)
        self.elapsed_changed.emit(0.0, self._total_s)
        self.progress_changed.emit(0.0)
        self.line_index_changed.emit(0)
        self._set_state("idle")

    def set_speed(self, speed: float) -> None:
        self._speed = max(0.1, float(speed))
        # Reset wall_last pour ne pas avaler de temps lors du changement
        self._wall_last = time.monotonic()

    def is_playing(self) -> bool:
        return self._state == "playing"

    @property
    def total_s(self) -> float:
        return self._total_s

    # ---------- Boucle ----------

    def _tick(self) -> None:
        if not self._segments:
            return
        now = time.monotonic()
        wall_dt = now - self._wall_last
        self._wall_last = now
        self._sim_time += wall_dt * self._speed

        if self._sim_time >= self._total_s:
            self._sim_time = self._total_s
            self.position_updated.emit(self._segments[-1].end)
            self.line_index_changed.emit(self._segments[-1].line_no)
            self.elapsed_changed.emit(self._sim_time, self._total_s)
            self.progress_changed.emit(100.0)
            self._timer.stop()
            self._set_state("finished")
            return

        # Trouve le segment courant (linéaire — on pourrait binary search
        # mais pour des programmes < 10000 segments c'est rapide).
        acc = 0.0
        cur_seg: _SimSegment | None = None
        local_t = 0.0
        for seg in self._segments:
            if acc + seg.duration_s >= self._sim_time:
                cur_seg = seg
                local_t = (self._sim_time - acc) / seg.duration_s if seg.duration_s > 0 else 1.0
                break
            acc += seg.duration_s
        if cur_seg is None:
            return

        pos = _lerp4(cur_seg.start, cur_seg.end, local_t)
        self.position_updated.emit(pos)
        self.line_index_changed.emit(cur_seg.line_no)
        self.elapsed_changed.emit(self._sim_time, self._total_s)
        self.progress_changed.emit(100.0 * self._sim_time / self._total_s)

    def _set_state(self, s: str) -> None:
        if s != self._state:
            self._state = s
            self.state_changed.emit(s)


def _dist4(a: tuple, b: tuple) -> float:
    return math.sqrt(sum((b[i] - a[i]) ** 2 for i in range(4)))


def _lerp4(a: tuple, b: tuple, t: float) -> tuple[float, float, float, float]:
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(4))
