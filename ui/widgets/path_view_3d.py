"""Vue 3D du fil chaud entre les 2 chariots avec navigation enrichie.

Convention spatiale (pyqtgraph.opengl, Z up) :
- Axe X 3D : direction de la corde (horizontale, dans le plan d'envergure)
- Axe Y 3D : envergure (le fil va du tour gauche y=0 au tour droit y=L_fil)
- Axe Z 3D : épaisseur (vertical)

Mapping G-code → 3D :
- chariot gauche : G-code X = chord, G-code Y = thickness  →  pos 3D (X, 0, Y)
- chariot droit  : G-code A = chord, G-code Z = thickness  →  pos 3D (A, L, Z)

Navigation :
- Glisser souris : orbiter
- Molette : zoomer
- Clic droit + glisser : panoramique
- Boutons toolbar et raccourcis clavier 1/2/3/4 : vues pré-définies
- F ou Home : recadre sur le contenu
"""

from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

try:
    import pyqtgraph.opengl as gl
    _GL_OK = True
except Exception as _e:
    gl = None  # type: ignore
    _GL_OK = False


if _GL_OK:
    class _GLPanView(gl.GLViewWidget):
        """GLViewWidget enrichi : clic droit + glisser = pan,
        Shift+gauche = pan également (en plus du clic milieu standard)."""

        def mousePressEvent(self, ev):
            # Initialise la position pour les drags non-gérés par le parent
            if ev.button() == Qt.RightButton:
                self.mousePos = ev.position() if hasattr(ev, "position") else ev.localPos()
                ev.accept()
                return
            super().mousePressEvent(ev)

        def mouseMoveEvent(self, ev):
            buttons = ev.buttons()
            mods = ev.modifiers()

            # Cas pan : clic droit OU shift+clic gauche
            pan_with_right = bool(buttons & Qt.RightButton)
            pan_with_shift = bool(buttons & Qt.LeftButton) and bool(mods & Qt.ShiftModifier)

            if pan_with_right or pan_with_shift:
                lpos = ev.position() if hasattr(ev, "position") else ev.localPos()
                if not hasattr(self, "mousePos"):
                    self.mousePos = lpos
                diff = lpos - self.mousePos
                self.mousePos = lpos
                self.pan(diff.x(), diff.y(), 0, relative="view-upright")
                ev.accept()
                return

            super().mouseMoveEvent(ev)

        def mouseReleaseEvent(self, ev):
            if ev.button() == Qt.RightButton:
                ev.accept()
                return
            super().mouseReleaseEvent(ev)

        def contextMenuEvent(self, ev):
            # Empêche tout menu contextuel qui interférerait avec le pan
            ev.ignore()


# Vues pré-définies : (elevation deg, azimuth deg, label, raccourci clavier)
_VIEW_PRESETS = {
    "top":   (89.9, 0.0,    "Dessus",  "1"),
    "front": (0.0,  -90.0,  "Face",    "2"),
    "side":  (0.0,  0.0,    "Côté",    "3"),
    "iso":   (28.0, -55.0,  "Iso",     "4"),
}


class PathView3D(QWidget):
    """Vue 3D avec toolbar de navigation. Si OpenGL indisponible, message à la place."""

    sim_play_requested = Signal()
    sim_pause_requested = Signal()
    sim_stop_requested = Signal()
    sim_speed_changed = Signal(float)

    def __init__(self, wire_span_default: float = 1000.0, parent: QWidget | None = None):
        super().__init__(parent)
        self._wire_span = wire_span_default
        self._show_profiles = True
        self._show_sweep = True
        self._show_wire = True
        self._loaded_extents: tuple[float, float, float, float, float, float] | None = None
        # Mode simulation : quand True, ignore les `on_mpos` venant du firmware
        self._sim_mode = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        if not _GL_OK:
            lbl = QLabel(
                "Vue 3D indisponible : `PyOpenGL` non installé.\n"
                "Pour activer cette vue, exécute :\n\n"
                "    pip install PyOpenGL\n"
                "puis relance l'application."
            )
            lbl.setWordWrap(True)
            lbl.setStyleSheet("padding: 20px; color: #666;")
            outer.addWidget(lbl)
            self._view = None
            return

        # ---- Toolbar ----
        outer.addWidget(self._build_toolbar())

        # ---- Vue OpenGL ----
        self._view = _GLPanView()
        self._view.setBackgroundColor((24, 26, 32))
        self._view.setCameraPosition(distance=1500, elevation=28, azimuth=-55)
        outer.addWidget(self._view, 1)

        # ---- Barre de simulation (en bas) ----
        outer.addWidget(self._build_sim_toolbar())

        # ---- Items 3D ----
        # Grille au sol (plan XY, Z=0)
        grid = gl.GLGridItem()
        grid.setSize(2400, 2400)
        grid.setSpacing(100, 100)
        grid.setColor((110, 118, 132, 60))
        self._view.addItem(grid)

        # Axes XYZ avec couleurs RGB
        axis = gl.GLAxisItem(antialias=True)
        axis.setSize(220, 220, 220)
        self._view.addItem(axis)

        # Profils
        self._curve_root = gl.GLLinePlotItem(
            pos=np.zeros((1, 3), dtype=np.float32),
            color=(0.30, 0.65, 1.0, 1.0),
            width=2.5,
            antialias=True,
        )
        self._curve_tip = gl.GLLinePlotItem(
            pos=np.zeros((1, 3), dtype=np.float32),
            color=(1.0, 0.45, 0.45, 1.0),
            width=2.5,
            antialias=True,
        )
        self._view.addItem(self._curve_root)
        self._view.addItem(self._curve_tip)

        # Fil courant (jaune épais)
        self._wire = gl.GLLinePlotItem(
            pos=np.array([[0, 0, 0], [0, self._wire_span, 0]], dtype=np.float32),
            color=(1.0, 0.85, 0.0, 1.0),
            width=4.0,
            antialias=True,
        )
        self._view.addItem(self._wire)

        # Surface balayée — 3 catégories en couleurs différentes :
        # G1 + fil ON  : rouge soutenu (la vraie coupe)
        # G1 + fil OFF : gris pointillé (lead-in/out)
        # G0 (rapide)  : vert très discret
        self._sweep_cut = gl.GLLinePlotItem(
            pos=np.zeros((1, 3), dtype=np.float32),
            color=(0.84, 0.21, 0.24, 0.55),   # rouge translucide
            width=1.5,
            antialias=True,
            mode="lines",
        )
        self._sweep_lead = gl.GLLinePlotItem(
            pos=np.zeros((1, 3), dtype=np.float32),
            color=(0.55, 0.6, 0.7, 0.35),     # gris translucide
            width=1.0,
            antialias=True,
            mode="lines",
        )
        self._sweep_rapid = gl.GLLinePlotItem(
            pos=np.zeros((1, 3), dtype=np.float32),
            color=(0.12, 0.62, 0.34, 0.30),   # vert translucide
            width=1.0,
            antialias=True,
            mode="lines",
        )
        # Alias pour la compat avec l'ancien code de visibility toggle
        self._sweep = self._sweep_cut
        self._view.addItem(self._sweep_cut)
        self._view.addItem(self._sweep_lead)
        self._view.addItem(self._sweep_rapid)

        # Boîte englobante (mise à jour avec set_program)
        self._bbox = gl.GLLinePlotItem(
            pos=np.zeros((1, 3), dtype=np.float32),
            color=(1.0, 1.0, 1.0, 0.18),
            width=1.0,
            antialias=True,
            mode="lines",
        )
        self._view.addItem(self._bbox)

        # Étiquettes d'axes (texte 3D si dispo dans la version pyqtgraph installée)
        self._add_axis_labels()

        # ---- Raccourcis clavier ----
        for name, (_e, _a, _lbl, key) in _VIEW_PRESETS.items():
            sc = QShortcut(QKeySequence(key), self)
            sc.activated.connect(lambda n=name: self._set_view(n))
        QShortcut(QKeySequence("F"), self).activated.connect(self.fit_view)
        QShortcut(QKeySequence("Home"), self).activated.connect(self.fit_view)

    # ---------- Toolbar ----------

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet("background-color: #f3f5f8; border-bottom: 1px solid #d6dde6;")
        h = QHBoxLayout(bar)
        h.setContentsMargins(8, 6, 8, 6)
        h.setSpacing(6)

        lbl = QLabel("Vue :")
        lbl.setStyleSheet("color: #637381; font-weight: 600;")
        h.addWidget(lbl)

        for name, (_e, _a, label, key) in _VIEW_PRESETS.items():
            b = QPushButton(f"{label} ({key})")
            b.setProperty("compact", True)
            b.setMinimumWidth(80)
            b.setMinimumHeight(28)
            b.setToolTip(f"Vue {label.lower()} (raccourci {key})")
            b.clicked.connect(lambda _=False, n=name: self._set_view(n))
            h.addWidget(b)

        sep1 = QLabel(" · ")
        sep1.setStyleSheet("color: #aab3bf;")
        h.addWidget(sep1)

        self.btn_fit = QPushButton("Ajuster (F)")
        self.btn_fit.setProperty("variant", "primary")
        self.btn_fit.setProperty("compact", True)
        self.btn_fit.setMinimumWidth(110)
        self.btn_fit.setMinimumHeight(28)
        self.btn_fit.setToolTip("Recadre la caméra sur le contenu chargé (F ou Home)")
        self.btn_fit.clicked.connect(self.fit_view)
        h.addWidget(self.btn_fit)

        sep2 = QLabel(" · ")
        sep2.setStyleSheet("color: #aab3bf;")
        h.addWidget(sep2)

        self.btn_show_profiles = QPushButton("Profils")
        self.btn_show_sweep = QPushButton("Surface")
        self.btn_show_wire = QPushButton("Fil")
        for b, attr, tip in (
            (self.btn_show_profiles, "_show_profiles", "Afficher/masquer les contours emplanture+saumon"),
            (self.btn_show_sweep,    "_show_sweep",    "Afficher/masquer la surface balayée"),
            (self.btn_show_wire,     "_show_wire",     "Afficher/masquer le fil tendu courant"),
        ):
            b.setCheckable(True)
            b.setChecked(True)
            b.setProperty("compact", True)
            b.setMinimumHeight(28)
            b.setMinimumWidth(80)
            b.setToolTip(tip)
            b.toggled.connect(lambda checked, a=attr: self._toggle_visibility(a, checked))
            h.addWidget(b)

        h.addStretch(1)

        self.lbl_info = QLabel("Aucun programme chargé")
        self.lbl_info.setStyleSheet("color: #9aa3ad;")
        f = self.lbl_info.font()
        f.setItalic(True)
        self.lbl_info.setFont(f)
        h.addWidget(self.lbl_info)
        return bar

    def _build_sim_toolbar(self) -> QWidget:
        """Barre de simulation en bas du panneau 3D."""
        bar = QFrame()
        bar.setStyleSheet(
            "QFrame { background-color: #1e2230; border-top: 1px solid #2c3142; }"
            "QLabel { color: #c8d0dd; }"
        )
        bar.setFixedHeight(48)
        h = QHBoxLayout(bar)
        h.setContentsMargins(10, 6, 10, 6)
        h.setSpacing(8)

        lbl = QLabel("🎬 Simulation :")
        lbl.setStyleSheet("color: #c8d0dd; font-weight: 600;")
        h.addWidget(lbl)

        self.btn_sim_play = QPushButton("▶")
        self.btn_sim_play.setProperty("variant", "primary")
        self.btn_sim_play.setProperty("compact", True)
        self.btn_sim_play.setFixedWidth(40)
        self.btn_sim_play.setMinimumHeight(28)
        self.btn_sim_play.setToolTip("Démarre / reprend la simulation")
        self.btn_sim_play.clicked.connect(self.sim_play_requested)
        h.addWidget(self.btn_sim_play)

        self.btn_sim_pause = QPushButton("⏸")
        self.btn_sim_pause.setProperty("compact", True)
        self.btn_sim_pause.setFixedWidth(40)
        self.btn_sim_pause.setMinimumHeight(28)
        self.btn_sim_pause.setToolTip("Pause")
        self.btn_sim_pause.clicked.connect(self.sim_pause_requested)
        h.addWidget(self.btn_sim_pause)

        self.btn_sim_stop = QPushButton("⏹")
        self.btn_sim_stop.setProperty("compact", True)
        self.btn_sim_stop.setFixedWidth(40)
        self.btn_sim_stop.setMinimumHeight(28)
        self.btn_sim_stop.setToolTip("Stop / retour au début")
        self.btn_sim_stop.clicked.connect(self.sim_stop_requested)
        h.addWidget(self.btn_sim_stop)

        h.addWidget(QLabel("Vitesse :"))
        self.cb_sim_speed = QComboBox()
        for label, val in (("1×", 1.0), ("5×", 5.0), ("10×", 10.0),
                           ("50×", 50.0), ("100×", 100.0), ("Max", 1000.0)):
            self.cb_sim_speed.addItem(label, val)
        self.cb_sim_speed.setCurrentIndex(1)  # 5×
        self.cb_sim_speed.setMinimumWidth(70)
        self.cb_sim_speed.currentIndexChanged.connect(
            lambda _i: self.sim_speed_changed.emit(self.cb_sim_speed.currentData())
        )
        h.addWidget(self.cb_sim_speed)

        self.sim_progress = QProgressBar()
        self.sim_progress.setRange(0, 1000)
        self.sim_progress.setValue(0)
        self.sim_progress.setTextVisible(False)
        self.sim_progress.setMinimumWidth(180)
        h.addWidget(self.sim_progress, 1)

        self.lbl_sim_time = QLabel("00:00 / 00:00")
        self.lbl_sim_time.setStyleSheet(
            "color: #c8d0dd; font-family: Consolas, monospace; font-weight: 600;"
        )
        h.addWidget(self.lbl_sim_time)

        self.lbl_sim_state = QLabel("Aucun programme")
        self.lbl_sim_state.setStyleSheet("color: #8a93a3; font-style: italic;")
        h.addWidget(self.lbl_sim_state)

        return bar

    # ---------- API simulation ----------

    @Slot(tuple)
    def on_sim_position(self, pos: tuple) -> None:
        """Position fournie par le simulateur (X, Y, Z, A en mm)."""
        if self._view is None or len(pos) < 4:
            return
        x, y, z, a = pos[0], pos[1], pos[2], pos[3]
        self._wire.setData(
            pos=np.array(
                [[x, 0.0, y], [a, self._wire_span, z]],
                dtype=np.float32,
            ),
        )

    @Slot(float)
    def on_sim_progress(self, pct: float) -> None:
        self.sim_progress.setValue(int(pct * 10))

    @Slot(float, float)
    def on_sim_elapsed(self, elapsed_s: float, total_s: float) -> None:
        def fmt(s: float) -> str:
            s = int(s)
            return f"{s // 60:02d}:{s % 60:02d}"
        self.lbl_sim_time.setText(f"{fmt(elapsed_s)} / {fmt(total_s)}")

    @Slot(str)
    def on_sim_state(self, state: str) -> None:
        labels = {
            "idle": ("Prêt", "#8a93a3"),
            "playing": ("En cours", "#1f9d55"),
            "paused": ("Pause", "#f59f00"),
            "finished": ("Terminé", "#1f6feb"),
        }
        text, color = labels.get(state, ("?", "#8a93a3"))
        self.lbl_sim_state.setText(text)
        self.lbl_sim_state.setStyleSheet(f"color: {color}; font-weight: 600;")
        self._sim_mode = (state == "playing" or state == "paused")
        # En sim mode on cache la wire firmware pour éviter conflits
        if state == "idle":
            self._sim_mode = False

    def _toggle_visibility(self, attr: str, checked: bool) -> None:
        setattr(self, attr, checked)
        # Refresh
        if self._view is None:
            return
        items = {
            "_show_profiles": [self._curve_root, self._curve_tip],
            "_show_sweep":    [self._sweep_cut, self._sweep_lead, self._sweep_rapid],
            "_show_wire":     [self._wire],
        }.get(attr, [])
        for it in items:
            it.setVisible(checked)

    # ---------- Vues pré-définies ----------

    def _set_view(self, name: str) -> None:
        if self._view is None:
            return
        if name not in _VIEW_PRESETS:
            return
        elev, azim, _label, _key = _VIEW_PRESETS[name]
        self._view.setCameraPosition(elevation=elev, azimuth=azim)

    def fit_view(self) -> None:
        """Ajuste la distance et le centre caméra pour englober tout le contenu."""
        if self._view is None:
            return
        if self._loaded_extents is None:
            return
        xmin, ymin, zmin, xmax, ymax, zmax = self._loaded_extents
        cx = 0.5 * (xmin + xmax)
        cy = 0.5 * (ymin + ymax)
        cz = 0.5 * (zmin + zmax)
        # rayon = demi-diagonale de la bbox
        radius = 0.5 * math.sqrt(
            (xmax - xmin) ** 2 + (ymax - ymin) ** 2 + (zmax - zmin) ** 2
        )
        if radius < 50:
            radius = 50
        # FOV par défaut de pyqtgraph ≈ 60° → distance ≈ radius / tan(30°) * 1.6 (marge)
        distance = radius / math.tan(math.radians(30.0)) * 1.5
        try:
            from pyqtgraph import Vector
            self._view.opts["center"] = Vector(cx, cy, cz)
        except Exception:
            self._view.opts["center"].setX(cx)
            self._view.opts["center"].setY(cy)
            self._view.opts["center"].setZ(cz)
        self._view.setCameraPosition(distance=distance)
        self._view.update()

    # ---------- Axe + labels ----------

    def _add_axis_labels(self) -> None:
        """Ajoute des labels X/Y/Z aux extrémités si la version de pyqtgraph
        supporte GLTextItem. Sinon on saute (rétrocompat)."""
        try:
            from pyqtgraph.opengl import GLTextItem
        except ImportError:
            return
        for txt, pos, color in (
            ("X corde",     (240, 0, 0),     (255, 200, 200)),
            ("Y envergure", (0, 240, 0),     (200, 255, 200)),
            ("Z épaisseur", (0, 0, 240),     (200, 200, 255)),
        ):
            try:
                t = GLTextItem(pos=pos, text=txt, color=color)
                self._view.addItem(t)
            except Exception:
                # Si l'API change selon la version, on évite le crash silencieusement.
                pass

    # ---------- API publique ----------

    def set_wire_span(self, span: float) -> None:
        self._wire_span = max(1.0, span)

    def set_program(self, parsed) -> None:
        if self._view is None:
            return
        moves = parsed.moves
        if not moves:
            empty = np.zeros((1, 3), dtype=np.float32)
            self._curve_root.setData(pos=empty)
            self._curve_tip.setData(pos=empty)
            self._sweep_cut.setData(pos=empty)
            self._sweep_lead.setData(pos=empty)
            self._sweep_rapid.setData(pos=empty)
            self._bbox.setData(pos=empty)
            self._loaded_extents = None
            self.lbl_info.setText("Aucun programme chargé")
            return

        L = self._wire_span
        root_pts = np.array([[m.pos["X"], 0.0, m.pos["Y"]] for m in moves], dtype=np.float32)
        tip_pts = np.array([[m.pos["A"], L, m.pos["Z"]] for m in moves], dtype=np.float32)
        self._curve_root.setData(pos=root_pts)
        self._curve_tip.setData(pos=tip_pts)

        # Catégorise chaque segment selon (rapid, wire_on) pour le code couleur
        sweep_cut: list = []
        sweep_lead: list = []
        sweep_rapid: list = []
        for i, m in enumerate(moves):
            pair = (root_pts[i], tip_pts[i])
            if m.rapid:
                sweep_rapid.extend(pair)
            elif m.wire_on:
                sweep_cut.extend(pair)
            else:
                sweep_lead.extend(pair)
        empty = np.zeros((1, 3), dtype=np.float32)
        self._sweep_cut.setData(
            pos=(np.array(sweep_cut, dtype=np.float32) if sweep_cut else empty)
        )
        self._sweep_lead.setData(
            pos=(np.array(sweep_lead, dtype=np.float32) if sweep_lead else empty)
        )
        self._sweep_rapid.setData(
            pos=(np.array(sweep_rapid, dtype=np.float32) if sweep_rapid else empty)
        )

        # Bbox pour visu + fit
        all_pts = np.vstack([root_pts, tip_pts])
        xmin, ymin, zmin = all_pts.min(axis=0)
        xmax, ymax, zmax = all_pts.max(axis=0)
        self._loaded_extents = (
            float(xmin), float(ymin), float(zmin),
            float(xmax), float(ymax), float(zmax),
        )
        self._bbox.setData(pos=_bbox_lines(xmin, ymin, zmin, xmax, ymax, zmax))

        self.lbl_info.setText(
            f"{len(moves)} points · corde {xmax - xmin:.0f} mm · "
            f"envergure {ymax - ymin:.0f} mm · épaisseur {zmax - zmin:.0f} mm"
        )
        self.fit_view()

    @Slot(tuple)
    def on_mpos(self, mpos: tuple) -> None:
        if self._view is None or len(mpos) < 4:
            return
        # En mode simulation, on ignore le firmware pour ne pas écraser
        # la position simulée.
        if self._sim_mode:
            return
        x, y, z, a = mpos[0], mpos[1], mpos[2], mpos[3]
        self._wire.setData(
            pos=np.array(
                [[x, 0.0, y], [a, self._wire_span, z]],
                dtype=np.float32,
            ),
        )


def _bbox_lines(xmin, ymin, zmin, xmax, ymax, zmax) -> np.ndarray:
    """Retourne les 12 segments d'une boîte englobante en mode 'lines'."""
    c = [
        (xmin, ymin, zmin), (xmax, ymin, zmin), (xmax, ymax, zmin), (xmin, ymax, zmin),
        (xmin, ymin, zmax), (xmax, ymin, zmax), (xmax, ymax, zmax), (xmin, ymax, zmax),
    ]
    edges = [
        (0, 1), (1, 2), (2, 3), (3, 0),  # base
        (4, 5), (5, 6), (6, 7), (7, 4),  # sommet
        (0, 4), (1, 5), (2, 6), (3, 7),  # arêtes verticales
    ]
    pts = np.empty((len(edges) * 2, 3), dtype=np.float32)
    for i, (a, b) in enumerate(edges):
        pts[i * 2] = c[a]
        pts[i * 2 + 1] = c[b]
    return pts
