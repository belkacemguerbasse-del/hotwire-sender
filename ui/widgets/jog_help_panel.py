"""Aide-mémoire des raccourcis clavier de jog."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QGroupBox, QLabel, QVBoxLayout, QWidget


class JogHelpPanel(QGroupBox):
    def __init__(self, parent: QWidget | None = None):
        super().__init__("Jogging au clavier", parent)
        text = (
            "<b>Activer la case « Activer le clavier »</b> dans le panneau Jogging puis :\n"
            "<ul>"
            "<li><b>Chariot gauche corde (X)</b> — Flèche gauche / droite</li>"
            "<li><b>Chariot gauche épaisseur (Y)</b> — Flèche haut / bas</li>"
            "<li><b>Chariot droit corde (A)</b> — Page Up / Page Down</li>"
            "</ul>"
            "Le pas de déplacement et la vitesse sont ceux choisis dans le panneau Jogging "
            "(distance 1 / 10 / 50 / 100 mm et vitesse 50 / 100 / 200 / 300 mm/min)."
        ).replace("\n", "")
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.RichText)
        f = QFont()
        f.setPointSize(10)
        lbl.setFont(f)
        v = QVBoxLayout(self)
        v.addWidget(lbl)
        v.addStretch(1)
