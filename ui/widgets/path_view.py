"""Vues 2D : XY Wire Path (chariot gauche) et ZA Wire Path (chariot droit).

Trace :
- chemin programmé (G0 en gris pointillé, G1/G2/G3 en rouge)
- position courante (croix) avec mise à jour temps réel
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Slot
from PySide6.QtWidgets import QVBoxLayout, QWidget

from gcode.parser import ParseResult


class _SinglePathPlot(pg.PlotWidget):
    def __init__(self, title: str, x_letter: str, y_letter: str):
        super().__init__()
        self.x_letter = x_letter
        self.y_letter = y_letter
        self.setBackground("w")
        self.showGrid(x=True, y=True, alpha=0.3)
        self.setLabel("bottom", x_letter)
        self.setLabel("left", y_letter)
        self.setTitle(title)
        self.setAspectLocked(True)

        self._cut_curve = self.plot([], [], pen=pg.mkPen("r", width=2))
        self._rapid_curve = self.plot(
            [], [], pen=pg.mkPen((150, 150, 150), width=1, style=pg.QtCore.Qt.DashLine)
        )
        self._cursor = self.plot(
            [0], [0], pen=None, symbol="+", symbolSize=14,
            symbolPen=pg.mkPen("b", width=2)
        )

    def set_program(self, moves, x_key: str, y_key: str) -> None:
        cut_x: list[float] = []
        cut_y: list[float] = []
        rap_x: list[float] = []
        rap_y: list[float] = []
        last = (0.0, 0.0)
        for m in moves:
            x = m.pos.get(x_key, last[0])
            y = m.pos.get(y_key, last[1])
            if m.rapid:
                rap_x += [last[0], x, np.nan]
                rap_y += [last[1], y, np.nan]
            else:
                cut_x += [last[0], x, np.nan]
                cut_y += [last[1], y, np.nan]
            last = (x, y)
        self._cut_curve.setData(cut_x, cut_y, connect="finite")
        self._rapid_curve.setData(rap_x, rap_y, connect="finite")
        if cut_x or rap_x:
            self.autoRange()

    def set_cursor(self, x: float, y: float) -> None:
        self._cursor.setData([x], [y])


class PathView(QWidget):
    """Composite avec les 2 plots XY (en haut) et AZ (en bas).

    Convention : sur chaque chariot, l'axe horizontal = sens de la corde, l'axe
    vertical = sens de l'épaisseur. Côté gauche (X,Y), côté droit (A,Z).
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.xy = _SinglePathPlot("XY Wire Path", "X", "Y")
        # Sur le chariot droit : A = horizontal (corde), Z = vertical (épaisseur)
        self.za = _SinglePathPlot("AZ Wire Path (chariot droit)", "A", "Z")

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(self.xy)
        v.addWidget(self.za)

    def set_program(self, parsed: ParseResult) -> None:
        self.xy.set_program(parsed.moves, "X", "Y")
        self.za.set_program(parsed.moves, "A", "Z")

    @Slot(tuple)
    def on_mpos(self, mpos: tuple[float, ...]) -> None:
        # mpos suit l'ordre firmware : X, Y, Z, A → indices 0,1,2,3
        if len(mpos) >= 2:
            self.xy.set_cursor(mpos[0], mpos[1])
        if len(mpos) >= 4:
            # Plot AZ : A en X-axe (mpos[3]), Z en Y-axe (mpos[2])
            self.za.set_cursor(mpos[3], mpos[2])
