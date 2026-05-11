"""Onglet Macros : liste éditable de séquences G-code à exécuter en 1 clic."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core.macros import Macro, MacroStore


class MacrosTab(QWidget):
    """Composite : liste à gauche, édition + exécution à droite."""

    send_lines_requested = Signal(list)   # liste de lignes G-code à envoyer

    def __init__(self, store: MacroStore, parent: QWidget | None = None):
        super().__init__(parent)
        self.store = store
        self._build_ui()
        self.store.changed.connect(self._refresh_list)
        self._refresh_list()

    def _build_ui(self) -> None:
        # ---- Liste à gauche ----
        self.list_w = QListWidget()
        self.list_w.currentRowChanged.connect(self._on_select)

        self.btn_add = QPushButton("➕  Ajouter")
        self.btn_add.setMinimumHeight(30)
        self.btn_add.clicked.connect(self._on_add)

        self.btn_delete = QPushButton("🗑  Supprimer")
        self.btn_delete.setMinimumHeight(30)
        self.btn_delete.clicked.connect(self._on_delete)

        list_actions = QHBoxLayout()
        list_actions.addWidget(self.btn_add)
        list_actions.addWidget(self.btn_delete)

        left = QWidget()
        v_left = QVBoxLayout(left)
        v_left.setContentsMargins(8, 8, 8, 8)
        lbl_list = QLabel("Mes macros")
        f = lbl_list.font()
        f.setBold(True)
        f.setPointSize(11)
        lbl_list.setFont(f)
        v_left.addWidget(lbl_list)
        v_left.addWidget(self.list_w, 1)
        v_left.addLayout(list_actions)

        # ---- Édition à droite ----
        self.le_name = QLineEdit()
        self.le_name.setPlaceholderText("Nom de la macro")
        self.le_name.editingFinished.connect(self._on_save_current)

        self.le_desc = QLineEdit()
        self.le_desc.setPlaceholderText("Description (optionnelle)")
        self.le_desc.editingFinished.connect(self._on_save_current)

        self.te_lines = QPlainTextEdit()
        self.te_lines.setPlaceholderText(
            "Une ligne G-code par ligne, ex:\n"
            "G90\n"
            "G0 X0 Y80\n"
            "M3 S500\n"
            "G4 P3\n"
            "M5"
        )
        self.te_lines.setFont(QFont("Consolas", 10))
        self.te_lines.focusOutEvent = self._wrap_focus_out(self.te_lines.focusOutEvent)

        self.btn_run = QPushButton("▶  Exécuter cette macro")
        self.btn_run.setProperty("variant", "primary")
        self.btn_run.setMinimumHeight(38)
        self.btn_run.setToolTip(
            "Envoie toutes les lignes de la macro au firmware (séquence)."
        )
        self.btn_run.clicked.connect(self._on_run)

        edit_box = QWidget()
        v_edit = QVBoxLayout(edit_box)
        v_edit.setContentsMargins(8, 8, 8, 8)
        v_edit.addWidget(QLabel("Nom :"))
        v_edit.addWidget(self.le_name)
        v_edit.addWidget(QLabel("Description :"))
        v_edit.addWidget(self.le_desc)
        v_edit.addWidget(QLabel("Lignes G-code (une par ligne) :"))
        v_edit.addWidget(self.te_lines, 1)
        v_edit.addWidget(self.btn_run)

        # Layout général
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(edit_box)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([260, 600])

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(splitter)

        self._editing_index: int = -1
        self._set_edit_enabled(False)

    def _wrap_focus_out(self, original):
        """Wrap pour sauvegarder le contenu du textarea quand on perd le focus."""
        def handler(ev):
            self._on_save_current()
            original(ev)
        return handler

    def _set_edit_enabled(self, enabled: bool) -> None:
        for w in (self.le_name, self.le_desc, self.te_lines, self.btn_run, self.btn_delete):
            w.setEnabled(enabled)

    @Slot()
    def _refresh_list(self) -> None:
        cur_row = self.list_w.currentRow()
        self.list_w.blockSignals(True)
        self.list_w.clear()
        for m in self.store.all():
            self.list_w.addItem(QListWidgetItem(m.name or "(sans nom)"))
        # Restaure la sélection si possible
        if 0 <= cur_row < self.list_w.count():
            self.list_w.setCurrentRow(cur_row)
        elif self.list_w.count() > 0:
            self.list_w.setCurrentRow(0)
        self.list_w.blockSignals(False)
        # Force le chargement du contenu de la macro sélectionnée
        self._on_select(self.list_w.currentRow())

    @Slot(int)
    def _on_select(self, row: int) -> None:
        macros = self.store.all()
        if not (0 <= row < len(macros)):
            self._editing_index = -1
            self.le_name.clear()
            self.le_desc.clear()
            self.te_lines.clear()
            self._set_edit_enabled(False)
            return
        m = macros[row]
        self._editing_index = row
        self.le_name.setText(m.name)
        self.le_desc.setText(m.description)
        self.te_lines.setPlainText("\n".join(m.lines))
        self._set_edit_enabled(True)

    def _current_macro_from_form(self) -> Macro:
        lines = [ln.rstrip()
                 for ln in self.te_lines.toPlainText().splitlines()
                 if ln.strip()]
        return Macro(
            name=self.le_name.text().strip() or "(sans nom)",
            description=self.le_desc.text().strip(),
            lines=lines,
        )

    def _on_save_current(self) -> None:
        if self._editing_index < 0:
            return
        self.store.update(self._editing_index, self._current_macro_from_form())

    def _on_add(self) -> None:
        new = Macro(name="Nouvelle macro", description="", lines=["G90"])
        self.store.add(new)
        # Sélectionne la nouvelle
        self.list_w.setCurrentRow(len(self.store.all()) - 1)

    def _on_delete(self) -> None:
        if self._editing_index < 0:
            return
        name = self.le_name.text() or "(sans nom)"
        ans = QMessageBox.question(
            self, "Supprimer la macro",
            f"Supprimer la macro « {name} » ?\nCette action est irréversible.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if ans == QMessageBox.Yes:
            self.store.remove(self._editing_index)

    def _on_run(self) -> None:
        m = self._current_macro_from_form()
        if not m.lines:
            QMessageBox.information(
                self, "Macro vide",
                "Cette macro ne contient aucune ligne à envoyer."
            )
            return
        # Sauve d'abord (au cas où le user a édité sans valider)
        self._on_save_current()
        self.send_lines_requested.emit(list(m.lines))
