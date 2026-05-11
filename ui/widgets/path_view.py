"""Vues 2D : XY Wire Path (chariot gauche) et AZ Wire Path (chariot droit).

Trace 3 catégories de mouvements en couleurs distinctes :
- G0 (rapide) : VERT pointillé fin → déplacements hors mousse
- G1 fil ON  : ROUGE plein épais → coupe effective dans la mousse
- G1 fil OFF : GRIS pointillé → lead-in / lead-out / approche

+ position courante (croix bleue) animée par les status reports.
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

        # G1 fil ON : rouge plein épais (coupe réelle)
        self._cut_curve = self.plot(
            [], [], pen=pg.mkPen("#d6363d", width=2.4)
        )
        # G1 fil OFF : gris pointillé (lead-in / lead-out)
        self._lead_curve = self.plot(
            [], [], pen=pg.mkPen((130, 130, 130), width=1.4,
                                 style=pg.QtCore.Qt.DashLine)
        )
        # G0 rapide : vert pointillé fin (déplacements à vide)
        self._rapid_curve = self.plot(
            [], [], pen=pg.mkPen((30, 157, 85, 200), width=1,
                                 style=pg.QtCore.Qt.DotLine)
        )
        self._cursor = self.plot(
            [0], [0], pen=None, symbol="+", symbolSize=14,
            symbolPen=pg.mkPen("#1f6feb", width=2)
        )

    def set_program(self, moves, x_key: str, y_key: str) -> None:
        cut_x: list[float] = []      # G1 + fil ON
        cut_y: list[float] = []
        lead_x: list[float] = []     # G1 + fil OFF
        lead_y: list[float] = []
        rap_x: list[float] = []      # G0
        rap_y: list[float] = []
        last = (0.0, 0.0)
        for m in moves:
            x = m.pos.get(x_key, last[0])
            y = m.pos.get(y_key, last[1])
            if m.rapid:
                rap_x += [last[0], x, np.nan]
                rap_y += [last[1], y, np.nan]
            elif m.wire_on:
                cut_x += [last[0], x, np.nan]
                cut_y += [last[1], y, np.nan]
            else:
                lead_x += [last[0], x, np.nan]
                lead_y += [last[1], y, np.nan]
            last = (x, y)
        self._cut_curve.setData(cut_x, cut_y, connect="finite")
        self._lead_curve.setData(lead_x, lead_y, connect="finite")
        self._rapid_curve.setData(rap_x, rap_y, connect="finite")
        if cut_x or rap_x or lead_x:
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
