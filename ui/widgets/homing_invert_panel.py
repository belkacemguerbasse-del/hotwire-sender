"""Éditeur visuel du masque `$23` (sens du homing par axe).

Le mask `$23` est un entier dont chaque bit représente un axe :
- bit 0 (= 1)  : X
- bit 1 (= 2)  : Y
- bit 2 (= 4)  : Z
- bit 3 (= 8)  : A
- bit 4 (= 16) : B
- bit 5 (= 32) : C

Cocher une case = inverser le sens de homing pour cet axe.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.theme import COLORS

AXIS_NAMES = ("X", "Y", "Z", "A")


class HomingInvertPanel(QGroupBox):
    """Émet `$23=N` quand l'utilisateur clique Appliquer."""

    write_setting_requested = Signal(str)
    refresh_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Inverser direction homing ($23)", parent)

        self.checks: list[QCheckBox] = []
        boxes_row = QHBoxLayout()
        for ax in AXIS_NAMES:
            cb = QCheckBox(ax)
            cb.setStyleSheet("font-weight: 700;")
            self.checks.append(cb)
            boxes_row.addWidget(cb)
        boxes_row.addStretch(1)

        self.lbl_value = QLabel("Valeur courante : —")
        self.lbl_value.setStyleSheet(f"color: {COLORS['text_muted']};")

        self.btn_apply = QPushButton("Appliquer")
        self.btn_apply.setProperty("variant", "primary")
        self.btn_apply.setMinimumHeight(28)
        self.btn_apply.clicked.connect(self._apply)

        self.btn_refresh = QPushButton("Recharger")
        self.btn_refresh.setMinimumHeight(28)
        self.btn_refresh.clicked.connect(self.refresh_requested)

        actions = QHBoxLayout()
        actions.addWidget(self.lbl_value, 1)
        actions.addWidget(self.btn_refresh)
        actions.addWidget(self.btn_apply)

        v = QVBoxLayout(self)
        v.addLayout(boxes_row)
        v.addLayout(actions)

    @Slot(int)
    def set_mask(self, value: int) -> None:
        """Mise à jour visuelle quand un `$23=N` arrive."""
        self.lbl_value.setText(f"Valeur courante : {value}")
        for i, cb in enumerate(self.checks):
            cb.blockSignals(True)
            cb.setChecked(bool(value & (1 << i)))
            cb.blockSignals(False)

    def _compute_mask(self) -> int:
        return sum((1 << i) for i, cb in enumerate(self.checks) if cb.isChecked())

    def _apply(self) -> None:
        v = self._compute_mask()
        self.lbl_value.setText(f"Valeur courante : {v}")
        self.write_setting_requested.emit(f"$23={v}")
