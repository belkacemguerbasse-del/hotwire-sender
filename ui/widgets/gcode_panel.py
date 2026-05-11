"""Panneau G-code : ouvrir / lecture / pause / stop / reload + table de progression.

Optimisations clés :
- mark_line() est appelée jusqu'à plusieurs milliers de fois par seconde lors
  d'un streaming rapide. Le scrollToItem et la maj du label de progression
  sont throttlés à 10 Hz max via un QTimer pour ne pas bloquer l'UI.
- load_file() insère les lignes en bulk avec setUpdatesEnabled(False) pour
  éviter un re-layout par ligne (gain : ~10× sur les gros fichiers).
- reset_marks() utilise le même mécanisme bulk.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QBrush, QColor, QFont
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


# Brush utilisé pour surligner la ligne courante en exécution
_HIGHLIGHT_BRUSH = QBrush(QColor("#cfe1ff"))   # bleu clair (cohérent avec thème)
_DEFAULT_BRUSH = QBrush()  # par défaut Qt = transparent


class GcodePanel(QGroupBox):
    file_loaded = Signal(str, list)         # path, list[str] lines
    play_requested = Signal()
    pause_requested = Signal()
    stop_requested = Signal()
    reload_requested = Signal()
    simulate_requested = Signal()
    history_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__("GCode", parent)

        self.btn_open = QPushButton("Ouvrir…")
        self.btn_simulate = QPushButton("🎬  Simuler")
        self.btn_play = QPushButton("▶  Lancer")
        self.btn_pause = QPushButton("⏸  Pause")
        self.btn_stop = QPushButton("⏹  Stop")
        self.btn_reload = QPushButton("↻  Recharger")
        self.btn_history = QPushButton("📋  Historique")
        self.btn_history.setToolTip(
            "Ouvre l'historique des programmes lancés : "
            "date, durée, état, lignes, et ré-import en 1 clic."
        )
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
                  self.btn_pause, self.btn_stop, self.btn_reload, self.btn_history):
            b.setMinimumHeight(30)

        self.btn_open.clicked.connect(self._open)
        self.btn_simulate.clicked.connect(self.simulate_requested)
        self.btn_play.clicked.connect(self.play_requested)
        self.btn_pause.clicked.connect(self.pause_requested)
        self.btn_stop.clicked.connect(self.stop_requested)
        self.btn_reload.clicked.connect(self.reload_requested)
        self.btn_history.clicked.connect(self.history_requested)

        self.lbl_progress = QLabel("0 de 0")
        self.lbl_elapsed = QLabel("00:00:00")
        self.lbl_elapsed.setFont(QFont("Consolas", 10))

        # Estimation du programme (calculé à load)
        self.lbl_estimate = QLabel("")
        self.lbl_estimate.setStyleSheet(
            "color: #1f6feb; font-style: italic; padding: 4px 0;"
        )

        top = QHBoxLayout()
        top.addWidget(self.btn_open)
        top.addWidget(self.btn_simulate)
        top.addWidget(self.btn_play)
        top.addWidget(self.btn_pause)
        top.addWidget(self.btn_stop)
        top.addWidget(self.btn_reload)
        top.addWidget(self.btn_history)
        top.addStretch(1)

        info = QHBoxLayout()
        info.addWidget(QLabel("Suivre"))
        info.addWidget(self.lbl_progress)
        info.addStretch(1)
        info.addWidget(QLabel("Écoulé"))
        info.addWidget(self.lbl_elapsed)

        estimate_row = QHBoxLayout()
        estimate_row.addWidget(self.lbl_estimate)
        estimate_row.addStretch(1)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Sts", "Ligne", "Gcode"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        # IMPORTANT : col 0 (statut) en Fixed, pas ResizeToContents.
        # ResizeToContents recalcule la largeur sur TOUTES les lignes à
        # chaque modification de cellule → O(N²) pour reset_marks et
        # mark_line. Pour 1000 lignes = ~2.2 s de freeze.
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 44)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.setStyleSheet("QTableWidget { font-family: Consolas; font-size: 11px; }")

        v = QVBoxLayout(self)
        v.addLayout(top)
        v.addLayout(info)
        v.addLayout(estimate_row)
        v.addWidget(self.table, 1)

        self._lines: list[str] = []
        self._current_path: str = ""

        # Throttling : la table est mise à jour très souvent (chaque
        # ligne envoyée + chaque ack). On accumule les indices et on
        # rafraîchit l'écran à 10 Hz max via ce timer.
        self._pending_idx: int = -1
        self._highlighted_row: int = -1   # ligne actuellement surlignée
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(100)  # 10 Hz
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._do_refresh)

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
        self._populate_table(lines)
        self.lbl_progress.setText(f"0 de {len(lines)}")
        self.file_loaded.emit(path, list(lines))

    def _populate_table(self, lines: list[str]) -> None:
        """Remplit la table en bulk : updates désactivées + setRowCount unique
        (10× plus rapide que insertRow par ligne)."""
        self.table.setUpdatesEnabled(False)
        self.table.setSortingEnabled(False)
        try:
            self.table.clearContents()
            self.table.setRowCount(len(lines))
            for i, ln in enumerate(lines):
                # Colonne 0 : statut (vide au départ)
                it_status = QTableWidgetItem("")
                self.table.setItem(i, 0, it_status)
                # Colonne 1 : numéro de ligne
                it_line = QTableWidgetItem(str(i + 1))
                self.table.setItem(i, 1, it_line)
                # Colonne 2 : G-code
                it_gcode = QTableWidgetItem(ln)
                self.table.setItem(i, 2, it_gcode)
        finally:
            self.table.setUpdatesEnabled(True)
        # Reset le surlignage : la nouvelle table n'a aucune ligne active
        self._highlighted_row = -1
        self._pending_idx = -1
        self._refresh_timer.stop()

    def lines(self) -> list[str]:
        return list(self._lines)

    @Slot(int, str)
    def mark_line(self, idx_zero_based: int, status: str) -> None:
        """Marque la ligne avec un statut. La maj du label et du scroll sont
        throttlées à 10 Hz pour ne pas bloquer l'UI lors d'un streaming rapide.

        Cas spécial : sur le tout 1er mark_line après reset (aucune ligne
        surlignée), on fait un refresh IMMÉDIAT pour que le surlignage
        apparaisse à la première ligne plutôt que sauter au n°30+ après
        100ms de throttle (pendant lesquels le pump avale les commentaires)."""
        if idx_zero_based < 0 or idx_zero_based >= self.table.rowCount():
            return
        item = self.table.item(idx_zero_based, 0)
        if item is None:
            item = QTableWidgetItem(status)
            self.table.setItem(idx_zero_based, 0, item)
        else:
            item.setText(status)
        self._pending_idx = idx_zero_based
        if self._highlighted_row < 0:
            # Tout 1er mark après reset : refresh tout de suite pour que
            # l'utilisateur voie le surlignage commencer au début.
            self._do_refresh()
        elif not self._refresh_timer.isActive():
            self._refresh_timer.start()

    def _do_refresh(self) -> None:
        """Effectue le scroll + label + surlignage, appelé à 10 Hz max."""
        if self._pending_idx < 0:
            return
        idx = self._pending_idx
        self._pending_idx = -1
        if not (0 <= idx < self.table.rowCount()):
            return
        self.lbl_progress.setText(f"{idx + 1} de {len(self._lines)}")
        # Déplace le surlignage de l'ancienne ligne vers la nouvelle
        if self._highlighted_row != idx:
            if self._highlighted_row >= 0:
                self._set_row_brush(self._highlighted_row, _DEFAULT_BRUSH)
            self._set_row_brush(idx, _HIGHLIGHT_BRUSH)
            self._highlighted_row = idx
        # Auto-scroll pour garder la ligne visible
        item = self.table.item(idx, 0)
        if item is not None:
            self.table.scrollToItem(item)

    def _set_row_brush(self, row: int, brush: QBrush) -> None:
        """Applique un fond à toutes les cellules d'une ligne."""
        if row < 0 or row >= self.table.rowCount():
            return
        for col in range(self.table.columnCount()):
            it = self.table.item(row, col)
            if it is not None:
                it.setBackground(brush)

    def clear_active_highlight(self) -> None:
        """Efface le surlignage de la ligne courante (fin/abort/stop du job)."""
        if self._highlighted_row >= 0:
            self._set_row_brush(self._highlighted_row, _DEFAULT_BRUSH)
            self._highlighted_row = -1

    @Slot(str)
    def set_elapsed(self, hms: str) -> None:
        self.lbl_elapsed.setText(hms)

    def set_estimates(self, est: dict | None) -> None:
        """Affiche les estimations (durée, longueur, etc.) sous le panneau.
        `est` est un dict produit par gcode.parser.estimate_program."""
        if not est or est.get("n_moves", 0) == 0:
            self.lbl_estimate.setText("")
            return
        t = est["total_time_s"]
        h = int(t) // 3600
        m = (int(t) % 3600) // 60
        s = int(t) % 60
        if h > 0:
            time_str = f"{h}h {m:02d}min {s:02d}s"
        else:
            time_str = f"{m} min {s:02d} s"
        self.lbl_estimate.setText(
            f"⏱ ≈ {time_str}"
            f"   ·   📏 {est['total_length_mm']:.0f} mm trajet"
            f"   ·   🔥 {est['wire_length_mm']:.0f} mm fil chaud"
            f"   ·   {est['n_moves']} déplacements"
        )

    def append_status_message(self, msg: str) -> None:
        # Hook si plus tard on veut afficher des erreurs en pied de panneau.
        pass

    def reset_marks(self) -> None:
        """Efface tous les statuts + le surlignage. Bulk update pour vitesse."""
        self.table.setUpdatesEnabled(False)
        try:
            # Efface le surlignage avant tout (sinon il reste visible sur
            # la ligne précédente)
            if self._highlighted_row >= 0:
                self._set_row_brush(self._highlighted_row, _DEFAULT_BRUSH)
                self._highlighted_row = -1
            for row in range(self.table.rowCount()):
                it = self.table.item(row, 0)
                if it is not None and it.text():
                    it.setText("")
        finally:
            self.table.setUpdatesEnabled(True)
        self._pending_idx = -1
        self._refresh_timer.stop()
        self.lbl_progress.setText(f"0 de {len(self._lines)}")
