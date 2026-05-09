"""Onglet Réglages : édition des paramètres `$N` du firmware Grbl + outils annexes.

Layout 3 colonnes :
- Gauche  : table éditable des $N (load/edit/save)
- Milieu  : Position (G28/G30, zéros), Décalages actifs ($#)
- Droite  : Informations firmware ($I), Aide jog clavier
"""

from __future__ import annotations

import re

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.grbl_settings import settings_info

from .firmware_info_panel import FirmwareInfoPanel
from .homing_invert_panel import HomingInvertPanel
from .jog_help_panel import JogHelpPanel
from .offsets_panel import OffsetsPanel
from .position_panel import PositionPanel
from .preferences_panel import PreferencesPanel

SETTING_RE = re.compile(r"^\$(\d+)\s*=\s*(.+?)\s*$")


class _SettingsTable(QWidget):
    """Tableau éditable des `$N` du firmware."""

    write_setting_requested = Signal(str)
    reload_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.btn_reload = QPushButton("Charger réglages Grbl")
        self.btn_reload.setMinimumHeight(32)
        self.btn_reload.clicked.connect(self.reload_requested)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["ID", "Valeur", "Label", "Unité", "Description"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.Interactive)
        h.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setStyleSheet("QTableWidget { font-family: Consolas; font-size: 12px; }")
        self.table.itemChanged.connect(self._on_item_changed)

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(self.btn_reload)
        v.addWidget(self.table, 1)

        self._row_by_id: dict[int, int] = {}
        self._suppress_change = False

    def clear(self) -> None:
        self._suppress_change = True
        self.table.setRowCount(0)
        self._row_by_id.clear()
        self._suppress_change = False

    @Slot(str)
    def maybe_consume_line(self, line: str) -> None:
        m = SETTING_RE.match(line)
        if not m:
            return
        try:
            sid = int(m.group(1))
        except ValueError:
            return
        self._upsert(sid, m.group(2))

    def _upsert(self, sid: int, value: str) -> None:
        info = settings_info(sid)
        self._suppress_change = True
        try:
            row = self._row_by_id.get(sid)
            if row is None:
                row = self.table.rowCount()
                self.table.insertRow(row)
                id_item = QTableWidgetItem(f"${sid}")
                id_item.setFlags(id_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, 0, id_item)

                val_item = QTableWidgetItem(value)
                f = QFont("Consolas")
                f.setBold(True)
                val_item.setFont(f)
                val_item.setData(Qt.UserRole, sid)
                self.table.setItem(row, 1, val_item)

                lbl = QTableWidgetItem(info.label)
                lbl.setFlags(lbl.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, 2, lbl)

                unit = QTableWidgetItem(info.unit)
                unit.setFlags(unit.flags() & ~Qt.ItemIsEditable)
                unit.setForeground(QColor("#666"))
                self.table.setItem(row, 3, unit)

                desc = QTableWidgetItem(info.description)
                desc.setFlags(desc.flags() & ~Qt.ItemIsEditable)
                desc.setForeground(QColor("#444"))
                self.table.setItem(row, 4, desc)

                self._row_by_id[sid] = row
                self._sort_by_id()
            else:
                self.table.item(row, 1).setText(value)
        finally:
            self._suppress_change = False

    def _sort_by_id(self) -> None:
        rows = []
        for row in range(self.table.rowCount()):
            id_text = self.table.item(row, 0).text().lstrip("$")
            try:
                sid = int(id_text)
            except ValueError:
                continue
            cells = [self.table.item(row, c).text() for c in range(self.table.columnCount())]
            rows.append((sid, cells))
        rows.sort(key=lambda r: r[0])
        self.table.setRowCount(0)
        self._row_by_id.clear()
        for sid, cells in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self._row_by_id[sid] = row
            for c, txt in enumerate(cells):
                item = QTableWidgetItem(txt)
                if c != 1:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                else:
                    item.setData(Qt.UserRole, sid)
                    f = QFont("Consolas")
                    f.setBold(True)
                    item.setFont(f)
                if c in (3, 4):
                    item.setForeground(QColor("#666" if c == 3 else "#444"))
                self.table.setItem(row, c, item)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._suppress_change:
            return
        if item.column() != 1:
            return
        sid = item.data(Qt.UserRole)
        if sid is None:
            return
        new_val = item.text().strip()
        if not new_val:
            return
        self.write_setting_requested.emit(f"${sid}={new_val}")


class SettingsTab(QWidget):
    """Onglet complet Réglages : assemblage des sous-panneaux."""

    write_setting_requested = Signal(str)  # ligne `$N=val` à envoyer
    reload_requested = Signal()             # demande d'envoi de '$$'
    send_line_requested = Signal(str)       # ligne g-code arbitraire (G28.1, $I, $#, …)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self._table = _SettingsTable()
        self._table.write_setting_requested.connect(self.write_setting_requested)
        self._table.reload_requested.connect(self.reload_requested)

        self.position = PositionPanel()
        self.position.send_line_requested.connect(self.send_line_requested)

        self.offsets = OffsetsPanel()
        self.offsets.refresh_requested.connect(lambda: self.send_line_requested.emit("$#"))

        self.firmware = FirmwareInfoPanel()
        self.firmware.refresh_requested.connect(lambda: self.send_line_requested.emit("$I"))

        self.preferences = PreferencesPanel()
        # `settings_applied` est ré-émis tel quel pour que le main_window
        # propage les valeurs au runtime (poll period, etc.)

        self.homing_invert = HomingInvertPanel()
        self.homing_invert.write_setting_requested.connect(self.write_setting_requested)
        self.homing_invert.refresh_requested.connect(self.reload_requested)

        self.jog_help = JogHelpPanel()

        # Colonnes
        col_left = self._table  # déjà un widget
        col_mid = QWidget()
        v_mid = QVBoxLayout(col_mid)
        v_mid.setContentsMargins(0, 0, 0, 0)
        v_mid.addWidget(self.position)
        v_mid.addWidget(self.homing_invert)
        v_mid.addWidget(self.offsets, 1)

        col_right = QWidget()
        v_right = QVBoxLayout(col_right)
        v_right.setContentsMargins(0, 0, 0, 0)
        v_right.addWidget(self.preferences)
        v_right.addWidget(self.firmware)
        v_right.addWidget(self.jog_help)
        v_right.addStretch(1)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(col_left)
        splitter.addWidget(col_mid)
        splitter.addWidget(col_right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 1)
        splitter.setSizes([700, 380, 400])

        outer = QHBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.addWidget(splitter)

    # ---- API publique pour le main_window ----

    def clear(self) -> None:
        """Reset complet (à la déconnexion par exemple)."""
        self._table.clear()
        self.offsets.clear()
        self.firmware.clear()

    def maybe_consume_line(self, line: str) -> None:
        """Routeur : dispatche chaque ligne RX vers le bon sous-panneau."""
        self._table.maybe_consume_line(line)
        self.offsets.maybe_consume_line(line)
        self.firmware.maybe_consume_line(line)
        # Mise à jour du panneau Inverser homing si on voit un $23=...
        m = SETTING_RE.match(line)
        if m:
            try:
                if int(m.group(1)) == 23:
                    self.homing_invert.set_mask(int(m.group(2)))
            except ValueError:
                pass

    def set_port(self, port: str) -> None:
        self.firmware.set_port(port)
