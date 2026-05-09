"""Fenêtre du slicer fil chaud multi-panneaux : N sections -> G-code 4 axes.

Layout :
- Haut : liste de Sections (2 à 4), chacune avec profil + corde + twist + offsets + kerf
- Milieu gauche : géométrie machine et bloc
- Milieu droit : paramètres de coupe + mode de génération (Continu / Séparé)
- Bas : aperçu pyqtgraph + boutons d'action
"""

from __future__ import annotations

import os
from pathlib import Path

import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core import persistence
from gcode.profiles import load_profile, resample
from gcode.slicer import CutGeometry, CutParams, generate_gcode_wing, project
from gcode.wing import Section, WingDefinition

from .airfoil_library import AirfoilLibraryDialog

# Palette de couleurs pour distinguer les sections dans l'aperçu
SECTION_COLORS = ["#1f6feb", "#d6363d", "#1f9d55", "#7950f2"]
PANEL_COLORS = [(31, 111, 235, 100), (214, 54, 61, 100),
                (31, 157, 85, 100), (121, 80, 242, 100)]

MAX_SECTIONS = 4
MIN_SECTIONS = 2


class _SectionPanel(QGroupBox):
    """Bloc de paramètres pour UNE section de l'aile."""

    changed = Signal()
    delete_requested = Signal(object)  # self
    library_requested = Signal(object)  # self

    def __init__(self, index: int, parent: QWidget | None = None):
        super().__init__("", parent)
        self._index = index
        self.section = Section(span_y_mm=0.0)

        # --- Header (titre + supprimer) ---
        self.lbl_title = QLabel(f"Section {index}")
        self.lbl_title.setFont(QFont("", 11, QFont.Bold))
        # Couleur de la section
        col = SECTION_COLORS[index % len(SECTION_COLORS)]
        self.lbl_title.setStyleSheet(f"color: {col};")

        self.btn_delete = QPushButton("✕")
        self.btn_delete.setProperty("compact", True)
        self.btn_delete.setFixedWidth(34)
        self.btn_delete.setToolTip("Supprimer cette section")
        self.btn_delete.clicked.connect(lambda: self.delete_requested.emit(self))

        header = QHBoxLayout()
        header.addWidget(self.lbl_title, 1)
        header.addWidget(self.btn_delete)

        # --- Path + boutons chargement ---
        self.le_path = QLineEdit()
        self.le_path.setReadOnly(True)
        self.le_path.setPlaceholderText("Aucun profil chargé")
        self.btn_load = QPushButton("📂")
        self.btn_load.setProperty("compact", True)
        self.btn_load.setFixedWidth(36)
        self.btn_load.setToolTip("Charger un fichier .dat depuis le disque")
        self.btn_load.clicked.connect(self._load_from_disk)

        self.btn_library = QPushButton("📚")
        self.btn_library.setProperty("compact", True)
        self.btn_library.setFixedWidth(36)
        self.btn_library.setToolTip("Choisir dans la bibliothèque Profili 2 Pro")
        self.btn_library.clicked.connect(lambda: self.library_requested.emit(self))

        path_row = QHBoxLayout()
        path_row.addWidget(self.le_path, 1)
        path_row.addWidget(self.btn_load)
        path_row.addWidget(self.btn_library)

        # --- Champs paramètres ---
        self.sb_span = QDoubleSpinBox()
        self.sb_span.setRange(0, 5000)
        self.sb_span.setSuffix(" mm")
        self.sb_span.setDecimals(1)
        self.sb_span.setToolTip(
            "Position de cette section le long de l'envergure, depuis l'emplanture"
        )

        self.sb_chord = QDoubleSpinBox()
        self.sb_chord.setRange(1, 5000)
        self.sb_chord.setSuffix(" mm")
        self.sb_chord.setValue(200.0)
        self.sb_chord.setDecimals(1)

        self.sb_twist = QDoubleSpinBox()
        self.sb_twist.setRange(-45, 45)
        self.sb_twist.setSuffix(" °")
        self.sb_twist.setDecimals(2)
        self.sb_twist.setToolTip("Vrillage : positif = nez en haut")

        self.sb_offset_x = QDoubleSpinBox()
        self.sb_offset_x.setRange(-5000, 5000)
        self.sb_offset_x.setSuffix(" mm")
        self.sb_offset_x.setToolTip(
            "Décalage horizontal (sweep accumulé depuis l'emplanture)"
        )

        self.sb_offset_y = QDoubleSpinBox()
        self.sb_offset_y.setRange(-5000, 5000)
        self.sb_offset_y.setSuffix(" mm")
        self.sb_offset_y.setToolTip(
            "Décalage vertical (dièdre accumulé depuis l'emplanture)"
        )

        self.sb_kerf = QDoubleSpinBox()
        self.sb_kerf.setRange(-5, 5)
        self.sb_kerf.setSingleStep(0.05)
        self.sb_kerf.setDecimals(2)
        self.sb_kerf.setSuffix(" mm")
        self.sb_kerf.setToolTip("Compensation sillage fil (positif = profil agrandi)")

        for sb in (self.sb_span, self.sb_chord, self.sb_twist,
                   self.sb_offset_x, self.sb_offset_y, self.sb_kerf):
            sb.valueChanged.connect(self._on_field_changed)

        form = QFormLayout()
        form.setVerticalSpacing(4)
        form.addRow("Position envergure :", self.sb_span)
        form.addRow("Corde :", self.sb_chord)
        form.addRow("Twist :", self.sb_twist)
        form.addRow("Offset X (sweep) :", self.sb_offset_x)
        form.addRow("Offset Y (dièdre) :", self.sb_offset_y)
        form.addRow("Compensation fil :", self.sb_kerf)

        v = QVBoxLayout(self)
        v.setContentsMargins(8, 6, 8, 8)
        v.setSpacing(6)
        v.addLayout(header)
        v.addLayout(path_row)
        v.addLayout(form)

    # ---- API ----

    def set_index(self, index: int, can_delete: bool) -> None:
        self._index = index
        col = SECTION_COLORS[index % len(SECTION_COLORS)]
        # Section 0 = emplanture (forcément à Y=0), N-1 = saumon
        if index == 0:
            self.lbl_title.setText(f"Section {index} — Emplanture")
            # Force span_y à 0 et désactive l'édition
            self.sb_span.blockSignals(True)
            self.sb_span.setValue(0.0)
            self.sb_span.setEnabled(False)
            self.sb_span.blockSignals(False)
        else:
            self.lbl_title.setText(f"Section {index}")
            self.sb_span.setEnabled(True)
        self.lbl_title.setStyleSheet(f"color: {col};")
        self.btn_delete.setEnabled(can_delete)
        self.btn_delete.setVisible(can_delete)

    def to_section(self) -> Section:
        s = Section(
            span_y_mm=self.sb_span.value(),
            profile_path=self.section.profile_path,
            profile_name=self.section.profile_name,
            chord_mm=self.sb_chord.value(),
            twist_deg=self.sb_twist.value(),
            offset_x_mm=self.sb_offset_x.value(),
            offset_y_mm=self.sb_offset_y.value(),
            kerf_mm=self.sb_kerf.value(),
            profile=self.section.profile,
        )
        return s

    def from_section(self, s: Section) -> None:
        self.section = s
        for sb, val in (
            (self.sb_span, s.span_y_mm),
            (self.sb_chord, s.chord_mm),
            (self.sb_twist, s.twist_deg),
            (self.sb_offset_x, s.offset_x_mm),
            (self.sb_offset_y, s.offset_y_mm),
            (self.sb_kerf, s.kerf_mm),
        ):
            sb.blockSignals(True)
            sb.setValue(val)
            sb.blockSignals(False)
        if s.profile_path:
            self.le_path.setText(os.path.basename(s.profile_path))
        else:
            self.le_path.clear()

    def load_from_path(self, path: str) -> None:
        try:
            prof = load_profile(path)
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Lecture impossible : {e}")
            return
        self.section.profile = prof
        self.section.profile_path = path
        self.section.profile_name = prof.name or os.path.basename(path)
        self.le_path.setText(os.path.basename(path))
        self.changed.emit()

    def _load_from_disk(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Charger un profil", "", "Profils (*.dat *.txt);;Tous (*)"
        )
        if path:
            self.load_from_path(path)

    def _on_field_changed(self) -> None:
        # Update la section interne
        self.section.span_y_mm = self.sb_span.value()
        self.section.chord_mm = self.sb_chord.value()
        self.section.twist_deg = self.sb_twist.value()
        self.section.offset_x_mm = self.sb_offset_x.value()
        self.section.offset_y_mm = self.sb_offset_y.value()
        self.section.kerf_mm = self.sb_kerf.value()
        self.changed.emit()


class SlicerWindow(QDialog):
    gcode_generated = Signal(list)  # liste de lignes G-code

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Slicer fil chaud — multi-panneaux")
        self.resize(1320, 880)

        self._sections: list[_SectionPanel] = []

        # ---- Liste de sections (scrollable horizontalement) ----
        self._sections_layout = QHBoxLayout()
        self._sections_layout.setSpacing(8)
        self._sections_layout.setContentsMargins(4, 4, 4, 4)
        sections_container = QWidget()
        sections_container.setLayout(self._sections_layout)

        self._sections_scroll = QScrollArea()
        self._sections_scroll.setWidget(sections_container)
        self._sections_scroll.setWidgetResizable(True)
        self._sections_scroll.setFrameShape(QFrame.NoFrame)
        self._sections_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._sections_scroll.setMinimumHeight(330)

        self.btn_add_section = QPushButton("+ Ajouter une section")
        self.btn_add_section.setProperty("variant", "primary")
        self.btn_add_section.setMinimumHeight(32)
        self.btn_add_section.clicked.connect(self._add_section)

        self.btn_new = QPushButton("🆕  Nouveau")
        self.btn_new.setMinimumHeight(32)
        self.btn_new.setToolTip(
            "Réinitialise l'aile à 2 sections vierges (sans profil chargé). "
            "Les paramètres machine et coupe sont conservés."
        )
        self.btn_new.clicked.connect(self._reset_to_blank)

        gb_sections = QGroupBox("Aile (sections)")
        v_sec = QVBoxLayout(gb_sections)
        v_sec.addWidget(self._sections_scroll)
        sec_actions = QHBoxLayout()
        sec_actions.addWidget(self.btn_new)
        sec_actions.addWidget(self.btn_add_section)
        sec_actions.addStretch(1)
        self.lbl_sections_info = QLabel("")
        self.lbl_sections_info.setStyleSheet("color: #637381; font-style: italic;")
        sec_actions.addWidget(self.lbl_sections_info)
        v_sec.addLayout(sec_actions)

        # ---- Géométrie machine et bloc ----
        gb_geom = QGroupBox("Géométrie machine et bloc")
        self.sb_wire_span = QDoubleSpinBox()
        self.sb_wire_span.setRange(50, 5000)
        self.sb_wire_span.setSuffix(" mm")
        self.sb_block_root = QDoubleSpinBox()
        self.sb_block_root.setRange(0, 5000)
        self.sb_block_root.setSuffix(" mm")
        self.sb_block_tip = QDoubleSpinBox()
        self.sb_block_tip.setRange(0, 5000)
        self.sb_block_tip.setSuffix(" mm")
        for sb in (self.sb_wire_span, self.sb_block_root, self.sb_block_tip):
            sb.valueChanged.connect(self._update_preview)
        fg = QFormLayout(gb_geom)
        fg.addRow("Distance entre tours (L_fil) :", self.sb_wire_span)
        fg.addRow("Tour gauche → face emplanture :", self.sb_block_root)
        fg.addRow("Tour gauche → face saumon :", self.sb_block_tip)

        # ---- Paramètres de coupe ----
        gb_cut = QGroupBox("Paramètres de coupe")
        self.sb_feed = QDoubleSpinBox()
        self.sb_feed.setRange(1, 5000)
        self.sb_feed.setSuffix(" mm/min")
        self.sb_s = QSpinBox()
        self.sb_s.setRange(0, 100000)
        self.sb_leadin = QDoubleSpinBox()
        self.sb_leadin.setRange(0, 200)
        self.sb_leadin.setSuffix(" mm")
        self.sb_leadout = QDoubleSpinBox()
        self.sb_leadout.setRange(0, 200)
        self.sb_leadout.setSuffix(" mm")
        self.sb_n = QSpinBox()
        self.sb_n.setRange(20, 2000)
        self.sb_safe_y = QDoubleSpinBox()
        self.sb_safe_y.setRange(0, 5000)
        self.sb_safe_y.setSuffix(" mm")
        self.cb_mode = QComboBox()
        self.cb_mode.addItem("Continu (1 fichier, pause M0 entre panneaux)", "single")
        self.cb_mode.addItem("Séparé (1 fichier par panneau)", "split")
        self.cb_mode.setToolTip(
            "Continu : un seul programme avec une pause M0 entre chaque panneau "
            "pour repositionner le bloc.\n"
            "Séparé : tu enregistres N fichiers .gcode (un par panneau)."
        )
        for sb in (self.sb_feed, self.sb_s, self.sb_leadin, self.sb_leadout,
                   self.sb_n, self.sb_safe_y):
            sb.valueChanged.connect(self._update_preview)
        fc = QFormLayout(gb_cut)
        fc.addRow("Avance de coupe :", self.sb_feed)
        fc.addRow("S (puissance fil) :", self.sb_s)
        fc.addRow("Lead-in (entrée) :", self.sb_leadin)
        fc.addRow("Lead-out (sortie) :", self.sb_leadout)
        fc.addRow("Nb points par profil :", self.sb_n)
        fc.addRow("Y sécurité retour :", self.sb_safe_y)
        fc.addRow("Mode de génération :", self.cb_mode)

        # ---- Aperçu ----
        self.plot = pg.PlotWidget()
        self.plot.setBackground("w")
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.setAspectLocked(True)
        self.plot.setLabel("bottom", "X (mm)")
        self.plot.setLabel("left", "Y (mm)")
        self._section_curves: list = []   # courbes de profils transformés
        self._panel_curves: list = []     # paires (curve_left, curve_right) par panneau

        # ---- Boutons d'action ----
        self.btn_preview = QPushButton("Rafraîchir l'aperçu")
        self.btn_save = QPushButton("Générer & sauver…")
        self.btn_load_in_app = QPushButton("Générer & charger dans l'app")
        self.btn_close = QPushButton("Fermer")
        for b in (self.btn_preview, self.btn_save, self.btn_load_in_app, self.btn_close):
            b.setMinimumHeight(34)
        self.btn_save.setProperty("variant", "primary")
        self.btn_load_in_app.setProperty("variant", "primary")
        self.btn_preview.clicked.connect(self._update_preview)
        self.btn_save.clicked.connect(self._save_gcode)
        self.btn_load_in_app.clicked.connect(self._load_in_app)
        self.btn_close.clicked.connect(self.close)

        # ---- Layout global ----
        mid = QHBoxLayout()
        mid.addWidget(gb_geom, 1)
        mid.addWidget(gb_cut, 1)

        actions = QHBoxLayout()
        actions.addWidget(self.btn_preview)
        actions.addStretch(1)
        actions.addWidget(self.btn_save)
        actions.addWidget(self.btn_load_in_app)
        actions.addWidget(self.btn_close)

        outer = QVBoxLayout(self)
        outer.addWidget(gb_sections)
        outer.addLayout(mid)
        outer.addWidget(self.plot, 1)
        outer.addLayout(actions)

        # Initialise avec 2 sections (compat v1)
        self._init_sections()
        self._load_persisted()
        self._update_section_indices()
        self._update_preview()

    # ---------- Sections : ajout / suppression ----------

    def _init_sections(self) -> None:
        for i in range(2):
            self._add_section(emit_change=False)

    def _add_section(self, emit_change: bool = True) -> None:
        if len(self._sections) >= MAX_SECTIONS:
            QMessageBox.information(
                self, "Maximum atteint",
                f"Limite de {MAX_SECTIONS} sections (= {MAX_SECTIONS - 1} panneaux maximum)."
            )
            return
        idx = len(self._sections)
        panel = _SectionPanel(index=idx)
        # Position envergure par défaut : si nouveau, prendre le double de la
        # précédente ou 300 mm si c'est la deuxième section
        if idx == 0:
            panel.sb_span.setValue(0.0)
        elif idx == 1:
            panel.sb_span.setValue(300.0)
        else:
            prev = self._sections[-1].sb_span.value()
            prev_prev = self._sections[-2].sb_span.value() if len(self._sections) >= 2 else 0.0
            panel.sb_span.setValue(prev + max(150.0, prev - prev_prev))
        # Corde par défaut : décroissante avec l'envergure
        if idx == 0:
            panel.sb_chord.setValue(200.0)
        else:
            prev_chord = self._sections[-1].sb_chord.value()
            panel.sb_chord.setValue(max(60.0, prev_chord * 0.7))
        panel.changed.connect(self._update_preview)
        panel.delete_requested.connect(self._delete_section)
        panel.library_requested.connect(self._open_library_for)
        self._sections.append(panel)
        self._sections_layout.addWidget(panel)
        self._update_section_indices()
        if emit_change:
            self._update_preview()

    def _delete_section(self, panel: _SectionPanel) -> None:
        if len(self._sections) <= MIN_SECTIONS:
            return
        try:
            self._sections.remove(panel)
        except ValueError:
            return
        self._sections_layout.removeWidget(panel)
        panel.setParent(None)
        panel.deleteLater()
        self._update_section_indices()
        self._update_preview()

    def _reset_to_blank(self) -> None:
        """Vide toutes les sections et repart sur 2 sections vierges."""
        # Confirmation si on a au moins un profil chargé
        loaded = any(p.section.profile is not None for p in self._sections)
        if loaded:
            answer = QMessageBox.question(
                self, "Nouveau projet",
                "Réinitialiser l'aile à 2 sections vierges ?\n"
                "Les profils chargés et leurs paramètres seront perdus.\n"
                "(Les paramètres machine et coupe sont conservés.)",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        # Supprime tous les panels existants
        while self._sections:
            p = self._sections.pop()
            self._sections_layout.removeWidget(p)
            p.setParent(None)
            p.deleteLater()
        # Repart sur 2 sections vierges
        for _ in range(MIN_SECTIONS):
            self._add_section(emit_change=False)
        self._update_section_indices()
        self._update_preview()

    def _update_section_indices(self) -> None:
        n = len(self._sections)
        for i, p in enumerate(self._sections):
            p.set_index(i, can_delete=(n > MIN_SECTIONS and i > 0))
        n_panels = max(0, n - 1)
        self.lbl_sections_info.setText(
            f"{n} section(s) → {n_panels} panneau(x) à découper"
        )

    # ---------- Bibliothèque ----------

    def _open_library_for(self, panel: _SectionPanel) -> None:
        idx = panel._index
        dlg = AirfoilLibraryDialog(
            button_label=f"Charger dans la section {idx}",
            parent=self,
        )
        dlg.profile_selected.connect(panel.load_from_path)
        dlg.exec()

    # ---------- Aperçu ----------

    def _build_wing(self) -> WingDefinition | None:
        """Construit la WingDefinition courante (ou None si incomplet)."""
        if not all(p.section.profile is not None for p in self._sections):
            return None
        sections = [p.to_section() for p in self._sections]
        # Vérification cohérence : span_y croissant
        spans = [s.span_y_mm for s in sections]
        if any(spans[i] >= spans[i + 1] for i in range(len(spans) - 1)):
            return None
        return WingDefinition(sections=sections)

    def _update_preview(self) -> None:
        # Nettoie les courbes existantes
        for c in self._section_curves:
            self.plot.removeItem(c)
        self._section_curves.clear()
        for cl, cr in self._panel_curves:
            self.plot.removeItem(cl)
            self.plot.removeItem(cr)
        self._panel_curves.clear()

        wing = self._build_wing()
        if wing is None:
            return

        # Trace les profils transformés (chaque section dans sa couleur)
        transformed = []
        for i, s in enumerate(wing.sections):
            t = s.transformed()
            if t is None:
                continue
            transformed.append(t)
            color = SECTION_COLORS[i % len(SECTION_COLORS)]
            curve = self.plot.plot(
                [p[0] for p in t.points],
                [p[1] for p in t.points],
                pen=pg.mkPen(color, width=2),
            )
            self._section_curves.append(curve)

        # Trace les projections sur les chariots pour chaque panneau
        try:
            geom = CutGeometry(
                wire_span=self.sb_wire_span.value(),
                block_root_x=self.sb_block_root.value(),
                block_tip_x=self.sb_block_tip.value(),
            )
            n = self.sb_n.value()
            for i in range(wing.n_panels):
                a = resample(transformed[i], n)
                b = resample(transformed[i + 1], n)
                pts = project(a, b, geom)
                color = PANEL_COLORS[i % len(PANEL_COLORS)]
                cl = self.plot.plot(
                    [p[0] for p in pts], [p[1] for p in pts],
                    pen=pg.mkPen(color, width=1, style=Qt.DashLine),
                )
                cr = self.plot.plot(
                    [p[2] for p in pts], [p[3] for p in pts],
                    pen=pg.mkPen(color, width=1, style=Qt.DashLine),
                )
                self._panel_curves.append((cl, cr))
        except Exception:
            pass
        self.plot.autoRange()

    # ---------- Génération G-code ----------

    def _build_gcode(self):
        """Retourne (lines, mode) ou (list[list[str]], 'split') selon le mode."""
        wing = self._build_wing()
        if wing is None:
            QMessageBox.warning(
                self, "Configuration incomplète",
                "Vérifie que toutes les sections ont un profil chargé "
                "et que les positions d'envergure sont strictement croissantes."
            )
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
            mode = self.cb_mode.currentData()
            return generate_gcode_wing(wing, geom, params, mode=mode), mode
        except Exception as e:
            QMessageBox.critical(self, "Erreur génération", str(e))
            return None

    def _save_gcode(self) -> None:
        out = self._build_gcode()
        if out is None:
            return
        result, mode = out
        if mode == "single":
            path, _ = QFileDialog.getSaveFileName(
                self, "Sauver le G-code", "aile.gcode",
                "G-code (*.gcode *.nc *.tap *.ngc);;Tous (*)",
            )
            if not path:
                return
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write("\n".join(result))
                    f.write("\n")
            except OSError as e:
                QMessageBox.critical(self, "Erreur", f"Écriture impossible : {e}")
                return
            QMessageBox.information(self, "OK", f"G-code écrit : {len(result)} lignes")
        else:
            # Mode split : demander un dossier puis écrire panneau_1.gcode, panneau_2.gcode...
            base_dir = QFileDialog.getExistingDirectory(
                self, "Choisir le dossier de sauvegarde",
                str(Path.home()),
            )
            if not base_dir:
                return
            count = 0
            for i, prog in enumerate(result):
                path = Path(base_dir) / f"aile_panneau_{i + 1}.gcode"
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write("\n".join(prog))
                        f.write("\n")
                    count += 1
                except OSError as e:
                    QMessageBox.critical(self, "Erreur", f"{path}: {e}")
                    break
            QMessageBox.information(
                self, "OK",
                f"{count} fichier(s) écrit(s) dans :\n{base_dir}"
            )

    def _load_in_app(self) -> None:
        out = self._build_gcode()
        if out is None:
            return
        result, mode = out
        if mode == "split":
            # On charge SEULEMENT le premier panneau dans l'app
            if not result:
                return
            QMessageBox.information(
                self, "Mode séparé",
                f"Mode séparé : {len(result)} programmes générés.\n\n"
                f"Seul le panneau 1 ({len(result[0])} lignes) sera chargé dans l'app. "
                f"Utilise « Sauver » pour exporter tous les panneaux."
            )
            self.gcode_generated.emit(result[0])
        else:
            self.gcode_generated.emit(result)
        self.close()

    # ---------- Persistance via WingDefinition JSON ----------

    def _load_persisted(self) -> None:
        # Géométrie machine + cut params
        defaults = {
            "wire_span": 1000.0, "block_root_x": 150.0, "block_tip_x": 850.0,
            "feed": 200.0, "hot_wire_s": 500, "leadin": 20.0, "leadout": 20.0,
            "n_resample": 200, "safe_y": 80.0, "mode": "single",
        }
        self.sb_wire_span.setValue(persistence.get_float("slicer/wire_span", defaults["wire_span"]))
        self.sb_block_root.setValue(persistence.get_float("slicer/block_root_x", defaults["block_root_x"]))
        self.sb_block_tip.setValue(persistence.get_float("slicer/block_tip_x", defaults["block_tip_x"]))
        self.sb_feed.setValue(persistence.get_float("slicer/feed", defaults["feed"]))
        self.sb_s.setValue(persistence.get_int("slicer/hot_wire_s", defaults["hot_wire_s"]))
        self.sb_leadin.setValue(persistence.get_float("slicer/leadin", defaults["leadin"]))
        self.sb_leadout.setValue(persistence.get_float("slicer/leadout", defaults["leadout"]))
        self.sb_n.setValue(persistence.get_int("slicer/n_resample", defaults["n_resample"]))
        self.sb_safe_y.setValue(persistence.get_float("slicer/safe_y", defaults["safe_y"]))

        mode = persistence.get_str("slicer/mode", defaults["mode"])
        idx = self.cb_mode.findData(mode)
        if idx >= 0:
            self.cb_mode.setCurrentIndex(idx)

        # WingDefinition (optionnelle, si elle existe)
        wing_json = persistence.get_str("slicer/wing_json", "")
        if wing_json:
            try:
                wing = WingDefinition.from_json(wing_json)
                if wing.n_sections >= MIN_SECTIONS:
                    # Reset les sections actuelles
                    while self._sections:
                        p = self._sections.pop()
                        self._sections_layout.removeWidget(p)
                        p.setParent(None)
                        p.deleteLater()
                    for s in wing.sections[:MAX_SECTIONS]:
                        self._add_section(emit_change=False)
                        panel = self._sections[-1]
                        panel.from_section(s)
                    self._update_section_indices()
            except Exception:
                pass

    def _save_persisted(self) -> None:
        persistence.set_("slicer/wire_span", self.sb_wire_span.value())
        persistence.set_("slicer/block_root_x", self.sb_block_root.value())
        persistence.set_("slicer/block_tip_x", self.sb_block_tip.value())
        persistence.set_("slicer/feed", self.sb_feed.value())
        persistence.set_("slicer/hot_wire_s", self.sb_s.value())
        persistence.set_("slicer/leadin", self.sb_leadin.value())
        persistence.set_("slicer/leadout", self.sb_leadout.value())
        persistence.set_("slicer/n_resample", self.sb_n.value())
        persistence.set_("slicer/safe_y", self.sb_safe_y.value())
        persistence.set_("slicer/mode", self.cb_mode.currentData() or "single")
        # WingDefinition
        wing = WingDefinition(sections=[p.to_section() for p in self._sections])
        persistence.set_("slicer/wing_json", wing.to_json())

    def closeEvent(self, event) -> None:
        self._save_persisted()
        super().closeEvent(event)
