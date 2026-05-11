"""Overlay OSD (On-Screen Display) qui se superpose au flux vidéo.

Affiche en surimpression :
- coin haut-gauche : pastille d'état machine (Idle / Run / Hold / Alarm…)
- coin haut-droit  : horodatage local + temps écoulé du job en cours
- coin bas         : positions X / Y / Z / A en grand monospace coloré
- coin milieu-droit : badge fil chaud (ON/OFF + valeur S)

L'overlay est transparent partout sauf sur les zones de texte qui ont
un fond semi-opaque sombre pour rester lisible sur n'importe quelle image.
"""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QSizePolicy,
    QWidget,
)


# Couleurs CNC traditionnelles par axe (cohérent avec la DRO)
AXIS_COLORS_OSD = {
    "X": "#ff5a66",   # rouge clair
    "Y": "#52d97a",   # vert clair
    "Z": "#5fa8ff",   # bleu clair
    "A": "#a585ff",   # violet clair
}

STATE_COLORS_OSD = {
    "Idle":   "#1f9d55",
    "Run":    "#1f6feb",
    "Hold":   "#f59f00",
    "Alarm":  "#d6363d",
    "Jog":    "#7950f2",
    "Door":   "#fab005",
    "Check":  "#fab005",
    "Home":   "#7950f2",
    "Sleep":  "#868e96",
    "Unknown":"#adb5bd",
}

STATE_LABELS_OSD = {
    "Idle": "PRÊT",
    "Run": "EN COURS",
    "Hold": "PAUSE",
    "Alarm": "ALARME",
    "Jog": "JOG",
    "Door": "PORTE",
    "Check": "VÉRIF",
    "Home": "HOMING",
    "Sleep": "VEILLE",
    "Unknown": "—",
}


class WebcamOSD(QWidget):
    """Widget transparent qui s'empile au-dessus du QVideoWidget via
    QStackedLayout(StackAll)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        # IMPORTANT : initialiser l'état AVANT de créer le timer qui pourrait
        # le lire dès le 1er tick.
        self._job_t0: float | None = None

        # Le widget lui-même est transparent ; les labels enfants ont leur
        # propre fond semi-opaque.
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setStyleSheet("background: transparent;")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # ---- Pastille d'état (haut gauche) ----
        self.lbl_state = QLabel("—")
        self._set_state_style("Unknown")
        self.lbl_state.setAlignment(Qt.AlignCenter)
        self.lbl_state.setMinimumWidth(110)

        # ---- Horloge + temps écoulé (haut droit) ----
        self.lbl_clock = QLabel("--:--:--")
        self.lbl_clock.setStyleSheet(self._chip_style("rgba(0,0,0,0.55)", "#ffffff"))
        self.lbl_clock.setAlignment(Qt.AlignCenter)

        self.lbl_elapsed = QLabel("⏱ 00:00:00")
        self.lbl_elapsed.setStyleSheet(self._chip_style("rgba(0,0,0,0.55)", "#ffffff"))
        self.lbl_elapsed.setAlignment(Qt.AlignCenter)

        # ---- Fil chaud (milieu droit) ----
        self.lbl_hotwire = QLabel("FIL OFF")
        self.lbl_hotwire.setStyleSheet(self._chip_style("rgba(0,0,0,0.55)", "#9aa3ad"))
        self.lbl_hotwire.setAlignment(Qt.AlignCenter)
        self.lbl_hotwire.setMinimumWidth(120)

        # ---- 4 axes (bas) ----
        self.lbl_x = self._make_axis_label("X")
        self.lbl_y = self._make_axis_label("Y")
        self.lbl_z = self._make_axis_label("Z")
        self.lbl_a = self._make_axis_label("A")

        # ---- Layout ----
        # Grille 4x3 :
        #   ┌───────────────┬─────────────┬───────────────┐
        #   │ état          │             │ horloge       │
        #   │               │             │ temps écoulé  │
        #   │               │             │               │
        #   │               │             │ fil chaud     │
        #   │               │             │               │
        #   │ X    Y    Z    A   (bas)                    │
        #   └───────────────┴─────────────┴───────────────┘

        g = QGridLayout(self)
        g.setContentsMargins(12, 12, 12, 12)
        g.setSpacing(6)

        # haut gauche
        g.addWidget(self.lbl_state, 0, 0, alignment=Qt.AlignTop | Qt.AlignLeft)
        # haut droit (horloge + écoulé empilés)
        right_top = QGridLayout()
        right_top.addWidget(self.lbl_clock, 0, 0)
        right_top.addWidget(self.lbl_elapsed, 1, 0)
        right_top.setSpacing(4)
        right_top_w = QWidget()
        right_top_w.setLayout(right_top)
        right_top_w.setStyleSheet("background: transparent;")
        right_top_w.setAttribute(Qt.WA_TransparentForMouseEvents)
        g.addWidget(right_top_w, 0, 2, alignment=Qt.AlignTop | Qt.AlignRight)

        # milieu droit : fil chaud
        g.addWidget(self.lbl_hotwire, 1, 2, alignment=Qt.AlignVCenter | Qt.AlignRight)

        # spacer central pour ne rien afficher au milieu
        g.setRowStretch(1, 1)
        g.setColumnStretch(1, 1)

        # bas : 4 axes en ligne
        axes_row = QGridLayout()
        axes_row.setContentsMargins(0, 0, 0, 0)
        axes_row.setSpacing(8)
        axes_row.addWidget(self.lbl_x, 0, 0)
        axes_row.addWidget(self.lbl_y, 0, 1)
        axes_row.addWidget(self.lbl_z, 0, 2)
        axes_row.addWidget(self.lbl_a, 0, 3)
        for c in range(4):
            axes_row.setColumnStretch(c, 1)
        axes_w = QWidget()
        axes_w.setLayout(axes_row)
        axes_w.setStyleSheet("background: transparent;")
        axes_w.setAttribute(Qt.WA_TransparentForMouseEvents)
        g.addWidget(axes_w, 2, 0, 1, 3, alignment=Qt.AlignBottom)

        # Horloge live
        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(1000)
        self._clock_timer.timeout.connect(self._tick_clock)
        self._clock_timer.start()
        self._tick_clock()

    # ---- Helpers de style ----

    def _chip_style(self, bg: str, color: str) -> str:
        return (
            f"background: {bg}; color: {color}; "
            "padding: 6px 12px; border-radius: 6px; "
            "font-family: Consolas, 'Cascadia Mono', monospace; "
            "font-size: 11pt; font-weight: bold; "
            "letter-spacing: 1px;"
        )

    def _make_axis_label(self, axis: str) -> QLabel:
        col = AXIS_COLORS_OSD.get(axis, "#ffffff")
        lbl = QLabel(f"{axis} 0.000")
        lbl.setStyleSheet(
            f"background: rgba(0,0,0,0.6); color: {col}; "
            "padding: 8px 14px; border-radius: 8px; "
            "font-family: Consolas, 'Cascadia Mono', monospace; "
            "font-size: 14pt; font-weight: bold; "
            f"border-left: 4px solid {col};"
        )
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setMinimumWidth(140)
        return lbl

    def _set_state_style(self, state: str) -> None:
        bg = STATE_COLORS_OSD.get(state, STATE_COLORS_OSD["Unknown"])
        self.lbl_state.setStyleSheet(
            f"background: {bg}; color: white; "
            "padding: 8px 18px; border-radius: 8px; "
            "font-weight: bold; font-size: 12pt; "
            "letter-spacing: 1.5px;"
        )

    # ---- Slots publics ----

    @Slot(str)
    def on_state(self, state: str) -> None:
        self.lbl_state.setText(STATE_LABELS_OSD.get(state, state.upper()))
        self._set_state_style(state)
        # Timer du job auto : démarre quand on entre en Run, stop sinon
        if state == "Run":
            if self._job_t0 is None:
                self._job_t0 = time.monotonic()
        elif state in ("Idle", "Alarm", "Unknown"):
            self._job_t0 = None
            self.lbl_elapsed.setText("⏱ 00:00:00")

    @Slot(tuple)
    def on_mpos(self, mpos: tuple) -> None:
        if len(mpos) >= 1:
            self.lbl_x.setText(f"X {mpos[0]:8.3f}")
        if len(mpos) >= 2:
            self.lbl_y.setText(f"Y {mpos[1]:8.3f}")
        if len(mpos) >= 3:
            self.lbl_z.setText(f"Z {mpos[2]:8.3f}")
        if len(mpos) >= 4:
            self.lbl_a.setText(f"A {mpos[3]:8.3f}")

    @Slot(bool, int)
    def on_hotwire(self, on: bool, value: int = 0) -> None:
        if on:
            self.lbl_hotwire.setText(f"🔥 FIL {value}")
            self.lbl_hotwire.setStyleSheet(
                self._chip_style("rgba(214,54,61,0.85)", "#ffffff")
            )
        else:
            self.lbl_hotwire.setText("FIL OFF")
            self.lbl_hotwire.setStyleSheet(
                self._chip_style("rgba(0,0,0,0.55)", "#9aa3ad")
            )

    # ---- Horloge interne ----

    def _tick_clock(self) -> None:
        self.lbl_clock.setText(time.strftime("%H:%M:%S"))
        if self._job_t0 is not None:
            s = int(time.monotonic() - self._job_t0)
            self.lbl_elapsed.setText(
                f"⏱ {s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"
            )
