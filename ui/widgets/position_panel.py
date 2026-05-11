"""Mémoires de position G28 / G30 et zéros par axe.

Grbl mémorise jusqu'à 2 positions en EEPROM accessibles par G28/G30 :
- `G28.1`     : enregistre la position courante en mémoire G28
- `G28`       : retourne à la position G28
- `G30.1`     : enregistre la position courante en mémoire G30
- `G30`       : retourne à la position G30
- `G10 L20 P0 X0 Y0 Z0 A0` : remet à zéro le WCO sur les axes donnés
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.i18n import tr


class PositionPanel(QGroupBox):
    send_line_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(tr("Position (G28 / G30)"), parent)

        # --- Mémoires G28 / G30 ---
        self.btn_set_g28 = QPushButton(tr("Mémoriser ici → G28"))
        self.btn_go_g28 = QPushButton(tr("Aller à G28"))
        self.btn_set_g30 = QPushButton(tr("Mémoriser ici → G30"))
        self.btn_go_g30 = QPushButton(tr("Aller à G30"))

        self.btn_set_g28.clicked.connect(lambda: self.send_line_requested.emit("G28.1"))
        self.btn_go_g28.clicked.connect(lambda: self.send_line_requested.emit("G28"))
        self.btn_set_g30.clicked.connect(lambda: self.send_line_requested.emit("G30.1"))
        self.btn_go_g30.clicked.connect(lambda: self.send_line_requested.emit("G30"))

        gb_mem = QGroupBox(tr("Mémoires"))
        gm = QGridLayout(gb_mem)
        gm.addWidget(self.btn_set_g28, 0, 0)
        gm.addWidget(self.btn_go_g28, 0, 1)
        gm.addWidget(self.btn_set_g30, 1, 0)
        gm.addWidget(self.btn_go_g30, 1, 1)

        # --- Zéros WCO ---
        self.btn_zero_all = QPushButton(tr("Zéro tout (XYZA)"))
        self.btn_zero_x = QPushButton(tr("Zéro X"))
        self.btn_zero_y = QPushButton(tr("Zéro Y"))
        self.btn_zero_z = QPushButton(tr("Zéro Z"))
        self.btn_zero_a = QPushButton(tr("Zéro A"))

        self.btn_zero_all.clicked.connect(
            lambda: self.send_line_requested.emit("G10 L20 P0 X0 Y0 Z0 A0")
        )
        self.btn_zero_x.clicked.connect(lambda: self.send_line_requested.emit("G10 L20 P0 X0"))
        self.btn_zero_y.clicked.connect(lambda: self.send_line_requested.emit("G10 L20 P0 Y0"))
        self.btn_zero_z.clicked.connect(lambda: self.send_line_requested.emit("G10 L20 P0 Z0"))
        self.btn_zero_a.clicked.connect(lambda: self.send_line_requested.emit("G10 L20 P0 A0"))

        gb_zero = QGroupBox(tr("Zéros (WCO)"))
        gz = QGridLayout(gb_zero)
        gz.addWidget(self.btn_zero_all, 0, 0, 1, 4)
        gz.addWidget(self.btn_zero_x, 1, 0)
        gz.addWidget(self.btn_zero_y, 1, 1)
        gz.addWidget(self.btn_zero_z, 1, 2)
        gz.addWidget(self.btn_zero_a, 1, 3)

        for b in (
            self.btn_set_g28, self.btn_go_g28, self.btn_set_g30, self.btn_go_g30,
            self.btn_zero_all, self.btn_zero_x, self.btn_zero_y, self.btn_zero_z, self.btn_zero_a,
        ):
            b.setMinimumHeight(30)

        v = QVBoxLayout(self)
        v.addWidget(gb_mem)
        v.addWidget(gb_zero)
