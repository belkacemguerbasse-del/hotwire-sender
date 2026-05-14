"""Contrôle du ventilateur de refroidissement RAMPS 1.4.

== Logique de contrôle (à respecter strictement) ==

Le ventilateur est piloté par le coolant flood de Grbl, qui sort sur le
pin D10 du RAMPS (12V). On utilise les g-codes Grbl :

  - `M8`  → coolant flood ON   (set explicite, pas un toggle)
  - `M9`  → coolant off        (set explicite)

On N'UTILISE PAS la commande temps-réel `0xA0` (CMD_COOLANT_FLOOD_TOGGLE)
car c'est un TOGGLE : si l'état UI diverge de l'état réel matériel, chaque
clic inverse l'écart au lieu de le corriger. Avec M8/M9 on a des commandes
explicites idempotentes.

== Synchronisation UI ↔ matériel ==

L'état affiché côté UI est synchronisé avec l'état matériel réel via le
status report Grbl 1.1 : le champ `A:` contient les accessoires actifs
(`F` = flood, `M` = mist, `S`/`C` = spindle CW/CCW). Ex :
  `<Idle|MPos:0,0,0,0,0|FS:0,0|A:SF>` → spindle ON + flood ON

main_window appelle `set_on_silent()` à chaque status report pour caler
l'UI sur la réalité, ce qui évite tout drift même en cas de M8/M9 venant
du g-code lui-même, d'un soft reset, ou d'une déconnexion.

== Câblage RAMPS 1.4 ==

Brancher le ventilateur 12V sur la sortie D10 du RAMPS (connecteur HE0 /
BED-OUT2 selon les variantes). Le firmware grbl-Mega-5X mappe
`COOLANT_FLOOD_BIT` sur PB4 = MEGA D10 (cf. cpu_map.h:219).

Pour piloter D9 plutôt que D10, remplacer M8/M9 par M7/M9 dans
main_window. (D9 = COOLANT_MIST_BIT = sortie FAN classique du RAMPS.)

== Démarrage automatique ==

Le ventilateur démarre automatiquement à chaque clic sur Run via
`_on_play()` (envoie M8 si l'UI dit OFF). Idempotent, donc ne perturbe
rien si l'utilisateur l'avait déjà allumé.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.i18n import tr
from ui.theme import COLORS, ui_font


class FanPanel(QGroupBox):
    """Carte « Ventilateur RAMPS » avec un gros bouton ON/OFF."""

    fan_on_requested = Signal()
    fan_off_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(tr("Ventilateur RAMPS"), parent)
        self._on = False

        self.lbl_status = QLabel("OFF")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setFont(ui_font(16, bold=True))
        self._refresh_status_style()

        self.btn_toggle = QPushButton(tr("ALLUMER LE VENTILATEUR"))
        self.btn_toggle.setProperty("variant", "primary")
        self.btn_toggle.setMinimumHeight(46)
        self.btn_toggle.setFont(ui_font(11, bold=True))
        self.btn_toggle.setToolTip(
            tr(
                "Active la sortie 12V D10 du RAMPS via M8 (coolant flood). "
                "Branche le ventilateur sur cette sortie."
            )
        )
        self.btn_toggle.clicked.connect(self._on_toggle)

        row = QHBoxLayout()
        row.addWidget(self.lbl_status, 1)
        row.addWidget(self.btn_toggle, 2)

        v = QVBoxLayout(self)
        v.setSpacing(8)
        v.addLayout(row)

    def _refresh_status_style(self) -> None:
        if self._on:
            self.lbl_status.setStyleSheet(f"color: {COLORS['success']};")
        else:
            self.lbl_status.setStyleSheet(f"color: {COLORS['text_subtle']};")

    def _on_toggle(self) -> None:
        if self._on:
            self.fan_off_requested.emit()
        else:
            self.fan_on_requested.emit()

    def set_on(self, on: bool) -> None:
        """Met à jour l'état UI. Appelé après émission d'un signal user
        (clic bouton) ou par main_window après envoi d'une commande."""
        self._on = on
        if on:
            self.btn_toggle.setText(tr("COUPER LE VENTILATEUR"))
            self.btn_toggle.setProperty("variant", "danger")
            self.lbl_status.setText("ON")
        else:
            self.btn_toggle.setText(tr("ALLUMER LE VENTILATEUR"))
            self.btn_toggle.setProperty("variant", "primary")
            self.lbl_status.setText("OFF")
        # Re-style après changement de propriété
        self.btn_toggle.style().unpolish(self.btn_toggle)
        self.btn_toggle.style().polish(self.btn_toggle)
        self._refresh_status_style()

    def set_on_silent(self, on: bool) -> None:
        """Met à jour l'état UI sans rien émettre.

        Appelé par main_window à chaque status report Grbl pour caler l'UI
        sur la réalité matérielle (champ `A:F` = flood actif). C'est cette
        synchro qui garantit qu'on ne se désynchronise jamais des g-codes
        embedded (M8 dans le programme, soft reset, etc.)."""
        if on != self._on:
            self.set_on(on)

    def force_off(self) -> None:
        if self._on:
            self.set_on(False)
            self.fan_off_requested.emit()
