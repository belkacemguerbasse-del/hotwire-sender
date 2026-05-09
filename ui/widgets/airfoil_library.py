"""Dialog « Bibliothèque de profils ».

Affiche les 2383 profils extraits de Profili 2 Pro avec :
- recherche par nom
- filtres par épaisseur min/max et cambrure min/max
- aperçu live du profil sélectionné
- métadonnées (épaisseur %, position max épaisseur, cambrure %)
- 1 bouton d'action générique « Sélectionner ce profil »

Le dialog renvoie le chemin du fichier .dat sélectionné via le signal
`profile_selected(file_path)`. L'appelant décide quoi en faire (emplanture,
saumon, section N, etc.).
"""

from __future__ import annotations

import json
from pathlib import Path

import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from gcode.profiles import load_profile

INDEX_PATH = Path(__file__).resolve().parent.parent.parent / "resources" / "airfoils" / "_index.json"


class AirfoilLibraryDialog(QDialog):
    """Dialog autonome de sélection de profil. Émet `profile_selected(file_path)`."""

    profile_selected = Signal(str)  # file_path

    def __init__(self, button_label: str = "Sélectionner ce profil",
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._button_label = button_label
        self.setWindowTitle("Bibliothèque de profils — Profili 2 Pro")
        self.resize(1100, 720)

        self._all: list[dict] = []
        self._filtered: list[dict] = []
        self._load_index()

        # --- Filtres ---
        gb_filter = QGroupBox("Filtres")
        self.le_search = QLineEdit()
        self.le_search.setPlaceholderText("Rechercher par nom (ex: NACA 0012)…")
        self.le_search.textChanged.connect(self._refilter)

        self.sb_th_min = QDoubleSpinBox()
        self.sb_th_min.setRange(0, 30)
        self.sb_th_min.setSuffix(" %")
        self.sb_th_min.setValue(0)
        self.sb_th_max = QDoubleSpinBox()
        self.sb_th_max.setRange(0, 30)
        self.sb_th_max.setSuffix(" %")
        self.sb_th_max.setValue(30)
        self.sb_cb_min = QDoubleSpinBox()
        self.sb_cb_min.setRange(0, 15)
        self.sb_cb_min.setSuffix(" %")
        self.sb_cb_min.setValue(0)
        self.sb_cb_max = QDoubleSpinBox()
        self.sb_cb_max.setRange(0, 15)
        self.sb_cb_max.setSuffix(" %")
        self.sb_cb_max.setValue(15)
        for sb in (self.sb_th_min, self.sb_th_max, self.sb_cb_min, self.sb_cb_max):
            sb.valueChanged.connect(self._refilter)

        f = QFormLayout(gb_filter)
        f.addRow("Recherche :", self.le_search)
        row_th = QHBoxLayout()
        row_th.addWidget(self.sb_th_min)
        row_th.addWidget(QLabel("→"))
        row_th.addWidget(self.sb_th_max)
        f.addRow("Épaisseur :", row_th)
        row_cb = QHBoxLayout()
        row_cb.addWidget(self.sb_cb_min)
        row_cb.addWidget(QLabel("→"))
        row_cb.addWidget(self.sb_cb_max)
        f.addRow("Cambrure :", row_cb)

        # --- Liste ---
        self.list_w = QListWidget()
        self.list_w.setUniformItemSizes(True)
        self.list_w.currentItemChanged.connect(self._on_selection_changed)

        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet("color: #637381; font-style: italic;")

        left = QWidget()
        v_left = QVBoxLayout(left)
        v_left.setContentsMargins(0, 0, 0, 0)
        v_left.addWidget(gb_filter)
        v_left.addWidget(self.lbl_count)
        v_left.addWidget(self.list_w, 1)

        # --- Aperçu ---
        gb_preview = QGroupBox("Aperçu")
        self.plot = pg.PlotWidget()
        self.plot.setBackground("w")
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.setAspectLocked(True)
        self.plot.setLabel("bottom", "x / corde")
        self.plot.setLabel("left", "y / corde")
        self._curve = self.plot.plot([], [], pen=pg.mkPen("#1f6feb", width=2))

        # Métadonnées
        self.lbl_name = QLabel("—")
        self.lbl_name.setFont(QFont("", 14, QFont.Bold))
        self.lbl_meta = QLabel("")
        self.lbl_meta.setStyleSheet("color: #637381;")
        self.lbl_note = QLabel("")
        self.lbl_note.setWordWrap(True)
        self.lbl_note.setStyleSheet("color: #1f2933;")

        v_prev = QVBoxLayout(gb_preview)
        v_prev.addWidget(self.lbl_name)
        v_prev.addWidget(self.lbl_meta)
        v_prev.addWidget(self.plot, 1)
        v_prev.addWidget(self.lbl_note)

        # --- Bouton d'action générique ---
        self.btn_select = QPushButton(self._button_label)
        self.btn_select.setProperty("variant", "primary")
        self.btn_select.setMinimumHeight(36)
        self.btn_select.setMinimumWidth(220)
        self.btn_select.clicked.connect(self._emit_choice)

        self.btn_close = QPushButton("Annuler")
        self.btn_close.setMinimumHeight(36)
        self.btn_close.clicked.connect(self.close)

        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(self.btn_select)
        actions.addWidget(self.btn_close)

        # --- Splitter principal ---
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(gb_preview)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([400, 700])

        outer = QVBoxLayout(self)
        outer.addWidget(splitter, 1)
        outer.addLayout(actions)

        self._refilter()

    # ---- Données ----

    def _load_index(self) -> None:
        if not INDEX_PATH.exists():
            self._all = []
            return
        try:
            with open(INDEX_PATH, encoding="utf-8") as f:
                data = json.load(f)
            self._all = data.get("profiles", [])
        except Exception:
            self._all = []

    # ---- Filtre ----

    def _refilter(self) -> None:
        q = self.le_search.text().strip().lower()
        th_min = self.sb_th_min.value()
        th_max = self.sb_th_max.value()
        cb_min = self.sb_cb_min.value()
        cb_max = self.sb_cb_max.value()

        out = []
        for p in self._all:
            if q and q not in p["nome"].lower():
                continue
            tw = p.get("max_width_pct") or 0.0
            cb = p.get("max_camber_pct") or 0.0
            # max_camber peut être stocké quasi-zéro avec exposant (e-19) -> on
            # arrondit pour le filtrage
            cb = abs(cb) if abs(cb) > 1e-6 else 0.0
            if not (th_min <= tw <= th_max):
                continue
            if not (cb_min <= cb <= cb_max):
                continue
            out.append(p)
        self._filtered = out

        self.list_w.clear()
        for p in out:
            tw = p.get("max_width_pct") or 0.0
            it = QListWidgetItem(f"{p['nome']}   ({tw:.1f}%)")
            it.setData(Qt.UserRole, p)
            self.list_w.addItem(it)

        self.lbl_count.setText(
            f"{len(out)} profil(s) sur {len(self._all)} affiché(s)"
        )

    # ---- Sélection ----

    def _on_selection_changed(self, item: QListWidgetItem | None, _prev) -> None:
        if item is None:
            self._curve.setData([], [])
            self.lbl_name.setText("—")
            self.lbl_meta.setText("")
            self.lbl_note.setText("")
            return
        p = item.data(Qt.UserRole)
        self.lbl_name.setText(p["nome"])
        tw = p.get("max_width_pct") or 0.0
        twp = p.get("max_width_pos") or 0.0
        cb = p.get("max_camber_pct") or 0.0
        cbp = p.get("max_camber_pos") or 0.0
        cb = abs(cb) if abs(cb) > 1e-6 else 0.0
        self.lbl_meta.setText(
            f"Épaisseur max : {tw:.2f} % à {twp:.1f} % de la corde · "
            f"Cambrure max : {cb:.2f} % à {cbp:.1f} % de la corde"
        )
        self.lbl_note.setText(p.get("note") or "")

        # Charge et affiche le profil
        path = self._path_of(p)
        try:
            prof = load_profile(str(path))
            xs = [pt[0] for pt in prof.points]
            ys = [pt[1] for pt in prof.points]
            self._curve.setData(xs, ys)
            self.plot.autoRange()
        except Exception as e:
            self._curve.setData([], [])
            self.lbl_note.setText(f"Erreur de chargement : {e}")

    def _path_of(self, profile: dict) -> Path:
        return INDEX_PATH.parent / profile["file"]

    def _emit_choice(self) -> None:
        item = self.list_w.currentItem()
        if item is None:
            return
        p = item.data(Qt.UserRole)
        self.profile_selected.emit(str(self._path_of(p)))
        self.accept()
