"""Affichage des décalages courants : G54..G59, G28, G30, G92, TLO, PRB.

La commande `$#` renvoie :
  [G54:0.000,0.000,0.000,0.000]
  [G55:0.000,0.000,0.000,0.000]
  ...
  [G92:0.000,0.000,0.000,0.000]
  [TLO:0.000]
  [PRB:0.000,0.000,0.000:0]
"""

from __future__ import annotations

import re

from PySide6.QtCore import Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

OFFSET_RE = re.compile(r"^\[(G54|G55|G56|G57|G58|G59|G28|G30|G92|TLO|PRB):([^\]]+)\]")


class OffsetsPanel(QGroupBox):
    refresh_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Décalages actifs ($#)", parent)
        self.btn_refresh = QPushButton("Rafraîchir ($#)")
        self.btn_refresh.clicked.connect(self.refresh_requested)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Repère", "X", "Y", "Z", "A"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.setStyleSheet("QTableWidget { font-family: Consolas; font-size: 11px; }")
        self.table.setMinimumHeight(220)

        v = QVBoxLayout(self)
        v.addWidget(self.btn_refresh)
        v.addWidget(self.table, 1)

        self._row_by_key: dict[str, int] = {}

    def clear(self) -> None:
        self.table.setRowCount(0)
        self._row_by_key.clear()

    @Slot(str)
    def maybe_consume_line(self, line: str) -> None:
        m = OFFSET_RE.match(line)
        if not m:
            return
        key = m.group(1)
        body = m.group(2)
        # PRB renvoie quelque chose comme "0.000,0.000,0.000,0.000:0"
        coords_part = body.split(":")[0]
        vals = []
        for tok in coords_part.split(","):
            try:
                vals.append(float(tok))
            except ValueError:
                vals.append(None)
        # On affiche les 4 premiers
        row = self._row_by_key.get(key)
        if row is None:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self._row_by_key[key] = row
            self.table.setItem(row, 0, QTableWidgetItem(key))
        for c in range(4):
            v = vals[c] if c < len(vals) else None
            txt = "" if v is None else f"{v:.3f}"
            it = self.table.item(row, c + 1)
            if it is None:
                it = QTableWidgetItem(txt)
                self.table.setItem(row, c + 1, it)
            else:
                it.setText(txt)
