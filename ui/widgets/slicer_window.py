"""Fenêtre du slicer fil chaud : 2 profils -> G-code 4 axes.

Layout :
- Haut gauche  : profil emplanture (chargement + chord/offset/twist + kerf)
- Haut droit   : profil saumon (idem)
- Milieu gauche: géométrie bloc/fil (block_root_x, block_tip_x, wire_span)
- Milieu droit : paramètres de coupe (feed, S, leadin/leadout, n_points)
- Bas          : aperçu pyqtgraph + boutons (Aperçu / Sauver / Charger & Fermer)
"""

from __future__ import annotations

import os

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core import persistence
from gcode.profiles import Profile, kerf_offset, load_profile, resample, transform
from gcode.slicer import CutGeometry, CutParams, generate_gcode, project

from .airfoil_library import AirfoilLibraryDialog


class _ProfilePanel(QGroupBox):
    """Bloc de paramètres pour UN profil (emplanture ou saumon)."""

    changed = Signal()

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(title, parent)
        self.profile: Profile | None = None

        self.le_path = QLineEdit()
        self.le_path.setReadOnly(True)
        self.le_path.setPlaceholderText("Aucun fichier chargé")
        self.btn_load = QPushButton("Charger .dat…")
        self.btn_load.clicked.connect(self._load)

        self.sb_chord = QDoubleSpinBox()
        self.sb_chord.setRange(1, 5000)
        self.sb_chord.setValue(200.0)
        self.sb_chord.setSuffix(" mm")
        self.sb_chord.setDecimals(2)

        self.sb_offset_x = QDoubleSpinBox()
        self.sb_offset_x.setRange(-5000, 5000)
        self.sb_offset_x.setValue(0.0)
        self.sb_offset_x.setSuffix(" mm")

        self.sb_offset_y = QDoubleSpinBox()
        self.sb_offset_y.setRange(-5000, 5000)
        self.sb_offset_y.setValue(0.0)
        self.sb_offset_y.setSuffix(" mm")

        self.sb_twist = QDoubleSpinBox()
        self.sb_twist.setRange(-45, 45)
        self.sb_twist.setValue(0.0)
        self.sb_twist.setSuffix(" °")

        self.sb_kerf = QDoubleSpinBox()
        self.sb_kerf.setRange(-5, 5)
        self.sb_kerf.setSingleStep(0.05)
        self.sb_kerf.setDecimals(2)
        self.sb_kerf.setValue(0.0)
        self.sb_kerf.setSuffix(" mm")
        self.sb_kerf.setToolTip("Compensation du sillage du fil chaud (positif = profil agrandi).")

        for sb in (self.sb_chord, self.sb_offset_x, self.sb_offset_y, self.sb_twist, self.sb_kerf):
            sb.valueChanged.connect(self.changed)

        path_row = QHBoxLayout()
        path_row.addWidget(self.le_path, 1)
        path_row.addWidget(self.btn_load)

        form = QFormLayout()
        form.addRow("Corde :", self.sb_chord)
        form.addRow("Offset X :", self.sb_offset_x)
        form.addRow("Offset Y :", self.sb_offset_y)
        form.addRow("Twist :", self.sb_twist)
        form.addRow("Compensation fil :", self.sb_kerf)

        v = QVBoxLayout(self)
        v.addLayout(path_row)
        v.addLayout(form)

    def _load(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Charger un profil", "", "Profils (*.dat *.txt);;Tous (*)"
        )
        if not path:
            return
        self.load_from_path(path)

    def load_from_path(self, path: str) -> None:
        try:
            self.profile = load_profile(path)
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Lecture impossible : {e}")
            return
        self.le_path.setText(os.path.basename(path))
        self.changed.emit()

    def transformed(self) -> Profile | None:
        if self.profile is None:
            return None
        p = transform(
            self.profile,
            chord_mm=self.sb_chord.value(),
            offset_x=self.sb_offset_x.value(),
            offset_y=self.sb_offset_y.value(),
            twist_deg=self.sb_twist.value(),
        )
        if abs(self.sb_kerf.value()) > 1e-9:
            p = kerf_offset(p, self.sb_kerf.value())
        return p


class SlicerWindow(QDialog):
    gcode_generated = Signal(list)  # liste de lignes G-code

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Slicer fil chaud — 2 profils → 4 axes")
        self.resize(1280, 820)

        self.root_panel = _ProfilePanel("Profil emplanture (chariot gauche XY)")
        self.tip_panel = _ProfilePanel("Profil saumon (chariot droit ZA)")

        # Géométrie bloc/fil
        gb_geom = QGroupBox("Géométrie machine et bloc")
        self.sb_wire_span = QDoubleSpinBox()
        self.sb_wire_span.setRange(50, 5000)
        self.sb_wire_span.setValue(1000.0)
        self.sb_wire_span.setSuffix(" mm")
        self.sb_block_root = QDoubleSpinBox()
        self.sb_block_root.setRange(0, 5000)
        self.sb_block_root.setValue(150.0)
        self.sb_block_root.setSuffix(" mm")
        self.sb_block_tip = QDoubleSpinBox()
        self.sb_block_tip.setRange(0, 5000)
        self.sb_block_tip.setValue(850.0)
        self.sb_block_tip.setSuffix(" mm")
        for sb in (self.sb_wire_span, self.sb_block_root, self.sb_block_tip):
            sb.valueChanged.connect(self._update_preview)
        fg = QFormLayout(gb_geom)
        fg.addRow("Distance entre tours (L_fil) :", self.sb_wire_span)
        fg.addRow("Tour gauche → face emplanture :", self.sb_block_root)
        fg.addRow("Tour gauche → face saumon :", self.sb_block_tip)

        # Paramètres de coupe
        gb_cut = QGroupBox("Paramètres de coupe")
        self.sb_feed = QDoubleSpinBox()
        self.sb_feed.setRange(1, 5000)
        self.sb_feed.setValue(200.0)
        self.sb_feed.setSuffix(" mm/min")
        self.sb_s = QSpinBox()
        self.sb_s.setRange(0, 100000)
        self.sb_s.setValue(500)
        self.sb_leadin = QDoubleSpinBox()
        self.sb_leadin.setRange(0, 200)
        self.sb_leadin.setValue(20.0)
        self.sb_leadin.setSuffix(" mm")
        self.sb_leadout = QDoubleSpinBox()
        self.sb_leadout.setRange(0, 200)
        self.sb_leadout.setValue(20.0)
        self.sb_leadout.setSuffix(" mm")
        self.sb_n = QSpinBox()
        self.sb_n.setRange(20, 2000)
        self.sb_n.setValue(200)
        self.sb_safe_y = QDoubleSpinBox()
        self.sb_safe_y.setRange(0, 5000)
        self.sb_safe_y.setValue(80.0)
        self.sb_safe_y.setSuffix(" mm")
        for sb in (
            self.sb_feed, self.sb_s, self.sb_leadin, self.sb_leadout,
            self.sb_n, self.sb_safe_y,
        ):
            sb.valueChanged.connect(self._update_preview)
        fc = QFormLayout(gb_cut)
        fc.addRow("Avance de coupe :", self.sb_feed)
        fc.addRow("S (puissance fil) :", self.sb_s)
        fc.addRow("Lead-in (entrée) :", self.sb_leadin)
        fc.addRow("Lead-out (sortie) :", self.sb_leadout)
        fc.addRow("Nb points par profil :", self.sb_n)
        fc.addRow("Y sécurité retour :", self.sb_safe_y)

        # Aperçu
        self.plot = pg.PlotWidget()
        self.plot.setBackground("w")
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.setAspectLocked(True)
        self.plot.setLabel("bottom", "X (mm)")
        self.plot.setLabel("left", "Y (mm)")
        self._curve_root = self.plot.plot([], [], pen=pg.mkPen("b", width=2), name="emplanture")
        self._curve_tip = self.plot.plot([], [], pen=pg.mkPen("r", width=2), name="saumon")
        self._curve_left = self.plot.plot([], [], pen=pg.mkPen((0, 120, 255, 120), width=1, style=Qt.DashLine))
        self._curve_right = self.plot.plot([], [], pen=pg.mkPen((255, 60, 60, 120), width=1, style=Qt.DashLine))

        # Boutons d'action
        self.btn_library = QPushButton("📚  Bibliothèque (2383 profils)")
        self.btn_library.setProperty("variant", "primary")
        self.btn_library.setMinimumHeight(34)
        self.btn_library.setToolTip(
            "Parcourir la bibliothèque Profili 2 Pro et charger un profil "
            "comme emplanture ou saumon"
        )
        self.btn_library.clicked.connect(self._open_library)

        self.btn_preview = QPushButton("Rafraîchir l'aperçu")
        self.btn_save = QPushButton("Générer & sauver…")
        self.btn_load_in_app = QPushButton("Générer & charger dans l'app")
        self.btn_close = QPushButton("Fermer")
        for b in (self.btn_preview, self.btn_save, self.btn_load_in_app, self.btn_close):
            b.setMinimumHeight(34)
        self.btn_preview.clicked.connect(self._update_preview)
        self.btn_save.clicked.connect(self._save_gcode)
        self.btn_load_in_app.clicked.connect(self._load_in_app)
        self.btn_close.clicked.connect(self.close)
        self.root_panel.changed.connect(self._update_preview)
        self.tip_panel.changed.connect(self._update_preview)

        # Layout global
        top = QGridLayout()
        top.addWidget(self.root_panel, 0, 0)
        top.addWidget(self.tip_panel, 0, 1)
        top.addWidget(gb_geom, 1, 0)
        top.addWidget(gb_cut, 1, 1)

        actions = QHBoxLayout()
        actions.addWidget(self.btn_library)
        actions.addWidget(self.btn_preview)
        actions.addStretch(1)
        actions.addWidget(self.btn_save)
        actions.addWidget(self.btn_load_in_app)
        actions.addWidget(self.btn_close)

        outer = QVBoxLayout(self)
        outer.addLayout(top)
        outer.addWidget(self.plot, 1)
        outer.addLayout(actions)

        self._load_persisted()


    # ---- Logic ----

    def _update_preview(self) -> None:
        root = self.root_panel.transformed()
        tip = self.tip_panel.transformed()
        if root is None or tip is None:
            self._curve_root.setData([], [])
            self._curve_tip.setData([], [])
            self._curve_left.setData([], [])
            self._curve_right.setData([], [])
            return
        rx = [p[0] for p in root.points]
        ry = [p[1] for p in root.points]
        tx = [p[0] for p in tip.points]
        ty = [p[1] for p in tip.points]
        self._curve_root.setData(rx, ry)
        self._curve_tip.setData(tx, ty)

        # Aperçu projection chariots
        try:
            n = self.sb_n.value()
            rs = resample(root, n)
            ts = resample(tip, n)
            geom = CutGeometry(
                wire_span=self.sb_wire_span.value(),
                block_root_x=self.sb_block_root.value(),
                block_tip_x=self.sb_block_tip.value(),
            )
            pts = project(rs, ts, geom)
            lx = [p[0] for p in pts]
            ly = [p[1] for p in pts]
            zx = [p[2] for p in pts]
            za = [p[3] for p in pts]
            self._curve_left.setData(lx, ly)
            self._curve_right.setData(zx, za)
        except Exception:
            self._curve_left.setData([], [])
            self._curve_right.setData([], [])

        self.plot.autoRange()

    def _build_gcode(self) -> list[str] | None:
        root = self.root_panel.transformed()
        tip = self.tip_panel.transformed()
        if root is None or tip is None:
            QMessageBox.warning(self, "Profils manquants",
                                "Charge un profil emplanture ET un profil saumon avant de générer.")
            return None
        try:
            geom = CutGeometry(
                wire_span=self.sb_wire_span.value(),
                block_root_x=self.sb_block_root.value(),
                block_tip_x=self.sb_block_tip.value(),
            )
            params = CutParams(
                feed=self.sb_feed.value(),
                hot_wire_s=self.sb_s.value(),
                leadin_mm=self.sb_leadin.value(),
                leadout_mm=self.sb_leadout.value(),
                n_resample=self.sb_n.value(),
                safe_y=self.sb_safe_y.value(),
            )
            return generate_gcode(root, tip, geom, params)
        except Exception as e:
            QMessageBox.critical(self, "Erreur génération", str(e))
            return None

    def _save_gcode(self) -> None:
        lines = self._build_gcode()
        if lines is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Sauver le G-code", "decoupe.gcode",
            "G-code (*.gcode *.nc *.tap *.ngc);;Tous (*)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
                f.write("\n")
        except OSError as e:
            QMessageBox.critical(self, "Erreur", f"Écriture impossible : {e}")
            return
        QMessageBox.information(self, "OK", f"G-code écrit : {len(lines)} lignes")

    def _load_in_app(self) -> None:
        lines = self._build_gcode()
        if lines is None:
            return
        self.gcode_generated.emit(lines)
        self.close()

    def _open_library(self) -> None:
        dlg = AirfoilLibraryDialog(self)
        dlg.profile_selected.connect(self._on_library_pick)
        dlg.exec()

    def _on_library_pick(self, side: str, path: str) -> None:
        panel = self.root_panel if side == "root" else self.tip_panel
        panel.load_from_path(path)

    # ---- Persistance ----

    _PERSIST_FIELDS = (
        # (key, widget_attr, kind)
        ("slicer/wire_span", "sb_wire_span", "f"),
        ("slicer/block_root_x", "sb_block_root", "f"),
        ("slicer/block_tip_x", "sb_block_tip", "f"),
        ("slicer/feed", "sb_feed", "f"),
        ("slicer/hot_wire_s", "sb_s", "i"),
        ("slicer/leadin", "sb_leadin", "f"),
        ("slicer/leadout", "sb_leadout", "f"),
        ("slicer/n_resample", "sb_n", "i"),
        ("slicer/safe_y", "sb_safe_y", "f"),
    )

    _PERSIST_PROFILE_FIELDS = (
        ("chord", "sb_chord", "f"),
        ("offset_x", "sb_offset_x", "f"),
        ("offset_y", "sb_offset_y", "f"),
        ("twist", "sb_twist", "f"),
        ("kerf", "sb_kerf", "f"),
    )

    def _load_persisted(self) -> None:
        for key, attr, kind in self._PERSIST_FIELDS:
            sb = getattr(self, attr)
            if kind == "f":
                v = persistence.get_float(key, sb.value())
                sb.setValue(v)
            else:
                sb.setValue(persistence.get_int(key, sb.value()))
        for prefix, panel in (("slicer/root", self.root_panel), ("slicer/tip", self.tip_panel)):
            for sub, attr, _ in self._PERSIST_PROFILE_FIELDS:
                sb = getattr(panel, attr)
                sb.setValue(persistence.get_float(f"{prefix}/{sub}", sb.value()))

    def _save_persisted(self) -> None:
        for key, attr, _ in self._PERSIST_FIELDS:
            persistence.set_(key, getattr(self, attr).value())
        for prefix, panel in (("slicer/root", self.root_panel), ("slicer/tip", self.tip_panel)):
            for sub, attr, _ in self._PERSIST_PROFILE_FIELDS:
                persistence.set_(f"{prefix}/{sub}", getattr(panel, attr).value())

    def closeEvent(self, event) -> None:
        self._save_persisted()
        super().closeEvent(event)
