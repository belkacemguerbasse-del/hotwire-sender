"""Affichage des infos firmware Grbl : version, options, axes, build, port.

Capture les lignes :
- `Grbl 1.2h ['$' for help]`     → version
- `[VER:1.2h.YYYYMMDD:....]`     → build
- `[OPT:VNMGZHL,35,255,64]`       → flags + buffers
- `[AXS:4:XYZA]`                  → nombre + lettres d'axes
"""

from __future__ import annotations

import re

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Signal

VER_RE = re.compile(r"^\[VER:([^\]]+)\]")
OPT_RE = re.compile(r"^\[OPT:([^\]]+)\]")
AXS_RE = re.compile(r"^\[AXS:([^\]]+)\]")
BANNER_RE = re.compile(r"^Grbl\s+(\S+)")


class FirmwareInfoPanel(QGroupBox):
    refresh_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Informations firmware", parent)
        mono = QFont("Consolas", 10)

        self.lbl_version = QLabel("—")
        self.lbl_build = QLabel("—")
        self.lbl_options = QLabel("—")
        self.lbl_axes = QLabel("—")
        self.lbl_buffers = QLabel("—")
        self.lbl_port = QLabel("—")
        for w in (self.lbl_version, self.lbl_build, self.lbl_options, self.lbl_axes, self.lbl_buffers, self.lbl_port):
            w.setFont(mono)
            w.setTextInteractionFlags(Qt.TextSelectableByMouse)

        form = QFormLayout()
        form.addRow("Version :", self.lbl_version)
        form.addRow("Build :", self.lbl_build)
        form.addRow("Options :", self.lbl_options)
        form.addRow("Axes :", self.lbl_axes)
        form.addRow("Buffers (planner/RX/TX) :", self.lbl_buffers)
        form.addRow("Port :", self.lbl_port)

        self.btn_refresh = QPushButton("Rafraîchir ($I)")
        self.btn_refresh.clicked.connect(self.refresh_requested)

        v = QVBoxLayout(self)
        v.addLayout(form)
        v.addWidget(self.btn_refresh)
        v.addStretch(1)

    def set_port(self, port: str) -> None:
        self.lbl_port.setText(port or "—")

    def clear(self) -> None:
        for w in (self.lbl_version, self.lbl_build, self.lbl_options, self.lbl_axes, self.lbl_buffers):
            w.setText("—")

    @Slot(str)
    def maybe_consume_line(self, line: str) -> None:
        m = BANNER_RE.match(line)
        if m:
            self.lbl_version.setText(m.group(1))
            return
        m = VER_RE.match(line)
        if m:
            self.lbl_build.setText(m.group(1).rstrip(":"))
            return
        m = OPT_RE.match(line)
        if m:
            inner = m.group(1)
            parts = inner.split(",")
            flags = parts[0] if parts else ""
            self.lbl_options.setText(flags)
            if len(parts) >= 4:
                self.lbl_buffers.setText(f"{parts[1]} blocs / {parts[2]} RX / {parts[3]} TX")
            return
        m = AXS_RE.match(line)
        if m:
            inner = m.group(1)
            ps = inner.split(":")
            if len(ps) >= 2:
                self.lbl_axes.setText(f"{ps[0]} axes ({ps[1]})")
            else:
                self.lbl_axes.setText(inner)
            return
