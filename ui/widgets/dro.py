"""DRO 4 axes : afficheurs MPos avec WPos en sous-titre.

Layout 2x2, comme l'app d'origine :
- haut-gauche : X         haut-droite : A
- bas-gauche  : Y         bas-droite  : Z

Visuel modernisé : grosse valeur monospace, étiquette d'axe colorée, sous-titre
WPos discret. Pulse subtil quand la valeur change pour donner du feedback.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ui.theme import COLORS, mono_font, ui_font


class DroCell(QFrame):
    def __init__(self, axis_letter: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("droCell")
        self.setProperty("active", False)
        self.setMinimumHeight(72)

        self.lbl_axis = QLabel(axis_letter)
        self.lbl_axis.setObjectName("droAxis")
        f = ui_font(20, bold=True)
        self.lbl_axis.setFont(f)
        self.lbl_axis.setAlignment(Qt.AlignCenter)
        self.lbl_axis.setFixedWidth(36)

        self.lbl_main = QLabel("0.000")
        self.lbl_main.setObjectName("droValue")
        self.lbl_main.setFont(mono_font(22, bold=True))
        self.lbl_main.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.lbl_caption = QLabel("MPos")
        self.lbl_caption.setStyleSheet(f"color: {COLORS['text_subtle']}; letter-spacing: 1px;")
        self.lbl_caption.setFont(ui_font(7))

        self.lbl_sub = QLabel("0.000")
        self.lbl_sub.setObjectName("droSub")
        self.lbl_sub.setFont(mono_font(10))
        self.lbl_sub.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.lbl_caption_sub = QLabel("WPos")
        self.lbl_caption_sub.setStyleSheet(f"color: {COLORS['text_subtle']}; letter-spacing: 1px;")
        self.lbl_caption_sub.setFont(ui_font(7))

        # ligne 1 : caption MPos + valeur
        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(8)
        row1.addWidget(self.lbl_caption)
        row1.addStretch(1)
        row1.addWidget(self.lbl_main)
        # ligne 2 : caption WPos + sous-valeur
        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(8)
        row2.addWidget(self.lbl_caption_sub)
        row2.addStretch(1)
        row2.addWidget(self.lbl_sub)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        right.addLayout(row1)
        right.addLayout(row2)

        h = QHBoxLayout(self)
        h.setContentsMargins(10, 6, 12, 6)
        h.setSpacing(10)
        h.addWidget(self.lbl_axis)
        h.addLayout(right, 1)

        self._pulse_timer = QTimer(self)
        self._pulse_timer.setSingleShot(True)
        self._pulse_timer.setInterval(140)
        self._pulse_timer.timeout.connect(self._pulse_off)

    def _pulse_off(self) -> None:
        self.setProperty("active", False)
        self._refresh_style()

    def _refresh_style(self) -> None:
        # Force le re-style après changement de propriété.
        self.style().unpolish(self)
        self.style().polish(self)

    def set_main(self, mpos: float) -> None:
        new_text = f"{mpos:.3f}"
        if new_text != self.lbl_main.text():
            self.lbl_main.setText(new_text)
            self.setProperty("active", True)
            self._refresh_style()
            self._pulse_timer.start()

    def set_sub(self, wpos: float) -> None:
        self.lbl_sub.setText(f"{wpos:.3f}")


class Dro(QGroupBox):
    """Layout 2x2 : (X, A) / (Y, Z)."""

    LAYOUT = [("X", 0), ("A", 3), ("Y", 1), ("Z", 2)]

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Position", parent)
        self.cells: dict[int, DroCell] = {}

        g = QGridLayout(self)
        g.setSpacing(8)
        for r, c, (letter, idx) in (
            (0, 0, self.LAYOUT[0]),
            (0, 1, self.LAYOUT[1]),
            (1, 0, self.LAYOUT[2]),
            (1, 1, self.LAYOUT[3]),
        ):
            cell = DroCell(letter)
            self.cells[idx] = cell
            g.addWidget(cell, r, c)

    @Slot(tuple)
    def set_mpos(self, mpos: tuple[float, ...]) -> None:
        for idx, cell in self.cells.items():
            v = mpos[idx] if idx < len(mpos) else 0.0
            cell.set_main(v)

    @Slot(tuple)
    def set_wpos(self, wpos: tuple[float, ...]) -> None:
        for idx, cell in self.cells.items():
            v = wpos[idx] if idx < len(wpos) else 0.0
            cell.set_sub(v)
