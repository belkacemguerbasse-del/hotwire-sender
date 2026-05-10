"""Panneau G-code : ouvrir / lecture / pause / stop / reload + table de progression."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class GcodePanel(QGroupBox):
    file_loaded = Signal(str, list)         # path, list[str] lines
    play_requested = Signal()
    pause_requested = Signal()
    stop_requested = Signal()
    reload_requested = Signal()
    simulate_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__("GCode", parent)

        self.btn_open = QPushButton("Ouvrir…")
        self.btn_simulate = QPushButton("🎬  Simuler")
        self.btn_play = QPushButton("▶  Lancer")
        self.btn_pause = QPushButton("⏸  Pause")
        self.btn_stop = QPushButton("⏹  Stop")
        self.btn_reload = QPushButton("↻  Recharger")
        self.btn_open.setToolTip("Ouvrir un fichier G-code (.nc, .gcode, .tap, .ngc)")
        self.btn_simulate.setToolTip(
            "Lance une simulation visuelle dans la vue 3D, sans envoyer "
            "au firmware. Vérifie la trajectoire avant la vraie coupe."
        )
        self.btn_play.setToolTip("Lancer / reprendre l'exécution sur la machine")
        self.btn_pause.setToolTip("Mettre en pause (feed hold)")
        self.btn_stop.setToolTip("Arrêter et réinitialiser")
        self.btn_reload.setToolTip("Recharger le fichier depuis le disque")
        self.btn_play.setProperty("variant", "primary")
        for b in (self.btn_open, self.btn_simulate, self.btn_play,
                  self.btn_pause, self.btn_stop, self.btn_reload):
            b.setMinimumHeight(30)

        self.btn_open.clicked.connect(self._open)
        self.btn_simulate.clicked.connect(self.simulate_requested)
        self.btn_play.clicked.connect(self.play_requested)
        self.btn_pause.clicked.connect(self.pause_requested)
        self.btn_stop.clicked.connect(self.stop_requested)
        self.btn_reload.clicked.connect(self.reload_requested)

        self.lbl_progress = QLabel("0 de 0")
        self.lbl_elapsed = QLabel("00:00:00")
        self.lbl_elapsed.setFont(QFont("Consolas", 10))

        top = QHBoxLayout()
        top.addWidget(self.btn_open)
        top.addWidget(self.btn_simulate)
        top.addWidget(self.btn_play)
        top.addWidget(self.btn_pause)
        top.addWidget(self.btn_stop)
        top.addWidget(self.btn_reload)
        top.addStretch(1)

        info = QHBoxLayout()
        info.addWidget(QLabel("Suivre"))
        info.addWidget(self.lbl_progress)
        info.addStretch(1)
        info.addWidget(QLabel("Écoulé"))
        info.addWidget(self.lbl_elapsed)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Sts", "Ligne", "Gcode"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.setStyleSheet("QTableWidget { font-family: Consolas; font-size: 11px; }")

        v = QVBoxLayout(self)
        v.addLayout(top)
        v.addLayout(info)
        v.addWidget(self.table, 1)

        self._lines: list[str] = []
        self._current_path: str = ""

    def _open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Ouvrir un fichier G-code", "", "G-code (*.nc *.gcode *.tap *.ngc *.txt);;Tous (*)"
        )
        if path:
            self.load_file(path)

    def load_file(self, path: str) -> None:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines = [ln.rstrip("\r\n") for ln in f.readlines()]
        except OSError as e:
            self.append_status_message(f"Erreur ouverture: {e}")
            return
        self._lines = lines
        self._current_path = path
        self.table.setRowCount(0)
        for i, ln in enumerate(lines, start=1):
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(""))
            self.table.setItem(row, 1, QTableWidgetItem(str(i)))
            self.table.setItem(row, 2, QTableWidgetItem(ln))
        self.lbl_progress.setText(f"0 de {len(lines)}")
        self.file_loaded.emit(path, list(lines))

    def lines(self) -> list[str]:
        return list(self._lines)

    @Slot(int, str)
    def mark_line(self, idx_zero_based: int, status: str) -> None:
        """idx_zero_based : index dans la liste, status : 'sent'/'ok'/'err'."""
        if idx_zero_based < 0 or idx_zero_based >= self.table.rowCount():
            return
        item = self.table.item(idx_zero_based, 0)
        if item is None:
            item = QTableWidgetItem("")
            self.table.setItem(idx_zero_based, 0, item)
        item.setText(status)
        self.lbl_progress.setText(f"{idx_zero_based + 1} de {len(self._lines)}")
        self.table.scrollToItem(item)

    @Slot(str)
    def set_elapsed(self, hms: str) -> None:
        self.lbl_elapsed.setText(hms)

    def append_status_message(self, msg: str) -> None:
        # Hook si plus tard on veut afficher des erreurs en pied de panneau.
        pass

    def reset_marks(self) -> None:
        for row in range(self.table.rowCount()):
            it = self.table.item(row, 0)
            if it is not None:
                it.setText("")
        self.lbl_progress.setText(f"0 de {len(self._lines)}")
