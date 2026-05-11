"""Panneau de log Grbl. Le badge d'état est désormais dans la HeaderBar.

Ce widget conserve l'historique des messages reçus / envoyés (verbose ou non),
auto-scroll uniquement si l'utilisateur est déjà en bas, bouton effacer.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.i18n import tr
from ui.theme import COLORS, mono_font


class StatusPanel(QGroupBox):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(tr("Journal Grbl"), parent)

        self.cb_verbose = QCheckBox(tr("Verbeux"))
        self.cb_verbose.setToolTip(
            tr("Afficher également les rapports d'état périodiques et les ack 'ok'.")
        )

        self.btn_clear = QPushButton(tr("Effacer"))
        self.btn_clear.setFixedWidth(80)

        top = QHBoxLayout()
        top.addWidget(self.cb_verbose, 1)
        top.addWidget(self.btn_clear)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        self.log.setFont(mono_font(9))

        self.btn_clear.clicked.connect(self.log.clear)

        v = QVBoxLayout(self)
        v.setSpacing(6)
        v.addLayout(top)
        v.addWidget(self.log, 1)

    # ---- Mode "compatibilité" pour le state (ancien header) ----
    # On conserve une no-op pour ne pas casser les wires existants.
    @Slot(str)
    def on_state(self, state: str) -> None:
        return

    def _append(self, text: str, color: str | None = None) -> None:
        sb = self.log.verticalScrollBar()
        was_at_bottom = sb.value() >= sb.maximum() - 4
        if color:
            self.log.appendHtml(
                f'<span style="color:{color}; white-space:pre;">'
                f'{_escape(text)}</span>'
            )
        else:
            self.log.appendPlainText(text)
        if was_at_bottom:
            sb.setValue(sb.maximum())

    @Slot(str)
    def append_rx(self, line: str) -> None:
        if not self.cb_verbose.isChecked():
            if line.startswith("<") and line.endswith(">"):
                return
            if line == "ok":
                return
        col = None
        if line.lower().startswith("alarm"):
            col = COLORS["danger"]
        elif line.lower().startswith("error"):
            col = COLORS["danger"]
        elif line.startswith("[VER:") or line.startswith("[OPT:") or line.startswith("[AXS:") or line.startswith("Grbl"):
            col = COLORS["primary"]
        self._append(f"<  {line}", color=col)

    @Slot(str)
    def append_tx(self, line: str) -> None:
        if not self.cb_verbose.isChecked():
            return
        self._append(f">  {line}", color=COLORS["text_muted"])

    @Slot(str)
    def append_info(self, msg: str) -> None:
        self._append(f"#  {msg}", color=COLORS["primary"])


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
