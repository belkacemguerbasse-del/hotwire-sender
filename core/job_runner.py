"""Exécution d'un programme G-code via le streamer character-counting.

Le runner pousse les lignes une à une dans la file du `GrblLink` et marque
chaque ligne comme `sent` puis `ok`/`err` à mesure que la file se vide.
"""

from __future__ import annotations

import time
from PySide6.QtCore import QObject, QTimer, Signal, Slot


HW_PAUSE_PREFIX = "; @HW_PAUSE:"


class JobRunner(QObject):
    line_sent = Signal(int)              # zero-based index
    line_acked = Signal(int, bool)       # zero-based index, ok=True
    finished = Signal()
    elapsed_tick = Signal(str)           # HH:MM:SS
    pause_with_message = Signal(str)     # message à afficher à l'utilisateur
    resumed_after_pause = Signal()       # quand l'utilisateur a relancé après une pause logique

    def __init__(self, link, parent: QObject | None = None):
        super().__init__(parent)
        self.link = link
        self._lines: list[str] = []
        self._cursor_send = 0
        self._cursor_ack = 0
        self._running = False
        self._paused = False
        self._t0: float | None = None

        self.link.line_received.connect(self._on_rx)

        self._tick = QTimer(self)
        self._tick.setInterval(500)
        self._tick.timeout.connect(self._on_tick)

    def load(self, lines: list[str]) -> None:
        self._lines = list(lines)
        self._cursor_send = 0
        self._cursor_ack = 0

    def start(self) -> None:
        if self._running and self._paused:
            self._paused = False
            self._pump()
            return
        if not self._lines:
            return
        self._running = True
        self._paused = False
        self._t0 = time.time()
        self._tick.start()
        self._pump()

    def pause(self) -> None:
        """Pause demandée par l'utilisateur ou auto sur erreur : envoie un
        feed hold au firmware en plus de stopper le pump."""
        self._paused = True
        self.link.feed_hold()

    def resume(self) -> None:
        """Reprise après une pause utilisateur (feed hold)."""
        self._paused = False
        self.link.cycle_start()
        self._pump()

    def resume_from_logical_pause(self) -> None:
        """Reprise après une pause logique `; @HW_PAUSE:` (pas de cycle_start
        car le firmware n'a jamais été en feed hold)."""
        self._paused = False
        self.resumed_after_pause.emit()
        self._pump()

    def stop(self) -> None:
        self._running = False
        self._paused = False
        self._tick.stop()
        self.link.soft_reset()
        self._t0 = None

    def is_running(self) -> bool:
        return self._running

    def _pump(self) -> None:
        if not self._running or self._paused:
            return
        while self._cursor_send < len(self._lines):
            ln = self._lines[self._cursor_send]
            stripped = ln.strip()

            # Pause logicielle : on s'arrête, on ack la ligne (pour la barre
            # de progression) et on émet un signal pour que la MainWindow
            # affiche le popup.
            if stripped.startswith(HW_PAUSE_PREFIX):
                msg = stripped[len(HW_PAUSE_PREFIX):].strip()
                idx = self._cursor_send
                self._cursor_send += 1
                self._cursor_ack = max(self._cursor_ack, self._cursor_send)
                self.line_sent.emit(idx)
                self.line_acked.emit(idx, True)
                self._paused = True
                self.pause_with_message.emit(msg)
                return

            if not stripped or stripped.startswith(";"):
                # Lignes vides / commentaires : ack immédiat
                idx = self._cursor_send
                self._cursor_send += 1
                self._cursor_ack = max(self._cursor_ack, self._cursor_send)
                self.line_sent.emit(idx)
                self.line_acked.emit(idx, True)
                continue

            self.link.send_line(stripped)
            self.line_sent.emit(self._cursor_send)
            self._cursor_send += 1
            # Plafonnement pour ne pas bloquer l'UI
            if self._cursor_send % 64 == 0:
                break
        if self._cursor_send >= len(self._lines) and self._cursor_ack >= len(self._lines):
            self._finish()

    @Slot(str)
    def _on_rx(self, line: str) -> None:
        if not self._running:
            return
        if line == "ok" or line.startswith("error:"):
            ok = (line == "ok")
            idx = self._cursor_ack
            if idx < len(self._lines):
                self.line_acked.emit(idx, ok)
            self._cursor_ack += 1
            if self._cursor_ack >= len(self._lines) and self._cursor_send >= len(self._lines):
                self._finish()
            else:
                self._pump()

    def _on_tick(self) -> None:
        if self._t0 is None:
            return
        s = int(time.time() - self._t0)
        self.elapsed_tick.emit(f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}")

    def _finish(self) -> None:
        self._running = False
        self._tick.stop()
        self.finished.emit()
