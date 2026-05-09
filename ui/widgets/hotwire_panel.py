"""Contrôle du fil chaud : slider de puissance + bouton ON/OFF gros et coloré.

Côté firmware grbl-Mega-5X, la sortie PWM est pilotée via M3/M5 + valeur S :
  - ON  : `M3 S<value>`
  - OFF : `M5`
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ui.theme import COLORS, mono_font, ui_font


class HotWirePanel(QGroupBox):
    set_power_requested = Signal(int)
    turn_on_requested = Signal(int)
    turn_off_requested = Signal()

    def __init__(self, max_value: int = 1000, parent: QWidget | None = None):
        super().__init__("Fil chaud", parent)
        self.max_value = max_value
        self._on = False
        self._value = 0

        # --- Ligne 1 : libellé + valeur courante ---
        self.lbl_title = QLabel("Puissance")
        self.lbl_title.setStyleSheet(f"color: {COLORS['text_muted']};")
        self.lbl_value = QLabel("0")
        self.lbl_value.setFont(mono_font(14, bold=True))
        self.lbl_value.setMinimumWidth(70)
        self.lbl_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        row1 = QHBoxLayout()
        row1.addWidget(self.lbl_title, 1)
        row1.addWidget(self.lbl_value)

        # --- Slider ---
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, max_value)
        self.slider.setValue(0)
        self.slider.setTickPosition(QSlider.TicksBelow)
        self.slider.setTickInterval(max(1, max_value // 10))
        self.slider.valueChanged.connect(self._on_slider)

        # --- Statut + gros bouton ---
        self.lbl_status = QLabel("OFF")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setFont(ui_font(16, bold=True))
        self._refresh_status_style()

        self.btn_toggle = QPushButton("ALLUMER LE FIL")
        self.btn_toggle.setProperty("variant", "primary")
        self.btn_toggle.setMinimumHeight(46)
        self.btn_toggle.setFont(ui_font(11, bold=True))
        self.btn_toggle.clicked.connect(self._on_toggle)

        row3 = QHBoxLayout()
        row3.addWidget(self.lbl_status, 1)
        row3.addWidget(self.btn_toggle, 2)

        v = QVBoxLayout(self)
        v.setSpacing(8)
        v.addLayout(row1)
        v.addWidget(self.slider)
        v.addLayout(row3)

    def _refresh_status_style(self) -> None:
        if self._on:
            self.lbl_status.setStyleSheet(f"color: {COLORS['danger']};")
        else:
            self.lbl_status.setStyleSheet(f"color: {COLORS['text_subtle']};")

    def _on_slider(self, v: int) -> None:
        self._value = v
        self.lbl_value.setText(str(v))
        if self._on:
            self.set_power_requested.emit(v)

    def _on_toggle(self) -> None:
        if self._on:
            self.turn_off_requested.emit()
        else:
            self.turn_on_requested.emit(self._value)

    def set_on(self, on: bool) -> None:
        self._on = on
        if on:
            self.btn_toggle.setText("COUPER LE FIL")
            self.btn_toggle.setProperty("variant", "danger")
            self.lbl_status.setText("ON")
        else:
            self.btn_toggle.setText("ALLUMER LE FIL")
            self.btn_toggle.setProperty("variant", "primary")
            self.lbl_status.setText("OFF")
        # Re-style après changement de propriété
        self.btn_toggle.style().unpolish(self.btn_toggle)
        self.btn_toggle.style().polish(self.btn_toggle)
        self._refresh_status_style()

    def force_off(self) -> None:
        if self._on:
            self.set_on(False)
            self.turn_off_requested.emit()
