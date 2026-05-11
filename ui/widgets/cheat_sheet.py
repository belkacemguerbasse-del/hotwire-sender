"""Dialog de l'aide-mémoire des raccourcis clavier (F1).

Liste tous les raccourcis actifs dans l'application, organisés par zone.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# Organisation : titre de section → liste de (touches, description)
SHORTCUTS = [
    ("Global", [
        ("F1", "Afficher ce panneau d'aide"),
        ("F9", "Afficher / masquer le panneau Caméra"),
    ]),
    ("Vue 3D", [
        ("1", "Vue Dessus"),
        ("2", "Vue Face"),
        ("3", "Vue Côté"),
        ("4", "Vue Iso (par défaut)"),
        ("F  ou  Home", "Ajuster automatiquement la caméra au contenu"),
        ("Clic gauche + glisser", "Orbiter autour du centre"),
        ("Clic droit + glisser", "Pan (translation latérale)"),
        ("Shift + clic gauche + glisser", "Pan (alternative)"),
        ("Clic milieu + glisser", "Pan (standard pyqtgraph)"),
        ("Molette", "Zoomer / dézoomer"),
    ]),
    ("Jogging clavier (cocher « Activer le clavier »)", [
        ("Flèche gauche / droite", "Chariot gauche, corde (axe X)"),
        ("Flèche haut / bas", "Chariot gauche, épaisseur (axe Y)"),
        ("Page Up / Page Down", "Chariot droit, corde (axe A)"),
    ]),
    ("Workflow recommandé", [
        ("Ouvrir / Slice", "Charger un G-code ou en générer un via le slicer"),
        ("🎬 Simuler", "Lance l'animation hors-ligne dans la Vue 3D"),
        ("▶ Lancer", "Démarre la coupe (et reprend après pause)"),
        ("⏸ Pause", "Pause logicielle (le bouton Lancer reprend ensuite)"),
        ("⏹ Stop", "Arrête net + soft-reset firmware"),
        ("ARRÊT D'URGENCE", "Coupe fil + reset firmware + stop runner (toujours visible)"),
    ]),
]


class CheatSheetDialog(QDialog):
    """Aide-mémoire des raccourcis. Ouvert via F1."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Aide-mémoire des raccourcis — F1")
        self.resize(640, 580)

        title = QLabel("⌨  Raccourcis clavier et workflow")
        f = title.font()
        f.setPointSize(14)
        f.setBold(True)
        title.setFont(f)

        # Construit le contenu HTML
        html_parts = ["<style>"
                      "h3 { color: #1f6feb; margin-top: 18px; margin-bottom: 4px; "
                      "  font-size: 11pt; letter-spacing: 0.5px; }"
                      "table { width: 100%; border-collapse: collapse; }"
                      "td.k { font-family: Consolas, monospace; font-weight: bold; "
                      "  background: #eaf2ff; color: #0d52c2; "
                      "  padding: 3px 8px; border-radius: 4px; white-space: nowrap; }"
                      "td.d { padding: 3px 10px; color: #1f2933; }"
                      "</style>"]
        for section_title, entries in SHORTCUTS:
            html_parts.append(f"<h3>{section_title}</h3>")
            html_parts.append("<table>")
            for keys, desc in entries:
                html_parts.append(
                    f"<tr><td class='k' width='35%'>{keys}</td>"
                    f"<td class='d'>{desc}</td></tr>"
                )
            html_parts.append("</table>")
        content_html = "".join(html_parts)

        content = QLabel(content_html)
        content.setTextFormat(Qt.RichText)
        content.setWordWrap(True)
        content.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        scroll = QScrollArea()
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        btn_close = QPushButton("Fermer")
        btn_close.setProperty("variant", "primary")
        btn_close.setMinimumHeight(34)
        btn_close.clicked.connect(self.close)

        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(btn_close)

        v = QVBoxLayout(self)
        v.setContentsMargins(16, 16, 16, 16)
        v.addWidget(title)
        v.addWidget(scroll, 1)
        v.addLayout(actions)
