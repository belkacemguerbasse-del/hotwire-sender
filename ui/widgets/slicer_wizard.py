"""Wizard de slicing inspiré de Profili 2 Pro.

Fenêtre QWizard en 8 étapes guidées :
    1. Données du panneau (corde, longueur, incidence, swept-back)
    2. Sélection des profils (emplanture + saumon)
    3. Coffrage (sheeting) et kerf
    4. Longerons (spars) — placeholder, Step 2
    5. Trous d'allègement (lightening holes) — placeholder, Step 2
    6. Placement du bloc de mousse
    7. Coupe LE / TE séparée — placeholder, Step 3
    8. Simulation et export

Le wizard ne remplace pas la fenêtre slicer historique (qui reste pour le
mode multi-panneaux et l'édition avancée). Il offre un workflow guidé
pour la coupe d'un panneau type planeur à la Profili.

Émet `gcode_generated(list[str])` à la fin pour que la fenêtre principale
le charge dans le GcodePanel.
"""

from __future__ import annotations

from pathlib import Path

import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from gcode.profiles import Profile, load_profile, resample
from gcode.slicer import CutGeometry, CutParams, generate_gcode_wing
from gcode.spars import LighteningHole, Spar
from gcode.wing import Section, WingDefinition

from .airfoil_library import AirfoilLibraryDialog


# Chaque page utilise self.wizard().shared pour partager l'état.
class _Shared:
    """Conteneur d'état partagé entre toutes les pages."""

    def __init__(self) -> None:
        # Panel info
        self.panel_name: str = ""
        self.panel_description: str = ""
        self.panel_length_mm: float = 1000.0
        self.root_chord_mm: float = 350.0
        self.tip_chord_mm: float = 200.0
        self.root_incidence_deg: float = 0.0
        self.tip_incidence_deg: float = 0.0
        self.swept_back_mm: float = 25.0

        # Airfoils
        self.root_profile_path: str = ""
        self.tip_profile_path: str = ""
        self.invert_airfoils: bool = False

        # Sheeting + kerf
        self.sheeting_upper_mm: float = 0.0
        self.sheeting_lower_mm: float = 0.0
        self.te_extend_mm: float = 10.0
        self.use_differential_kerf: bool = False
        self.kerf_root_mm: float = 1.0
        self.kerf_tip_mm: float = 1.0

        # Spars + lightening holes
        self.spars: list[Spar] = []
        self.lightening_holes: list[LighteningHole] = []

        # Block placement
        self.wire_span_mm: float = 1000.0
        self.block_thickness_mm: float = 50.0
        self.height_root_mm: float = 25.0
        self.height_tip_mm: float = 25.0
        self.distance_root_mm: float = 0.0
        self.distance_tip_mm: float = 0.0

        # Cut params
        self.feed: float = 200.0
        self.hot_wire_s: int = 500
        self.leadin_mm: float = 20.0
        self.leadout_mm: float = 20.0
        self.n_resample: int = 200


# ----------------------------------------------------------------------
# Page 1 — Panel general
# ----------------------------------------------------------------------

class _PanelInfoPage(QWizardPage):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setTitle("1. Données générales et plan du panneau")
        self.setSubTitle(
            "Définis les dimensions principales du panneau et l'angle "
            "d'incidence aux deux extrémités."
        )

        self.le_name = QLineEdit()
        self.le_name.setPlaceholderText("ex. aile_droite_panneau1")
        self.le_description = QLineEdit()
        self.le_description.setPlaceholderText("Description libre (optionnel)")

        self.sb_length = self._mk_spin(50, 5000, 1000.0, " mm")
        self.sb_root_chord = self._mk_spin(20, 2000, 350.0, " mm")
        self.sb_tip_chord = self._mk_spin(20, 2000, 200.0, " mm")
        self.sb_root_incid = self._mk_spin(-15, 15, 0.0, " °", decimals=2)
        self.sb_tip_incid = self._mk_spin(-15, 15, 0.0, " °", decimals=2)
        self.sb_sweep = self._mk_spin(-500, 500, 25.0, " mm")

        form = QFormLayout()
        form.addRow("Nom du panneau :", self.le_name)
        form.addRow("Description :", self.le_description)
        form.addRow("Longueur :", self.sb_length)
        form.addRow("Corde emplanture :", self.sb_root_chord)
        form.addRow("Corde saumon :", self.sb_tip_chord)
        form.addRow("Incidence emplanture :", self.sb_root_incid)
        form.addRow("Incidence saumon :", self.sb_tip_incid)
        form.addRow("Flèche bord d'attaque :", self.sb_sweep)

        # Aperçu en plan
        self.plot = pg.PlotWidget(background="w")
        self.plot.setAspectLocked(True)
        self.plot.showGrid(x=True, y=True, alpha=0.2)
        self.plot.setMinimumHeight(180)

        v = QVBoxLayout(self)
        v.addLayout(form)
        v.addWidget(QLabel("Aperçu plan :"))
        v.addWidget(self.plot, 1)

        for w in (
            self.sb_length, self.sb_root_chord, self.sb_tip_chord,
            self.sb_sweep,
        ):
            w.valueChanged.connect(self._refresh_plot)

    @staticmethod
    def _mk_spin(mn, mx, val, suffix, decimals=1) -> QDoubleSpinBox:
        sb = QDoubleSpinBox()
        sb.setRange(mn, mx)
        sb.setValue(val)
        sb.setSuffix(suffix)
        sb.setDecimals(decimals)
        return sb

    def initializePage(self) -> None:
        s = self.wizard().shared
        self.le_name.setText(s.panel_name)
        self.le_description.setText(s.panel_description)
        self.sb_length.setValue(s.panel_length_mm)
        self.sb_root_chord.setValue(s.root_chord_mm)
        self.sb_tip_chord.setValue(s.tip_chord_mm)
        self.sb_root_incid.setValue(s.root_incidence_deg)
        self.sb_tip_incid.setValue(s.tip_incidence_deg)
        self.sb_sweep.setValue(s.swept_back_mm)
        self._refresh_plot()

    def _refresh_plot(self) -> None:
        L = self.sb_length.value()
        cR = self.sb_root_chord.value()
        cT = self.sb_tip_chord.value()
        sw = self.sb_sweep.value()
        # Plan : x = corde, y = envergure (vue de dessus)
        xs = [0, cR, sw + cT, sw, 0]
        ys = [0, 0, L, L, 0]
        self.plot.clear()
        self.plot.plot(xs, ys, pen=pg.mkPen("#1f6feb", width=2))

    def validatePage(self) -> bool:
        s = self.wizard().shared
        s.panel_name = self.le_name.text().strip()
        s.panel_description = self.le_description.text().strip()
        s.panel_length_mm = self.sb_length.value()
        s.root_chord_mm = self.sb_root_chord.value()
        s.tip_chord_mm = self.sb_tip_chord.value()
        s.root_incidence_deg = self.sb_root_incid.value()
        s.tip_incidence_deg = self.sb_tip_incid.value()
        s.swept_back_mm = self.sb_sweep.value()
        return True


# ----------------------------------------------------------------------
# Page 2 — Airfoils
# ----------------------------------------------------------------------

class _AirfoilPage(QWizardPage):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setTitle("2. Sélection des profils")
        self.setSubTitle("Choisis les profils d'aile pour l'emplanture et le saumon.")

        # Root
        gb_root = QGroupBox("Profil emplanture (root)")
        self.lbl_root = QLabel("(aucun)")
        self.lbl_root.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.btn_root_lib = QPushButton("📚 Bibliothèque…")
        self.btn_root_file = QPushButton("📁 Fichier .dat…")
        hr = QHBoxLayout()
        hr.addWidget(self.btn_root_lib)
        hr.addWidget(self.btn_root_file)
        vr = QVBoxLayout(gb_root)
        vr.addWidget(self.lbl_root)
        vr.addLayout(hr)

        # Tip
        gb_tip = QGroupBox("Profil saumon (tip)")
        self.lbl_tip = QLabel("(aucun)")
        self.lbl_tip.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.btn_tip_lib = QPushButton("📚 Bibliothèque…")
        self.btn_tip_file = QPushButton("📁 Fichier .dat…")
        self.btn_tip_copy_root = QPushButton("= emplanture")
        ht = QHBoxLayout()
        ht.addWidget(self.btn_tip_lib)
        ht.addWidget(self.btn_tip_file)
        ht.addWidget(self.btn_tip_copy_root)
        vt = QVBoxLayout(gb_tip)
        vt.addWidget(self.lbl_tip)
        vt.addLayout(ht)

        self.cb_invert = QCheckBox("Inverser extrados/intrados (couper avec extrados en bas)")

        # Aperçu
        self.plot = pg.PlotWidget(background="w")
        self.plot.setAspectLocked(True)
        self.plot.showGrid(x=True, y=True, alpha=0.2)
        self.plot.setMinimumHeight(220)

        v = QVBoxLayout(self)
        v.addWidget(gb_root)
        v.addWidget(gb_tip)
        v.addWidget(self.cb_invert)
        v.addWidget(QLabel("Aperçu profils (rouge = root, bleu = tip) :"))
        v.addWidget(self.plot, 1)

        self.btn_root_lib.clicked.connect(lambda: self._pick_from_library("root"))
        self.btn_tip_lib.clicked.connect(lambda: self._pick_from_library("tip"))
        self.btn_root_file.clicked.connect(lambda: self._pick_from_file("root"))
        self.btn_tip_file.clicked.connect(lambda: self._pick_from_file("tip"))
        self.btn_tip_copy_root.clicked.connect(self._tip_same_as_root)

    def initializePage(self) -> None:
        s = self.wizard().shared
        self._set_root(s.root_profile_path)
        self._set_tip(s.tip_profile_path)
        self.cb_invert.setChecked(s.invert_airfoils)

    def _pick_from_library(self, slot: str) -> None:
        dlg = AirfoilLibraryDialog(parent=self)
        def _on_pick(path: str):
            if slot == "root":
                self._set_root(path)
            else:
                self._set_tip(path)
            dlg.accept()
        dlg.profile_selected.connect(_on_pick)
        dlg.exec()

    def _pick_from_file(self, slot: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir un profil .dat", "",
            "Profils Selig (*.dat);;Tous (*)",
        )
        if not path:
            return
        if slot == "root":
            self._set_root(path)
        else:
            self._set_tip(path)

    def _tip_same_as_root(self) -> None:
        if self.wizard().shared.root_profile_path:
            self._set_tip(self.wizard().shared.root_profile_path)

    def _set_root(self, path: str) -> None:
        s = self.wizard().shared
        s.root_profile_path = path
        self.lbl_root.setText(Path(path).stem if path else "(aucun)")
        self._refresh_plot()
        self.completeChanged.emit()

    def _set_tip(self, path: str) -> None:
        s = self.wizard().shared
        s.tip_profile_path = path
        self.lbl_tip.setText(Path(path).stem if path else "(aucun)")
        self._refresh_plot()
        self.completeChanged.emit()

    def _refresh_plot(self) -> None:
        self.plot.clear()
        s = self.wizard().shared
        for path, color in ((s.root_profile_path, "#d12c2c"),
                            (s.tip_profile_path, "#1f6feb")):
            if not path:
                continue
            try:
                p = load_profile(path)
                xs = [pt[0] for pt in p.points]
                ys = [pt[1] for pt in p.points]
                self.plot.plot(xs, ys, pen=pg.mkPen(color, width=2))
            except Exception:
                pass

    def isComplete(self) -> bool:
        s = self.wizard().shared
        return bool(s.root_profile_path and s.tip_profile_path)

    def validatePage(self) -> bool:
        self.wizard().shared.invert_airfoils = self.cb_invert.isChecked()
        return True


# ----------------------------------------------------------------------
# Page 3 — Sheeting + Kerf
# ----------------------------------------------------------------------

class _SheetingKerfPage(QWizardPage):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setTitle("3. Coffrage (sheeting) et kerf")
        self.setSubTitle(
            "Coffrage = épaisseur balsa/fibre à pré-soustraire du profil. "
            "Kerf = épaisseur de mousse mangée par le fil chaud."
        )

        # Sheeting
        gb_sheet = QGroupBox("Coffrage (sheeting)")
        self.cb_sheet_upper = QCheckBox("Coffrage extrados, épaisseur =")
        self.sb_sheet_upper = self._mk_spin(0.0, 10.0, 2.0)
        self.cb_sheet_lower = QCheckBox("Coffrage intrados, épaisseur =")
        self.sb_sheet_lower = self._mk_spin(0.0, 10.0, 2.0)
        self.cb_sheet_upper.toggled.connect(self.sb_sheet_upper.setEnabled)
        self.cb_sheet_lower.toggled.connect(self.sb_sheet_lower.setEnabled)
        self.sb_sheet_upper.setEnabled(False)
        self.sb_sheet_lower.setEnabled(False)

        u = QHBoxLayout()
        u.addWidget(self.cb_sheet_upper)
        u.addWidget(self.sb_sheet_upper)
        u.addStretch(1)
        d = QHBoxLayout()
        d.addWidget(self.cb_sheet_lower)
        d.addWidget(self.sb_sheet_lower)
        d.addStretch(1)
        vs = QVBoxLayout(gb_sheet)
        vs.addLayout(u)
        vs.addLayout(d)

        # TE extension
        self.sb_te = self._mk_spin(0.0, 50.0, 10.0)
        gb_te = QGroupBox("Allongement tangentiel du bord de fuite")
        ft = QFormLayout(gb_te)
        ft.addRow("Longueur ajoutée :", self.sb_te)

        # Kerf
        gb_kerf = QGroupBox("Kerf (épaisseur de mousse mangée par le fil)")
        self.cb_use_diff = QCheckBox("Utiliser un kerf différencié root / tip")
        self.sb_kerf_root = self._mk_spin(0.0, 5.0, 1.0)
        self.sb_kerf_tip = self._mk_spin(0.0, 5.0, 1.0)
        fk = QFormLayout()
        fk.addRow("Kerf emplanture :", self.sb_kerf_root)
        fk.addRow("Kerf saumon :", self.sb_kerf_tip)
        vk = QVBoxLayout(gb_kerf)
        vk.addWidget(self.cb_use_diff)
        vk.addLayout(fk)

        v = QVBoxLayout(self)
        v.addWidget(gb_sheet)
        v.addWidget(gb_te)
        v.addWidget(gb_kerf)
        v.addStretch(1)

    @staticmethod
    def _mk_spin(mn, mx, val) -> QDoubleSpinBox:
        sb = QDoubleSpinBox()
        sb.setRange(mn, mx)
        sb.setValue(val)
        sb.setSuffix(" mm")
        sb.setDecimals(2)
        return sb

    def initializePage(self) -> None:
        s = self.wizard().shared
        self.cb_sheet_upper.setChecked(s.sheeting_upper_mm > 0)
        self.sb_sheet_upper.setValue(s.sheeting_upper_mm or 2.0)
        self.cb_sheet_lower.setChecked(s.sheeting_lower_mm > 0)
        self.sb_sheet_lower.setValue(s.sheeting_lower_mm or 2.0)
        self.sb_te.setValue(s.te_extend_mm)
        self.cb_use_diff.setChecked(s.use_differential_kerf)
        self.sb_kerf_root.setValue(s.kerf_root_mm)
        self.sb_kerf_tip.setValue(s.kerf_tip_mm)

    def validatePage(self) -> bool:
        s = self.wizard().shared
        s.sheeting_upper_mm = self.sb_sheet_upper.value() if self.cb_sheet_upper.isChecked() else 0.0
        s.sheeting_lower_mm = self.sb_sheet_lower.value() if self.cb_sheet_lower.isChecked() else 0.0
        s.te_extend_mm = self.sb_te.value()
        s.use_differential_kerf = self.cb_use_diff.isChecked()
        s.kerf_root_mm = self.sb_kerf_root.value()
        s.kerf_tip_mm = self.sb_kerf_tip.value()
        return True


# ----------------------------------------------------------------------
# Page 4 — Spars (Step 2)
# ----------------------------------------------------------------------

class _SparsPage(QWizardPage):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setTitle("4. Longerons (spars)")
        self.setSubTitle(
            "Encoches rectangulaires dans le profil pour le passage des "
            "longerons. Position en mm depuis le bord d'attaque."
        )

        self._suppress_form_sync = False

        # Liste
        self.lst = QListWidget()
        self.btn_add = QPushButton("➕  Ajouter")
        self.btn_del = QPushButton("🗑  Supprimer")
        self.btn_del.setEnabled(False)
        side_actions = QHBoxLayout()
        side_actions.addWidget(self.btn_add)
        side_actions.addWidget(self.btn_del)
        side_actions.addStretch(1)
        side = QVBoxLayout()
        side.addWidget(QLabel("Liste des longerons :"))
        side.addWidget(self.lst, 1)
        side.addLayout(side_actions)
        side_widget = QWidget()
        side_widget.setLayout(side)

        # Form
        self.le_name = QLineEdit()
        self.le_name.setPlaceholderText("nom optionnel")
        self.cb_surface = QComboBox()
        self.cb_surface.addItem("Extrados (upper)", "upper")
        self.cb_surface.addItem("Intrados (lower)", "lower")

        self.sb_x_root = self._mk_spin(0, 1000, 30.0, " mm")
        self.sb_x_tip = self._mk_spin(0, 1000, 30.0, " mm")
        self.sb_w_root = self._mk_spin(0.5, 50, 8.0, " mm", decimals=2)
        self.sb_w_tip = self._mk_spin(0.5, 50, 8.0, " mm", decimals=2)
        self.sb_d_root = self._mk_spin(0.5, 50, 5.0, " mm", decimals=2)
        self.sb_d_tip = self._mk_spin(0.5, 50, 5.0, " mm", decimals=2)

        form = QFormLayout()
        form.addRow("Nom :", self.le_name)
        form.addRow("Surface :", self.cb_surface)
        form.addRow("X emplanture :", self.sb_x_root)
        form.addRow("X saumon :", self.sb_x_tip)
        form.addRow("Largeur emplanture :", self.sb_w_root)
        form.addRow("Largeur saumon :", self.sb_w_tip)
        form.addRow("Profondeur emplanture :", self.sb_d_root)
        form.addRow("Profondeur saumon :", self.sb_d_tip)

        self.gb_form = QGroupBox("Longeron sélectionné")
        self.gb_form.setLayout(form)
        self.gb_form.setEnabled(False)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(side_widget)
        split.addWidget(self.gb_form)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 2)

        v = QVBoxLayout(self)
        v.addWidget(split, 1)

        self.btn_add.clicked.connect(self._add)
        self.btn_del.clicked.connect(self._delete)
        self.lst.currentRowChanged.connect(self._on_row_changed)
        # Sync edits → modèle
        self.le_name.textChanged.connect(self._sync_to_model)
        self.cb_surface.currentIndexChanged.connect(self._sync_to_model)
        for sb in (self.sb_x_root, self.sb_x_tip,
                   self.sb_w_root, self.sb_w_tip,
                   self.sb_d_root, self.sb_d_tip):
            sb.valueChanged.connect(self._sync_to_model)

    @staticmethod
    def _mk_spin(mn, mx, val, suffix, decimals=1) -> QDoubleSpinBox:
        sb = QDoubleSpinBox()
        sb.setRange(mn, mx)
        sb.setValue(val)
        sb.setSuffix(suffix)
        sb.setDecimals(decimals)
        return sb

    def initializePage(self) -> None:
        s = self.wizard().shared
        self.lst.clear()
        for sp in s.spars:
            self.lst.addItem(self._label_for(sp))
        if s.spars:
            self.lst.setCurrentRow(0)

    @staticmethod
    def _label_for(sp: Spar) -> str:
        name = sp.name or "(sans nom)"
        return f"{name} — {sp.surface} @ x={sp.x_root_mm:.0f}…{sp.x_tip_mm:.0f}"

    def _add(self) -> None:
        s = self.wizard().shared
        x_default = max(20.0, self.wizard().shared.root_chord_mm * 0.3)
        sp = Spar(
            name=f"longeron {len(s.spars) + 1}",
            x_root_mm=x_default, x_tip_mm=x_default,
        )
        s.spars.append(sp)
        self.lst.addItem(self._label_for(sp))
        self.lst.setCurrentRow(self.lst.count() - 1)

    def _delete(self) -> None:
        s = self.wizard().shared
        i = self.lst.currentRow()
        if i < 0:
            return
        s.spars.pop(i)
        self.lst.takeItem(i)
        self._refresh_form_enabled()

    def _refresh_form_enabled(self) -> None:
        i = self.lst.currentRow()
        has = i >= 0
        self.gb_form.setEnabled(has)
        self.btn_del.setEnabled(has)

    def _on_row_changed(self, row: int) -> None:
        self._refresh_form_enabled()
        if row < 0:
            return
        s = self.wizard().shared
        if row >= len(s.spars):
            return
        sp = s.spars[row]
        self._suppress_form_sync = True
        self.le_name.setText(sp.name)
        idx = self.cb_surface.findData(sp.surface)
        if idx >= 0:
            self.cb_surface.setCurrentIndex(idx)
        self.sb_x_root.setValue(sp.x_root_mm)
        self.sb_x_tip.setValue(sp.x_tip_mm)
        self.sb_w_root.setValue(sp.width_root_mm)
        self.sb_w_tip.setValue(sp.width_tip_mm)
        self.sb_d_root.setValue(sp.depth_root_mm)
        self.sb_d_tip.setValue(sp.depth_tip_mm)
        self._suppress_form_sync = False

    def _sync_to_model(self) -> None:
        if self._suppress_form_sync:
            return
        i = self.lst.currentRow()
        if i < 0:
            return
        s = self.wizard().shared
        sp = s.spars[i]
        sp.name = self.le_name.text().strip()
        sp.surface = self.cb_surface.currentData()
        sp.x_root_mm = self.sb_x_root.value()
        sp.x_tip_mm = self.sb_x_tip.value()
        sp.width_root_mm = self.sb_w_root.value()
        sp.width_tip_mm = self.sb_w_tip.value()
        sp.depth_root_mm = self.sb_d_root.value()
        sp.depth_tip_mm = self.sb_d_tip.value()
        self.lst.item(i).setText(self._label_for(sp))


# ----------------------------------------------------------------------
# Page 5 — Lightening holes (Step 2)
# ----------------------------------------------------------------------

class _LighteningHolesPage(QWizardPage):
    """Trous d'allègement : paramètres documentaires uniquement.

    Un fil chaud 4 axes ne peut pas plonger au milieu du bloc, donc ces
    trous ne sont PAS coupés dans la mousse. Les paramètres sont conservés
    pour être inclus dans la fiche PDF (utile si tu génères des gabarits
    de nervures balsa au laser à part)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setTitle("5. Trous d'allègement (documentaire)")
        self.setSubTitle(
            "Note : ces trous ne sont PAS coupés dans la mousse (un fil chaud "
            "ne peut pas plonger). Ils sont sauvegardés dans le projet et "
            "inclus dans la fiche PDF pour la fabrication de nervures balsa à part."
        )

        self._suppress = False

        self.lst = QListWidget()
        self.btn_add = QPushButton("➕  Ajouter")
        self.btn_del = QPushButton("🗑  Supprimer")
        self.btn_del.setEnabled(False)
        side_actions = QHBoxLayout()
        side_actions.addWidget(self.btn_add)
        side_actions.addWidget(self.btn_del)
        side_actions.addStretch(1)
        side = QVBoxLayout()
        side.addWidget(QLabel("Trous d'allègement :"))
        side.addWidget(self.lst, 1)
        side.addLayout(side_actions)
        side_widget = QWidget()
        side_widget.setLayout(side)

        self.le_name = QLineEdit()
        self.cb_shape = QComboBox()
        self.cb_shape.addItem("Suit le profil (airfoil)", "airfoil")
        self.cb_shape.addItem("Rectangle", "rectangle")
        self.cb_shape.addItem("Ellipse", "ellipse")
        self.sb_edge = QDoubleSpinBox()
        self.sb_edge.setRange(5, 80)
        self.sb_edge.setSuffix(" %")
        self.sb_edge.setValue(20.0)
        self.cb_auto = QCheckBox("Génération automatique")
        self.sb_xs_root = QDoubleSpinBox(); self.sb_xs_root.setRange(0, 1000); self.sb_xs_root.setSuffix(" mm"); self.sb_xs_root.setValue(50.0)
        self.sb_xe_root = QDoubleSpinBox(); self.sb_xe_root.setRange(0, 1000); self.sb_xe_root.setSuffix(" mm"); self.sb_xe_root.setValue(100.0)
        self.sb_xs_tip = QDoubleSpinBox(); self.sb_xs_tip.setRange(0, 1000); self.sb_xs_tip.setSuffix(" mm"); self.sb_xs_tip.setValue(50.0)
        self.sb_xe_tip = QDoubleSpinBox(); self.sb_xe_tip.setRange(0, 1000); self.sb_xe_tip.setSuffix(" mm"); self.sb_xe_tip.setValue(100.0)

        f = QFormLayout()
        f.addRow("Nom :", self.le_name)
        f.addRow("Forme :", self.cb_shape)
        f.addRow("Épaisseur bord nervure :", self.sb_edge)
        f.addRow(self.cb_auto)
        f.addRow("X début emplanture :", self.sb_xs_root)
        f.addRow("X fin emplanture :", self.sb_xe_root)
        f.addRow("X début saumon :", self.sb_xs_tip)
        f.addRow("X fin saumon :", self.sb_xe_tip)

        self.gb_form = QGroupBox("Trou sélectionné")
        self.gb_form.setLayout(f)
        self.gb_form.setEnabled(False)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(side_widget)
        split.addWidget(self.gb_form)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 2)

        v = QVBoxLayout(self)
        v.addWidget(split, 1)

        self.btn_add.clicked.connect(self._add)
        self.btn_del.clicked.connect(self._delete)
        self.lst.currentRowChanged.connect(self._on_row_changed)
        for w in (self.le_name, self.cb_shape, self.sb_edge, self.cb_auto,
                  self.sb_xs_root, self.sb_xe_root, self.sb_xs_tip, self.sb_xe_tip):
            if isinstance(w, QLineEdit):
                w.textChanged.connect(self._sync)
            elif isinstance(w, QComboBox):
                w.currentIndexChanged.connect(self._sync)
            elif isinstance(w, QCheckBox):
                w.toggled.connect(self._sync)
            else:
                w.valueChanged.connect(self._sync)

    @staticmethod
    def _label(h: LighteningHole) -> str:
        return f"{h.name or '(sans nom)'} — {h.shape} {h.x_start_root_mm:.0f}…{h.x_end_root_mm:.0f}"

    def initializePage(self) -> None:
        s = self.wizard().shared
        self.lst.clear()
        for h in s.lightening_holes:
            self.lst.addItem(self._label(h))
        if s.lightening_holes:
            self.lst.setCurrentRow(0)

    def _add(self) -> None:
        s = self.wizard().shared
        h = LighteningHole(name=f"trou {len(s.lightening_holes) + 1}")
        s.lightening_holes.append(h)
        self.lst.addItem(self._label(h))
        self.lst.setCurrentRow(self.lst.count() - 1)

    def _delete(self) -> None:
        s = self.wizard().shared
        i = self.lst.currentRow()
        if i < 0:
            return
        s.lightening_holes.pop(i)
        self.lst.takeItem(i)
        has = self.lst.currentRow() >= 0
        self.gb_form.setEnabled(has)
        self.btn_del.setEnabled(has)

    def _on_row_changed(self, row: int) -> None:
        has = row >= 0
        self.gb_form.setEnabled(has)
        self.btn_del.setEnabled(has)
        if row < 0:
            return
        s = self.wizard().shared
        if row >= len(s.lightening_holes):
            return
        h = s.lightening_holes[row]
        self._suppress = True
        self.le_name.setText(h.name)
        idx = self.cb_shape.findData(h.shape)
        if idx >= 0:
            self.cb_shape.setCurrentIndex(idx)
        self.sb_edge.setValue(h.rib_edge_thickness_pct)
        self.cb_auto.setChecked(h.automatic)
        self.sb_xs_root.setValue(h.x_start_root_mm)
        self.sb_xe_root.setValue(h.x_end_root_mm)
        self.sb_xs_tip.setValue(h.x_start_tip_mm)
        self.sb_xe_tip.setValue(h.x_end_tip_mm)
        self._suppress = False

    def _sync(self) -> None:
        if self._suppress:
            return
        i = self.lst.currentRow()
        if i < 0:
            return
        s = self.wizard().shared
        h = s.lightening_holes[i]
        h.name = self.le_name.text().strip()
        h.shape = self.cb_shape.currentData()
        h.rib_edge_thickness_pct = self.sb_edge.value()
        h.automatic = self.cb_auto.isChecked()
        h.x_start_root_mm = self.sb_xs_root.value()
        h.x_end_root_mm = self.sb_xe_root.value()
        h.x_start_tip_mm = self.sb_xs_tip.value()
        h.x_end_tip_mm = self.sb_xe_tip.value()
        self.lst.item(i).setText(self._label(h))


# ----------------------------------------------------------------------
# Page 6 — Foam block placement
# ----------------------------------------------------------------------

class _FoamBlockPage(QWizardPage):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setTitle("6. Placement du bloc de mousse")
        self.setSubTitle(
            "Définis l'épaisseur du bloc, la hauteur du panneau dans le bloc "
            "et sa distance par rapport à chaque chariot."
        )

        self.sb_wire_span = self._mk_spin(100, 5000, 1000.0)
        self.sb_thickness = self._mk_spin(10, 500, 50.0)
        self.sb_h_root = self._mk_spin(0, 500, 25.0)
        self.sb_h_tip = self._mk_spin(0, 500, 25.0)
        self.sb_d_root = self._mk_spin(0, 2000, 0.0)
        self.sb_d_tip = self._mk_spin(0, 2000, 0.0)

        f = QFormLayout()
        f.addRow("Distance entre tours (wire_span) :", self.sb_wire_span)
        f.addRow("Épaisseur du bloc (T) :", self.sb_thickness)
        f.addRow("Hauteur panneau emplanture (H) :", self.sb_h_root)
        f.addRow("Hauteur panneau saumon (H) :", self.sb_h_tip)
        f.addRow("Distance bloc ↔ chariot gauche emplanture (D) :", self.sb_d_root)
        f.addRow("Distance bloc ↔ chariot gauche saumon (D) :", self.sb_d_tip)

        info = QLabel(
            "<i>Note : block_root_x = D root, block_tip_x = wire_span − D tip "
            "− corde saumon (calculé automatiquement à la génération).</i>"
        )
        info.setWordWrap(True)

        v = QVBoxLayout(self)
        v.addLayout(f)
        v.addWidget(info)
        v.addStretch(1)

    @staticmethod
    def _mk_spin(mn, mx, val) -> QDoubleSpinBox:
        sb = QDoubleSpinBox()
        sb.setRange(mn, mx)
        sb.setValue(val)
        sb.setSuffix(" mm")
        sb.setDecimals(1)
        return sb

    def initializePage(self) -> None:
        s = self.wizard().shared
        self.sb_wire_span.setValue(s.wire_span_mm)
        self.sb_thickness.setValue(s.block_thickness_mm)
        self.sb_h_root.setValue(s.height_root_mm)
        self.sb_h_tip.setValue(s.height_tip_mm)
        self.sb_d_root.setValue(s.distance_root_mm)
        self.sb_d_tip.setValue(s.distance_tip_mm)

    def validatePage(self) -> bool:
        s = self.wizard().shared
        s.wire_span_mm = self.sb_wire_span.value()
        s.block_thickness_mm = self.sb_thickness.value()
        s.height_root_mm = self.sb_h_root.value()
        s.height_tip_mm = self.sb_h_tip.value()
        s.distance_root_mm = self.sb_d_root.value()
        s.distance_tip_mm = self.sb_d_tip.value()
        return True


# ----------------------------------------------------------------------
# Page 7 — LE/TE cutting (Step 3)
# ----------------------------------------------------------------------

class _LeTeCuttingPage(QWizardPage):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setTitle("7. Coupe LE / TE séparée")
        self.setSubTitle("Coupe préliminaire du bord d'attaque et du bord de fuite.")
        lbl = QLabel(
            "🚧 Fonctionnalité en cours d'implémentation (Step 3 de la refonte).\n\n"
            "Tu pourras bientôt :\n"
            "  • activer une coupe LE et/ou TE plate avant le profil\n"
            "  • régler la largeur root/tip de chaque coupe\n"
            "  • régler la hauteur de sécurité au-dessus du bloc\n"
            "  • générer des gabarits de vérification de nez\n\n"
            "Pour l'instant, le wizard ignore cette étape."
        )
        lbl.setWordWrap(True)
        v = QVBoxLayout(self)
        v.addWidget(lbl)
        v.addStretch(1)


# ----------------------------------------------------------------------
# Page 8 — Cut params + Generation
# ----------------------------------------------------------------------

class _FinalPage(QWizardPage):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setTitle("8. Paramètres de coupe et génération")
        self.setSubTitle(
            "Derniers réglages d'avance et de puissance, puis cliquez Terminer."
        )
        self.setFinalPage(True)

        self.sb_feed = QSpinBox()
        self.sb_feed.setRange(10, 2000)
        self.sb_feed.setSuffix(" mm/min")
        self.sb_feed.setValue(200)

        self.sb_s = QSpinBox()
        self.sb_s.setRange(0, 1000)
        self.sb_s.setValue(500)

        self.sb_leadin = QDoubleSpinBox()
        self.sb_leadin.setRange(0, 200)
        self.sb_leadin.setSuffix(" mm")
        self.sb_leadin.setValue(20.0)

        self.sb_leadout = QDoubleSpinBox()
        self.sb_leadout.setRange(0, 200)
        self.sb_leadout.setSuffix(" mm")
        self.sb_leadout.setValue(20.0)

        self.sb_n = QSpinBox()
        self.sb_n.setRange(20, 2000)
        self.sb_n.setValue(200)

        f = QFormLayout()
        f.addRow("Avance de coupe (F) :", self.sb_feed)
        f.addRow("Puissance fil (S) :", self.sb_s)
        f.addRow("Lead-in :", self.sb_leadin)
        f.addRow("Lead-out :", self.sb_leadout)
        f.addRow("Points par profil :", self.sb_n)

        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.RichText)

        v = QVBoxLayout(self)
        v.addLayout(f)
        v.addWidget(QLabel("Récapitulatif :"))
        v.addWidget(self.summary, 1)

    def initializePage(self) -> None:
        s = self.wizard().shared
        self.sb_feed.setValue(int(s.feed))
        self.sb_s.setValue(s.hot_wire_s)
        self.sb_leadin.setValue(s.leadin_mm)
        self.sb_leadout.setValue(s.leadout_mm)
        self.sb_n.setValue(s.n_resample)
        sheet_html = ""
        if s.sheeting_upper_mm > 0 or s.sheeting_lower_mm > 0:
            sheet_html = (
                f"<li>Coffrage : extrados {s.sheeting_upper_mm:.1f} mm / "
                f"intrados {s.sheeting_lower_mm:.1f} mm</li>"
            )
        kerf_html = ""
        if s.use_differential_kerf:
            kerf_html = (
                f"<li>Kerf différencié : root {s.kerf_root_mm:.2f} mm → "
                f"tip {s.kerf_tip_mm:.2f} mm</li>"
            )
        self.summary.setText(
            f"<ul>"
            f"<li><b>Panneau</b> : {s.panel_length_mm:.0f} mm, "
            f"corde {s.root_chord_mm:.0f} → {s.tip_chord_mm:.0f} mm, "
            f"flèche {s.swept_back_mm:+.0f} mm</li>"
            f"<li><b>Profils</b> : {Path(s.root_profile_path).stem} → "
            f"{Path(s.tip_profile_path).stem}</li>"
            f"{sheet_html}"
            f"{kerf_html}"
            f"<li><b>TE étendu</b> : {s.te_extend_mm:.1f} mm</li>"
            f"<li><b>Bloc</b> : T={s.block_thickness_mm:.0f} mm, "
            f"H={s.height_root_mm:.0f}/{s.height_tip_mm:.0f}, "
            f"D={s.distance_root_mm:.0f}/{s.distance_tip_mm:.0f}</li>"
            f"<li><b>Longerons</b> : {len(s.spars)} "
            f"({sum(1 for sp in s.spars if sp.surface == 'upper')} extrados, "
            f"{sum(1 for sp in s.spars if sp.surface == 'lower')} intrados)</li>"
            f"<li><b>Trous d'allègement</b> : {len(s.lightening_holes)} "
            f"(documentaire uniquement, pas dans le G-code)</li>"
            f"</ul>"
        )

    def validatePage(self) -> bool:
        s = self.wizard().shared
        s.feed = self.sb_feed.value()
        s.hot_wire_s = self.sb_s.value()
        s.leadin_mm = self.sb_leadin.value()
        s.leadout_mm = self.sb_leadout.value()
        s.n_resample = self.sb_n.value()
        return True


# ----------------------------------------------------------------------
# Wizard
# ----------------------------------------------------------------------

class SlicerWizard(QWizard):
    """Wizard 8 étapes inspiré de Profili 2 Pro.

    Émet `gcode_generated(list[str])` sur Finish."""

    gcode_generated = Signal(list)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Slicer guidé — inspiré de Profili 2 Pro")
        self.setWizardStyle(QWizard.ModernStyle)
        self.setOption(QWizard.IndependentPages, False)
        self.setOption(QWizard.NoCancelButtonOnLastPage, False)
        self.resize(900, 720)

        self.shared = _Shared()

        self.addPage(_PanelInfoPage())
        self.addPage(_AirfoilPage())
        self.addPage(_SheetingKerfPage())
        self.addPage(_SparsPage())
        self.addPage(_LighteningHolesPage())
        self.addPage(_FoamBlockPage())
        self.addPage(_LeTeCuttingPage())
        self.addPage(_FinalPage())

        self.finished.connect(self._on_finished)

    def _on_finished(self, result: int) -> None:
        if result != QWizard.Accepted:
            return
        try:
            gcode = self._generate()
        except Exception as e:
            QMessageBox.critical(self, "Erreur génération", str(e))
            return
        if not gcode:
            return
        self.gcode_generated.emit(gcode)

    def _generate(self) -> list[str]:
        s = self.shared
        if not (s.root_profile_path and s.tip_profile_path):
            raise ValueError("Profils root et tip requis.")

        root = load_profile(s.root_profile_path)
        tip = load_profile(s.tip_profile_path)
        if s.invert_airfoils:
            root = Profile(name=root.name, points=[(x, -y) for x, y in root.points])
            tip = Profile(name=tip.name, points=[(x, -y) for x, y in tip.points])

        # Construction d'une WingDefinition à 2 sections
        sec_root = Section(
            span_y_mm=0.0,
            profile_path=s.root_profile_path,
            profile_name=root.name,
            chord_mm=s.root_chord_mm,
            twist_deg=s.root_incidence_deg,
            offset_x_mm=0.0,
            offset_y_mm=0.0,
            kerf_mm=0.0,
            profile=root,
        )
        sec_tip = Section(
            span_y_mm=s.panel_length_mm,
            profile_path=s.tip_profile_path,
            profile_name=tip.name,
            chord_mm=s.tip_chord_mm,
            twist_deg=s.tip_incidence_deg,
            offset_x_mm=s.swept_back_mm,
            offset_y_mm=0.0,
            kerf_mm=0.0,
            profile=tip,
        )
        wing = WingDefinition(sections=[sec_root, sec_tip])

        # Géométrie machine : on déduit block_root_x / block_tip_x des D et des cordes
        block_root_x = s.distance_root_mm
        max_chord = max(s.root_chord_mm + s.swept_back_mm, s.tip_chord_mm + s.swept_back_mm,
                        s.root_chord_mm, s.tip_chord_mm)
        block_tip_x = block_root_x + max_chord + 20.0  # marge de 20 mm
        geom = CutGeometry(
            wire_span=s.wire_span_mm,
            block_root_x=block_root_x,
            block_tip_x=block_tip_x,
        )

        # CutParams avec sheeting + kerf différencié activés selon les choix
        params = CutParams(
            feed=s.feed,
            hot_wire_s=s.hot_wire_s,
            leadin_mm=s.leadin_mm,
            leadout_mm=s.leadout_mm,
            n_resample=s.n_resample,
            safe_y=80.0,
            sheeting_upper_mm=s.sheeting_upper_mm,
            sheeting_lower_mm=s.sheeting_lower_mm,
            tangent_extend_te_mm=s.te_extend_mm,
            use_differential_kerf=s.use_differential_kerf,
            kerf_root_mm=s.kerf_root_mm,
            kerf_tip_mm=s.kerf_tip_mm,
        )

        return generate_gcode_wing(wing, geom, params, mode="single", spars=s.spars)
