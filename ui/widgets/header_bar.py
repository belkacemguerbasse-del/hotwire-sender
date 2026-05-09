"""Barre d'en-tête toujours visible.

Affiche :
- nom de l'app + axes (ex: "HotWire Sender — XYZA")
- indicateur de connexion : pastille colorée + nom du port
- pastille d'état machine (Idle / Run / Hold / Alarm…) avec couleur sémantique
- bouton ARRÊT D'URGENCE rouge (Ctrl-X soft reset firmware)

Tout reste accessible quel que soit l'onglet courant.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from ui.theme import COLORS, card_shadow, ui_font, update_shadow_color


_STATE_LABEL_FR = {
    "Idle": "PRÊT",
    "Run": "EN COURS",
    "Hold": "PAUSE",
    "Jog": "JOG",
    "Alarm": "ALARME",
    "Door": "PORTE",
    "Check": "VÉRIF",
    "Home": "HOMING",
    "Sleep": "VEILLE",
    "Unknown": "INCONNU",
}


def _state_color(state: str) -> str:
    key = "state_" + state.lower()
    return COLORS.get(key, COLORS["state_unknown"])


class HeaderBar(QFrame):
    estop_requested = Signal()
    camera_toggle_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("headerBar")
        self.setFrameShape(QFrame.NoFrame)
        self.setFixedHeight(64)

        # --- Titre ---
        self.lbl_title = QLabel("HotWire Sender")
        self.lbl_title.setFont(ui_font(13, bold=True))
        self.lbl_subtitle = QLabel("CNC fil chaud · 4 axes XYZA")
        self.lbl_subtitle.setFont(ui_font(9))
        self.lbl_subtitle.setStyleSheet(f"color: {COLORS['text_muted']};")
        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(0)
        title_box.addWidget(self.lbl_title)
        title_box.addWidget(self.lbl_subtitle)

        # --- Indicateur de connexion ---
        self.dot = QLabel("●")
        self.dot.setObjectName("connectionDot")
        self.dot.setStyleSheet(f"color: {COLORS['text_subtle']};")
        self.lbl_conn = QLabel("Non connecté")
        self.lbl_conn.setFont(ui_font(10, bold=True))
        conn_box = QHBoxLayout()
        conn_box.setContentsMargins(0, 0, 0, 0)
        conn_box.setSpacing(8)
        conn_box.addWidget(self.dot)
        conn_box.addWidget(self.lbl_conn)

        # --- Pastille d'état ---
        self.pill = QLabel("INCONNU")
        self.pill.setObjectName("statePill")
        self.pill.setAlignment(Qt.AlignCenter)
        self.pill.setMinimumWidth(140)
        self.pill.setMinimumHeight(32)
        self._set_state_color(COLORS["state_unknown"])
        # Ombre colorée qui suit l'état (mise à jour dans on_state)
        self._pill_shadow = card_shadow(
            self.pill, blur=18, offset_y=0,
            alpha=120, color=COLORS["state_unknown"],
        )

        # --- Bouton Caméra ---
        self.btn_camera = QPushButton("Caméra")
        self.btn_camera.setCheckable(True)
        self.btn_camera.setMinimumHeight(40)
        self.btn_camera.setMinimumWidth(110)
        self.btn_camera.setToolTip("Afficher/masquer le panneau caméra (raccourci F9)")
        self.btn_camera.setFont(ui_font(10, bold=True))
        self.btn_camera.clicked.connect(self.camera_toggle_requested)

        # --- Bouton ARRÊT ---
        self.btn_estop = QPushButton("ARRÊT D'URGENCE")
        self.btn_estop.setProperty("variant", "danger")
        self.btn_estop.setMinimumHeight(40)
        self.btn_estop.setMinimumWidth(190)
        self.btn_estop.setToolTip(
            "Soft reset firmware (Ctrl-X). Coupe le fil et stoppe tout mouvement."
        )
        self.btn_estop.setFont(ui_font(10, bold=True))
        self.btn_estop.clicked.connect(self.estop_requested)

        h = QHBoxLayout(self)
        h.setContentsMargins(16, 6, 16, 6)
        h.setSpacing(16)
        h.addLayout(title_box)
        h.addItem(QSpacerItem(40, 1, QSizePolicy.Expanding, QSizePolicy.Minimum))
        h.addLayout(conn_box)
        h.addWidget(self.pill)
        h.addWidget(self.btn_camera)
        h.addWidget(self.btn_estop)

    def _set_state_color(self, hex_color: str) -> None:
        self.pill.setStyleSheet(
            f"QLabel#statePill {{"
            f"  background-color: {hex_color};"
            f"  color: white;"
            f"  border-radius: 16px;"
            f"  padding: 4px 18px;"
            f"  font-weight: 700;"
            f"  letter-spacing: 1px;"
            f"}}"
        )

    # ---- Slots ----

    @Slot(str)
    def on_state(self, state: str) -> None:
        label = _STATE_LABEL_FR.get(state, state.upper())
        color = _state_color(state)
        self.pill.setText(label)
        self._set_state_color(color)
        update_shadow_color(self._pill_shadow, color, alpha=140)

    def set_axes(self, axes_text: str) -> None:
        self.lbl_subtitle.setText(f"CNC fil chaud · {axes_text}")

    @Slot(str)
    def on_connected(self, port: str) -> None:
        self.dot.setStyleSheet(f"color: {COLORS['success']};")
        self.lbl_conn.setText(f"Connecté · {port}")

    @Slot()
    def on_disconnected(self) -> None:
        self.dot.setStyleSheet(f"color: {COLORS['text_subtle']};")
        self.lbl_conn.setText("Non connecté")
        self.on_state("Unknown")
