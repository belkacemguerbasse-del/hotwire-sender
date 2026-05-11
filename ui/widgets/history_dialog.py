"""Dialog d'historique des coupes : affiche la liste des jobs exécutés
et permet de recharger un fichier en 1 clic.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.job_history import HistoryEntry, JobHistory

STATUS_COLORS = {
    "ok":      ("#1f9d55", "Terminé"),
    "stopped": ("#f59f00", "Stoppé"),
    "aborted": ("#d6363d", "Abandonné"),
    "error":   ("#d6363d", "Erreur"),
}


def _fmt_duration(s: float) -> str:
    s = int(s)
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    if h > 0:
        return f"{h}h {m:02d}min {sec:02d}s"
    if m > 0:
        return f"{m}min {sec:02d}s"
    return f"{sec}s"


def _fmt_iso(iso: str) -> str:
    # 2026-05-11T14:23:01 → "11/05/2026 14:23"
    try:
        d, t = iso.split("T")
        y, m, day = d.split("-")
        hh, mm = t.split(":")[:2]
        return f"{day}/{m}/{y} {hh}:{mm}"
    except Exception:
        return iso


class HistoryDialog(QDialog):
    reload_requested = Signal(str)  # file path à recharger

    def __init__(self, history: JobHistory, parent: QWidget | None = None):
        super().__init__(parent)
        self.history = history
        self.setWindowTitle("Historique des coupes")
        self.resize(900, 540)

        self._build_ui()
        self._refresh()
        # Si l'historique change pendant que le dialog est ouvert, rafraîchit
        self.history.changed.connect(self._refresh)

    def _build_ui(self) -> None:
        title = QLabel("📋  Historique des programmes lancés")
        f = title.font()
        f.setPointSize(13)
        f.setBold(True)
        title.setFont(f)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Date", "Durée", "Fichier", "Lignes", "État", "Chemin"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.Interactive)
        h.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(5, QHeaderView.Stretch)
        self.table.setStyleSheet(
            "QTableWidget { font-family: Consolas; font-size: 11px; }"
        )
        self.table.itemDoubleClicked.connect(lambda _it: self._reload())

        self.lbl_info = QLabel("")
        self.lbl_info.setStyleSheet("color: #637381; font-style: italic;")

        self.btn_reload = QPushButton("📂  Recharger")
        self.btn_reload.setProperty("variant", "primary")
        self.btn_reload.setMinimumHeight(34)
        self.btn_reload.setToolTip(
            "Recharge le fichier sélectionné dans le panneau GCode "
            "(double-clic sur une ligne fait pareil)."
        )
        self.btn_reload.clicked.connect(self._reload)

        self.btn_clear = QPushButton("🗑  Tout effacer")
        self.btn_clear.setMinimumHeight(34)
        self.btn_clear.clicked.connect(self._clear)

        self.btn_close = QPushButton("Fermer")
        self.btn_close.setMinimumHeight(34)
        self.btn_close.clicked.connect(self.close)

        actions = QHBoxLayout()
        actions.addWidget(self.btn_reload)
        actions.addWidget(self.btn_clear)
        actions.addStretch(1)
        actions.addWidget(self.btn_close)

        v = QVBoxLayout(self)
        v.addWidget(title)
        v.addWidget(self.table, 1)
        v.addWidget(self.lbl_info)
        v.addLayout(actions)

    def _refresh(self) -> None:
        entries = self.history.all()
        self.table.setRowCount(len(entries))
        for row, e in enumerate(entries):
            self.table.setItem(row, 0, QTableWidgetItem(_fmt_iso(e.started_at)))
            self.table.setItem(row, 1, QTableWidgetItem(_fmt_duration(e.duration_s)))

            name_item = QTableWidgetItem(e.file_name or "(sans nom)")
            f = name_item.font()
            f.setBold(True)
            name_item.setFont(f)
            self.table.setItem(row, 2, name_item)

            self.table.setItem(row, 3, QTableWidgetItem(str(e.lines_count)))

            color, label = STATUS_COLORS.get(e.status, ("#637381", e.status))
            st_item = QTableWidgetItem(label)
            st_item.setForeground(QBrush(QColor(color)))
            ff = st_item.font()
            ff.setBold(True)
            st_item.setFont(ff)
            self.table.setItem(row, 4, st_item)

            self.table.setItem(row, 5, QTableWidgetItem(e.file_path))

        if entries:
            self.lbl_info.setText(
                f"{len(entries)} entrée(s) · "
                f"stocké dans : {self.history.file_path}"
            )
        else:
            self.lbl_info.setText("Aucun job enregistré pour le moment.")

    def _selected_entry(self) -> HistoryEntry | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        row = rows[0].row()
        entries = self.history.all()
        if 0 <= row < len(entries):
            return entries[row]
        return None

    def _reload(self) -> None:
        e = self._selected_entry()
        if e is None:
            QMessageBox.information(
                self, "Recharger",
                "Sélectionne d'abord une ligne dans l'historique."
            )
            return
        if not e.file_path or e.file_path == "<slicer>":
            QMessageBox.warning(
                self, "Impossible de recharger",
                "Ce job a été généré par le slicer en interne — il n'y a "
                "pas de fichier .gcode à recharger. Régénère-le depuis le "
                "slicer si besoin."
            )
            return
        self.reload_requested.emit(e.file_path)
        self.close()

    def _clear(self) -> None:
        if not self.history.all():
            return
        answer = QMessageBox.question(
            self, "Effacer l'historique",
            "Effacer toutes les entrées de l'historique ?\n"
            "Cette action est irréversible.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self.history.clear()
