"""Boutons de contrôle Grbl : Référencement, Débloq, Réinit, Retiens, Départ, Vérifie."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QGroupBox, QPushButton, QVBoxLayout, QWidget

from ui.i18n import tr


class ControlPanel(QWidget):
    home_requested = Signal()
    unlock_requested = Signal()
    reset_requested = Signal()
    hold_requested = Signal()
    resume_requested = Signal()
    check_toggle_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.btn_home = QPushButton(tr("Cycle référencement"))
        self.btn_unlock = QPushButton(tr("Débloq."))
        self.btn_reset = QPushButton(tr("Réinit."))
        self.btn_hold = QPushButton(tr("Retiens"))
        self.btn_resume = QPushButton(tr("Départ"))
        self.btn_check = QPushButton(tr("Vérifie"))

        for b in (
            self.btn_home,
            self.btn_unlock,
            self.btn_reset,
            self.btn_hold,
            self.btn_resume,
            self.btn_check,
        ):
            b.setMinimumHeight(34)

        self.btn_home.clicked.connect(self.home_requested)
        self.btn_unlock.clicked.connect(self.unlock_requested)
        self.btn_reset.clicked.connect(self.reset_requested)
        self.btn_hold.clicked.connect(self.hold_requested)
        self.btn_resume.clicked.connect(self.resume_requested)
        self.btn_check.clicked.connect(self.check_toggle_requested)

        gb_home = QGroupBox(tr("Référencement"))
        v1 = QVBoxLayout(gb_home)
        v1.addWidget(self.btn_home)

        gb_ctrl = QGroupBox(tr("Contrôle"))
        g = QGridLayout(gb_ctrl)
        g.addWidget(self.btn_unlock, 0, 0)
        g.addWidget(self.btn_reset, 0, 1)
        g.addWidget(self.btn_hold, 0, 2)
        g.addWidget(self.btn_resume, 0, 3)
        g.addWidget(self.btn_check, 0, 4)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(gb_home)
        outer.addWidget(gb_ctrl)
