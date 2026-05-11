"""DRO 4 axes : afficheurs MPos avec WPos en sous-titre.

Layout 2x2 (comme l'app d'origine) :
- haut-gauche : X         haut-droite : A
- bas-gauche  : Y         bas-droite  : Z

Visuel :
- Code couleur CNC traditionnel par axe : X=rouge, Y=vert, Z=bleu, A=violet
- Lettre d'axe ENORME et colorée à gauche
- Valeur MPos en gros monospace à droite
- Liseré coloré sur le bord gauche pour rappel rapide
- Pulse coloré quand la valeur change (la lettre s'illumine)
- WPos en petit dessous, discret
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


# Couleurs CNC traditionnelles par axe (R V B + violet pour A)
AXIS_COLORS = {
    "X": "#e63946",   # rouge
    "Y": "#2a9d4a",   # vert
    "Z": "#1f6feb",   # bleu
    "A": "#7950f2",   # violet
}
AXIS_BG_TINTS = {
    "X": "#fdedee",
    "Y": "#e8f5ec",
    "Z": "#eaf2ff",
    "A": "#f1ebff",
}


class DroCell(QFrame):
    """Une cellule DRO pour un axe."""

    def __init__(self, axis_letter: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.axis_letter = axis_letter
        self.setObjectName("droCell")
        self.setMinimumHeight(96)

        color = AXIS_COLORS.get(axis_letter, COLORS["primary"])
        bg_tint = AXIS_BG_TINTS.get(axis_letter, COLORS["surface_alt"])
        self._color = color
        self._tint = bg_tint

        # Style : fond teinté, gros liseré gauche coloré arrondi
        self.setStyleSheet(f"""
            QFrame#droCell {{
                background-color: {bg_tint};
                border: none;
                border-left: 6px solid {color};
                border-radius: 8px;
            }}
        """)

        # Lettre d'axe ENORME à gauche, colorée
        self.lbl_axis = QLabel(axis_letter)
        self.lbl_axis.setFont(ui_font(38, bold=True))
        self.lbl_axis.setAlignment(Qt.AlignCenter)
        self.lbl_axis.setFixedWidth(64)
        self._set_axis_idle_style()

        # MPos : caption + valeur principale en GROS
        self.lbl_caption = QLabel("MPos")
        self.lbl_caption.setStyleSheet(
            f"color: {COLORS['text_subtle']}; background: transparent; "
            "letter-spacing: 1.5px; font-size: 8pt; font-weight: 600;"
        )

        self.lbl_main = QLabel("0.000")
        self.lbl_main.setFont(mono_font(30, bold=True))
        self.lbl_main.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_main.setStyleSheet(
            f"color: {COLORS['text']}; background: transparent;"
        )

        # WPos : caption + valeur secondaire en petit
        self.lbl_caption_sub = QLabel("WPos")
        self.lbl_caption_sub.setStyleSheet(
            f"color: {COLORS['text_subtle']}; background: transparent; "
            "letter-spacing: 1.5px; font-size: 8pt; font-weight: 600;"
        )

        self.lbl_sub = QLabel("0.000")
        self.lbl_sub.setFont(mono_font(13, bold=False))
        self.lbl_sub.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_sub.setStyleSheet(
            f"color: {COLORS['text_muted']}; background: transparent;"
        )

        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(8)
        row1.addWidget(self.lbl_caption)
        row1.addStretch(1)
        row1.addWidget(self.lbl_main)

        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(8)
        row2.addWidget(self.lbl_caption_sub)
        row2.addStretch(1)
        row2.addWidget(self.lbl_sub)

        right = QVBoxLayout()
        right.setContentsMargins(0, 6, 0, 6)
        right.setSpacing(2)
        right.addStretch(1)
        right.addLayout(row1)
        right.addLayout(row2)
        right.addStretch(1)

        h = QHBoxLayout(self)
        h.setContentsMargins(8, 4, 14, 4)
        h.setSpacing(8)
        h.addWidget(self.lbl_axis)
        h.addLayout(right, 1)

        self._pulse_timer = QTimer(self)
        self._pulse_timer.setSingleShot(True)
        self._pulse_timer.setInterval(200)
        self._pulse_timer.timeout.connect(self._set_axis_idle_style)

    def _set_axis_idle_style(self) -> None:
        self.lbl_axis.setStyleSheet(
            f"color: {self._color}; background: transparent; padding-right: 6px;"
        )

    def _set_axis_active_style(self) -> None:
        self.lbl_axis.setStyleSheet(
            f"color: white; background: {self._color}; padding: 4px 10px; "
            f"border-radius: 8px;"
        )

    def set_main(self, mpos: float) -> None:
        new_text = f"{mpos:.3f}"
        if new_text != self.lbl_main.text():
            self.lbl_main.setText(new_text)
            self._set_axis_active_style()
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
        g.setSpacing(10)
        g.setContentsMargins(8, 12, 8, 8)
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
