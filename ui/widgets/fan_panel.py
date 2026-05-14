"""Contrôle du ventilateur de refroidissement RAMPS 1.4.

Pilote la sortie 12V D10 du RAMPS via les G-codes Grbl standards :
  - `M8` : coolant flood ON   → met D10 à 12V (alimente le ventilateur)
  - `M9` : coolant off        → coupe D10

Câblage typique : ventilateur 12V branché sur la sortie « D10 » du RAMPS
(connecteur HE0 / BED-OUT2 selon les variantes). Le firmware grbl-Mega-5X
mappe `COOLANT_FLOOD_BIT` sur PB4 = MEGA D10 (cf. cpu_map.h).

Si tu préfères piloter D9 (sortie « FAN » classique du RAMPS), utilise
plutôt `M7` / `M9` ; il suffit de changer la commande dans `main_window`.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.i18n import tr
from ui.theme import COLORS, ui_font


class FanPanel(QGroupBox):
    """Carte « Ventilateur RAMPS » avec un gros bouton ON/OFF."""

    fan_on_requested = Signal()
    fan_off_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(tr("Ventilateur RAMPS"), parent)
        self._on = False

        self.lbl_status = QLabel("OFF")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setFont(ui_font(16, bold=True))
        self._refresh_status_style()

        self.btn_toggle = QPushButton(tr("ALLUMER LE VENTILATEUR"))
        self.btn_toggle.setProperty("variant", "primary")
        self.btn_toggle.setMinimumHeight(46)
        self.btn_toggle.setFont(ui_font(11, bold=True))
        self.btn_toggle.setToolTip(
            tr(
                "Active la sortie 12V D10 du RAMPS via M8 (coolant flood). "
                "Branche le ventilateur sur cette sortie."
            )
        )
        self.btn_toggle.clicked.connect(self._on_toggle)

        row = QHBoxLayout()
        row.addWidget(self.lbl_status, 1)
        row.addWidget(self.btn_toggle, 2)

        v = QVBoxLayout(self)
        v.setSpacing(8)
        v.addLayout(row)

    def _refresh_status_style(self) -> None:
        if self._on:
            self.lbl_status.setStyleSheet(f"color: {COLORS['success']};")
        else:
            self.lbl_status.setStyleSheet(f"color: {COLORS['text_subtle']};")

    def _on_toggle(self) -> None:
        if self._on:
            self.fan_off_requested.emit()
        else:
            self.fan_on_requested.emit()

    def set_on(self, on: bool) -> None:
        self._on = on
        if on:
            self.btn_toggle.setText(tr("COUPER LE VENTILATEUR"))
            self.btn_toggle.setProperty("variant", "danger")
            self.lbl_status.setText("ON")
        else:
            self.btn_toggle.setText(tr("ALLUMER LE VENTILATEUR"))
            self.btn_toggle.setProperty("variant", "primary")
            self.lbl_status.setText("OFF")
        # Re-style après changement de propriété
        self.btn_toggle.style().unpolish(self.btn_toggle)
        self.btn_toggle.style().polish(self.btn_toggle)
        self._refresh_status_style()

    def force_off(self) -> None:
        if self._on:
            self.set_on(False)
            self.fan_off_requested.emit()
