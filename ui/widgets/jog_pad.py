"""Trois pavés de jog : chariot gauche (XY), synchro deux chariots, chariot droit (ZA).

On utilise les jog Grbl 1.1 : `$J=G91 G21 X.. Y.. F..` qui ne perturbent pas
le parser g-code modal. Le bouton "0" (ramener à 0) émet un G90 + déplacement
absolu vers 0 sur les axes concernés.
"""

from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from ui.i18n import tr

JOG_DISTANCES = (100.0, 50.0, 10.0, 1.0)
JOG_FEEDS = (300, 200, 100, 50)


class JogSettings(QGroupBox):
    distance_changed = Signal(float)
    feed_changed = Signal(int)
    keyboard_toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(tr("Jogging"), parent)
        self.distance = 10.0
        self.feed = 300

        gb_dist = QGroupBox(tr("Distance"))
        gd = QVBoxLayout(gb_dist)
        self._dist_group = QButtonGroup(self)
        for i, d in enumerate(JOG_DISTANCES):
            rb = QRadioButton(f"{d:g}")
            if d == self.distance:
                rb.setChecked(True)
            rb.toggled.connect(lambda chk, val=d: chk and self._set_distance(val))
            self._dist_group.addButton(rb)
            gd.addWidget(rb)

        gb_feed = QGroupBox(tr("Vit. Avance"))
        gf = QVBoxLayout(gb_feed)
        self._feed_group = QButtonGroup(self)
        for f in JOG_FEEDS:
            rb = QRadioButton(str(f))
            if f == self.feed:
                rb.setChecked(True)
            rb.toggled.connect(lambda chk, val=f: chk and self._set_feed(val))
            self._feed_group.addButton(rb)
            gf.addWidget(rb)

        self.cb_metric = QCheckBox(tr("Métrique"))
        self.cb_metric.setChecked(True)
        self.cb_keyboard = QCheckBox(tr("Activer le clavier"))
        self.cb_keyboard.toggled.connect(self.keyboard_toggled)

        right = QVBoxLayout()
        right.addWidget(self.cb_metric)
        right.addWidget(self.cb_keyboard)
        right.addStretch(1)

        h = QHBoxLayout(self)
        h.addWidget(gb_dist)
        h.addWidget(gb_feed)
        h.addLayout(right, 1)

    def _set_distance(self, d: float) -> None:
        self.distance = d
        self.distance_changed.emit(d)

    def _set_feed(self, f: int) -> None:
        self.feed = f
        self.feed_changed.emit(f)


class _Pad(QGroupBox):
    """Pavé directionnel générique : 4 axes nominaux mappés sur 4 boutons +/-.

    horizontal_axis = lettre déplacée par les boutons gauche/droite.
    vertical_axis   = lettre déplacée par les boutons haut/bas.
    """

    jog_requested = Signal(str, float)  # axis_letter, signed_distance
    zero_requested = Signal()
    goto_zero_requested = Signal()

    def __init__(
        self,
        title: str,
        h_axis: str,
        v_axis: str,
        zero_label: str | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(title, parent)
        self.h_axis = h_axis
        self.v_axis = v_axis

        self.btn_up = QPushButton(f"{v_axis}+")
        self.btn_down = QPushButton(f"{v_axis}-")
        self.btn_left = QPushButton(f"{h_axis}-")
        self.btn_right = QPushButton(f"{h_axis}+")
        self.btn_zero = QPushButton("0")
        zl = zero_label if zero_label is not None else tr("Aller à 0")
        self.btn_goto_zero = QPushButton(zl.replace("\n", " "))
        for b in (
            self.btn_up, self.btn_down, self.btn_left, self.btn_right, self.btn_zero,
        ):
            b.setProperty("pad", True)
            b.setMinimumSize(56, 40)
        self.btn_goto_zero.setProperty("compact", True)
        self.btn_goto_zero.setMinimumHeight(30)

        g = QGridLayout(self)
        g.addWidget(self.btn_up, 0, 1)
        g.addWidget(self.btn_left, 1, 0)
        g.addWidget(self.btn_zero, 1, 1)
        g.addWidget(self.btn_right, 1, 2)
        g.addWidget(self.btn_down, 2, 1)
        g.addWidget(self.btn_goto_zero, 3, 0, 1, 3)

        self.btn_up.clicked.connect(lambda: self.jog_requested.emit(self.v_axis, +1.0))
        self.btn_down.clicked.connect(lambda: self.jog_requested.emit(self.v_axis, -1.0))
        self.btn_left.clicked.connect(lambda: self.jog_requested.emit(self.h_axis, -1.0))
        self.btn_right.clicked.connect(lambda: self.jog_requested.emit(self.h_axis, +1.0))
        self.btn_zero.clicked.connect(self.zero_requested)
        self.btn_goto_zero.clicked.connect(self.goto_zero_requested)


class _SyncPad(QGroupBox):
    """Pavé synchro : déplace simultanément les 2 chariots.

    Convention : flèche → → bouge X (gauche) et Z (droit) du même delta.
                ↑ → bouge Y et A.
    """

    jog_xz_requested = Signal(float)  # delta horizontal
    jog_ya_requested = Signal(float)  # delta vertical
    zero_all_requested = Signal()
    goto_zero_all_requested = Signal()
    display_reset_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(tr("jogger les deux chariots"), parent)

        self.btn_up = QPushButton("↑")
        self.btn_down = QPushButton("↓")
        self.btn_left = QPushButton("←")
        self.btn_right = QPushButton("→")
        self.btn_zero = QPushButton("0")
        self.btn_goto_zero = QPushButton(tr("Aller à 0 (tout)"))
        self.btn_goto_zero.setToolTip(tr("Déplace les 4 axes au zéro WCO actuel"))
        self.btn_reset = QPushButton(tr("Reset affichage"))
        self.btn_reset.setToolTip(tr("Remet la position à zéro côté affichage uniquement"))

        for b in (
            self.btn_up, self.btn_down, self.btn_left, self.btn_right, self.btn_zero,
        ):
            b.setProperty("pad", True)
            b.setMinimumSize(56, 40)
        for b in (self.btn_goto_zero, self.btn_reset):
            b.setProperty("compact", True)
            b.setMinimumHeight(30)

        g = QGridLayout(self)
        g.addWidget(self.btn_up, 0, 1)
        g.addWidget(self.btn_left, 1, 0)
        g.addWidget(self.btn_zero, 1, 1)
        g.addWidget(self.btn_right, 1, 2)
        g.addWidget(self.btn_down, 2, 1)
        g.addWidget(self.btn_goto_zero, 3, 0, 1, 3)
        g.addWidget(self.btn_reset, 4, 0, 1, 3)

        self.btn_up.clicked.connect(lambda: self.jog_ya_requested.emit(+1.0))
        self.btn_down.clicked.connect(lambda: self.jog_ya_requested.emit(-1.0))
        self.btn_left.clicked.connect(lambda: self.jog_xz_requested.emit(-1.0))
        self.btn_right.clicked.connect(lambda: self.jog_xz_requested.emit(+1.0))
        self.btn_zero.clicked.connect(self.zero_all_requested)
        self.btn_goto_zero.clicked.connect(self.goto_zero_all_requested)
        self.btn_reset.clicked.connect(self.display_reset_requested)


class JogPanel(QWidget):
    """Bloc complet : 3 pavés + réglages."""

    jog_axis = Signal(str, float, float)   # axis, signed_distance, feed
    jog_pair = Signal(str, str, float, float, float)  # ax1, ax2, d1, d2, feed
    zero_axes = Signal(tuple)              # tuple of axis letters to zero
    goto_zero_axes = Signal(tuple)
    display_reset = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        # Convention : sur chaque chariot, l'axe horizontal = sens de la corde,
        # l'axe vertical = sens de l'épaisseur. Sur le chariot droit, le firmware
        # (et HotwireWing3D / GrblHotWire-Mega-5X d'origine) utilisent A = horizontal,
        # Z = vertical.
        self.left = _Pad(tr("Chariot gauche"), h_axis="X", v_axis="Y", zero_label=tr("Aller à\n0 XY"))
        self.right = _Pad(tr("Chariot droit"), h_axis="A", v_axis="Z", zero_label=tr("Aller à\n0 ZA"))
        self.sync = _SyncPad()
        self.settings = JogSettings()

        self.left.jog_requested.connect(lambda ax, s: self._emit_axis(ax, s))
        self.right.jog_requested.connect(lambda ax, s: self._emit_axis(ax, s))
        # Synchro : flèche horizontale = corde des 2 chariots (X + A)
        # flèche verticale = épaisseur des 2 chariots (Y + Z)
        self.sync.jog_xz_requested.connect(lambda s: self._emit_pair("X", "A", s, s))
        self.sync.jog_ya_requested.connect(lambda s: self._emit_pair("Y", "Z", s, s))

        self.left.zero_requested.connect(lambda: self.zero_axes.emit(("X", "Y")))
        self.right.zero_requested.connect(lambda: self.zero_axes.emit(("A", "Z")))
        self.sync.zero_all_requested.connect(lambda: self.zero_axes.emit(("X", "Y", "Z", "A")))

        self.left.goto_zero_requested.connect(lambda: self.goto_zero_axes.emit(("X", "Y")))
        self.right.goto_zero_requested.connect(lambda: self.goto_zero_axes.emit(("A", "Z")))
        self.sync.goto_zero_all_requested.connect(lambda: self.goto_zero_axes.emit(("X", "Y", "Z", "A")))
        self.sync.display_reset_requested.connect(self.display_reset)

        h = QHBoxLayout()
        h.addWidget(self.left)
        h.addWidget(self.sync)
        h.addWidget(self.right)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(h)
        outer.addWidget(self.settings)

    def _emit_axis(self, axis: str, sign: float) -> None:
        d = sign * self.settings.distance
        self.jog_axis.emit(axis, d, float(self.settings.feed))

    def _emit_pair(self, a1: str, a2: str, s1: float, s2: float) -> None:
        d = self.settings.distance
        self.jog_pair.emit(a1, a2, s1 * d, s2 * d, float(self.settings.feed))

    def keyPressEvent(self, event):
        if not self.settings.cb_keyboard.isChecked():
            return super().keyPressEvent(event)
        k = event.key()
        if k == Qt.Key_Left:
            self._emit_axis("X", -1.0)
        elif k == Qt.Key_Right:
            self._emit_axis("X", +1.0)
        elif k == Qt.Key_Up:
            self._emit_axis("Y", +1.0)
        elif k == Qt.Key_Down:
            self._emit_axis("Y", -1.0)
        elif k == Qt.Key_PageUp:
            self._emit_axis("A", +1.0)
        elif k == Qt.Key_PageDown:
            self._emit_axis("A", -1.0)
        else:
            return super().keyPressEvent(event)
        event.accept()
