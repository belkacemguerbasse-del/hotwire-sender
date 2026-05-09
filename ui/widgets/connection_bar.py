"""Barre de connexion Grbl : COM, baud, Connecter / Déconnecter, Re-Scan."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.grbl_link import list_serial_ports
from core import persistence

BAUDS = ["9600", "19200", "38400", "57600", "115200", "230400", "250000"]


class ConnectionBar(QGroupBox):
    connect_requested = Signal(str, int)
    disconnect_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Grbl", parent)
        self.cb_port = QComboBox()
        self.cb_baud = QComboBox()
        self.cb_baud.addItems(BAUDS)
        self.cb_baud.setCurrentText("115200")
        self.btn_connect = QPushButton("Connecter")
        self.btn_rescan = QPushButton("Re-Scan")

        self.btn_rescan.clicked.connect(self.refresh_ports)
        self.btn_connect.clicked.connect(self._toggle)

        line1 = QHBoxLayout()
        line1.addWidget(self.cb_port, 1)
        line1.addWidget(self.btn_connect)
        line2 = QHBoxLayout()
        line2.addWidget(self.cb_baud, 1)
        line2.addWidget(self.btn_rescan)

        lay = QVBoxLayout(self)
        lay.addLayout(line1)
        lay.addLayout(line2)

        self._open = False
        self.refresh_ports()

        # Restaure le dernier port et baud
        last_port = persistence.get_str("connection/port")
        last_baud = persistence.get_str("connection/baud", "115200")
        if last_port:
            idx = self.cb_port.findData(last_port)
            if idx >= 0:
                self.cb_port.setCurrentIndex(idx)
        if last_baud:
            idx = self.cb_baud.findText(last_baud)
            if idx >= 0:
                self.cb_baud.setCurrentIndex(idx)

    def refresh_ports(self) -> None:
        prev = self.cb_port.currentText()
        self.cb_port.clear()
        for dev, desc in list_serial_ports():
            label = dev if not desc or desc == "n/a" else f"{dev} — {desc}"
            self.cb_port.addItem(label, dev)
        if prev:
            idx = self.cb_port.findText(prev)
            if idx >= 0:
                self.cb_port.setCurrentIndex(idx)

    def set_open(self, is_open: bool) -> None:
        self._open = is_open
        self.btn_connect.setText("Déconnecter" if is_open else "Connecter")
        self.cb_port.setEnabled(not is_open)
        self.cb_baud.setEnabled(not is_open)
        self.btn_rescan.setEnabled(not is_open)

    def _toggle(self) -> None:
        if self._open:
            self.disconnect_requested.emit()
        else:
            port = self.cb_port.currentData() or self.cb_port.currentText()
            try:
                baud = int(self.cb_baud.currentText())
            except ValueError:
                baud = 115200
            if port:
                persistence.set_("connection/port", port)
                persistence.set_("connection/baud", str(baud))
                self.connect_requested.emit(port, baud)
