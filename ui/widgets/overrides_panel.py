"""Panneaux d'overrides Grbl 1.1 : avance et broche/accessoire."""

from __future__ import annotations

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.grbl_protocol import (
    CMD_FEED_OVR_COARSE_MINUS,
    CMD_FEED_OVR_COARSE_PLUS,
    CMD_FEED_OVR_FINE_MINUS,
    CMD_FEED_OVR_FINE_PLUS,
    CMD_FEED_OVR_RESET,
    CMD_SPINDLE_OVR_COARSE_MINUS,
    CMD_SPINDLE_OVR_COARSE_PLUS,
    CMD_SPINDLE_OVR_FINE_MINUS,
    CMD_SPINDLE_OVR_FINE_PLUS,
    CMD_SPINDLE_OVR_RESET,
)
from ui.i18n import tr


class _OverrideRow(QGroupBox):
    cmd_requested = Signal(bytes)

    def __init__(self, title: str, cmds: dict[str, bytes], parent: QWidget | None = None):
        super().__init__(title, parent)
        self.lbl_pct = QLabel("100 %")
        self.lbl_pct.setMinimumWidth(56)
        f = self.lbl_pct.font()
        f.setBold(True)
        self.lbl_pct.setFont(f)

        h = QHBoxLayout(self)
        h.setSpacing(6)
        h.addWidget(self.lbl_pct)
        for label, cmd in cmds.items():
            b = QPushButton(label)
            b.setProperty("compact", True)
            b.setMinimumWidth(58)
            b.setMinimumHeight(28)
            b.clicked.connect(lambda _=False, c=cmd: self.cmd_requested.emit(c))
            h.addWidget(b, 1)

    @Slot(int)
    def set_percent(self, p: int) -> None:
        self.lbl_pct.setText(f"{p}%")


class OverridesPanel(QWidget):
    cmd_requested = Signal(bytes)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.feed = _OverrideRow(
            tr("Remplacer le taux d'avance"),
            {
                "-10%": CMD_FEED_OVR_COARSE_MINUS,
                "- 1%": CMD_FEED_OVR_FINE_MINUS,
                tr("Réinit"): CMD_FEED_OVR_RESET,
                "+ 1%": CMD_FEED_OVR_FINE_PLUS,
                "+10%": CMD_FEED_OVR_COARSE_PLUS,
            },
        )
        self.spindle = _OverrideRow(
            tr("Remplacer le paramètre actuel"),
            {
                "-10%": CMD_SPINDLE_OVR_COARSE_MINUS,
                "- 1%": CMD_SPINDLE_OVR_FINE_MINUS,
                tr("Réinit"): CMD_SPINDLE_OVR_RESET,
                "+ 1%": CMD_SPINDLE_OVR_FINE_PLUS,
                "+10%": CMD_SPINDLE_OVR_COARSE_PLUS,
            },
        )
        self.feed.cmd_requested.connect(self.cmd_requested)
        self.spindle.cmd_requested.connect(self.cmd_requested)

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(self.feed)
        v.addWidget(self.spindle)

    @Slot(int, int, int)
    def on_overrides(self, feed: int, rapid: int, spindle: int) -> None:
        self.feed.set_percent(feed)
        self.spindle.set_percent(spindle)
