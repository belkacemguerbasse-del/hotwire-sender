"""Ligne de commande manuelle (MDI) avec historique haut/bas."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QWidget,
)


class _HistoryEdit(QLineEdit):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._history: list[str] = []
        self._idx = 0

    def push(self, line: str) -> None:
        if line and (not self._history or self._history[-1] != line):
            self._history.append(line)
        self._idx = len(self._history)

    def keyPressEvent(self, ev: QKeyEvent) -> None:
        if ev.key() == Qt.Key_Up and self._history:
            self._idx = max(0, self._idx - 1)
            self.setText(self._history[self._idx])
            return
        if ev.key() == Qt.Key_Down:
            if self._history and self._idx < len(self._history) - 1:
                self._idx += 1
                self.setText(self._history[self._idx])
            else:
                self._idx = len(self._history)
                self.clear()
            return
        super().keyPressEvent(ev)


class MdiPanel(QGroupBox):
    line_submitted = Signal(str)
    slice_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__("MDI", parent)
        self.edit = _HistoryEdit()
        self.edit.setPlaceholderText("Commande manuelle…")
        self.btn = QPushButton("Envoyer")
        self.btn_slice = QPushButton("Slice")

        self.edit.returnPressed.connect(self._submit)
        self.btn.clicked.connect(self._submit)
        self.btn_slice.clicked.connect(self.slice_requested)

        h = QHBoxLayout(self)
        h.addWidget(self.edit, 1)
        h.addWidget(self.btn)
        h.addWidget(self.btn_slice)

    def _submit(self) -> None:
        line = self.edit.text().strip()
        if not line:
            return
        self.edit.push(line)
        self.line_submitted.emit(line)
        self.edit.clear()
