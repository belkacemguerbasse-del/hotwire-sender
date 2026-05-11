"""Préférences générales de l'app, persistées dans QSettings.

Couvre les comportements utilisateur courants :
- auto-connexion à l'ouverture
- pause automatique sur erreur Grbl
- intervalle d'interrogation du statut (ms)
- délai de silence bootloader Mega à l'ouverture du port (s)
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QVBoxLayout,
    QWidget,
)

from core import persistence
from ui.i18n import tr


class PreferencesPanel(QGroupBox):
    """Émis quand l'utilisateur clique « Appliquer ». Le main_window se charge
    de propager les valeurs aux composants concernés (GrblLink, JobRunner…)."""

    settings_applied = Signal(dict)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(tr("Préférences"), parent)

        self.cb_autoconnect = QCheckBox(tr("Connecter automatiquement à l'ouverture"))
        self.cb_autoconnect.setToolTip(
            "À chaque démarrage, ouvre le dernier port utilisé sans intervention."
        )

        self.cb_pause_on_error = QCheckBox(tr("Pause automatique sur erreur Grbl"))
        self.cb_pause_on_error.setToolTip(
            "En cas de réponse `error:` pendant un programme, met en pause "
            "le job pour que tu puisses inspecter avant de continuer."
        )

        self.sb_poll_ms = QSpinBox()
        self.sb_poll_ms.setRange(50, 2000)
        self.sb_poll_ms.setSingleStep(50)
        self.sb_poll_ms.setSuffix(" ms")
        self.sb_poll_ms.setToolTip(
            "Fréquence des requêtes `?` envoyées au firmware. "
            "200 ms = 5 Hz, valeur recommandée pour Grbl 1.1."
        )

        self.sb_boot_delay = QDoubleSpinBox()
        self.sb_boot_delay.setRange(0.5, 10.0)
        self.sb_boot_delay.setSingleStep(0.5)
        self.sb_boot_delay.setSuffix(" s")
        self.sb_boot_delay.setDecimals(1)
        self.sb_boot_delay.setToolTip(
            "Silence après ouverture du port pour laisser le bootloader Arduino "
            "Mega céder la main à Grbl. 3 s = recommandé pour stk500v2."
        )

        # --- Apparence ---
        self.cb_theme = QComboBox()
        self.cb_theme.addItem(tr("Clair"), "light")
        self.cb_theme.addItem(tr("Sombre"), "dark")
        self.cb_theme.setToolTip(
            "Bascule l'apparence générale de l'application.\n"
            "Le changement est appliqué immédiatement."
        )

        self.cb_lang = QComboBox()
        self.cb_lang.addItem("Français", "fr")
        self.cb_lang.addItem("English", "en")
        self.cb_lang.setToolTip(
            "Langue de l'interface. Le changement prend effet "
            "au prochain redémarrage de l'application."
        )

        self.cb_watchdog = QCheckBox(tr("Watchdog de sécurité"))
        self.cb_watchdog.setToolTip(
            "Si aucun status report n'arrive pendant le délai ci-dessous "
            "alors qu'un job est en cours, coupe le fil chaud + met en pause "
            "et alerte. Protection contre câble débranché ou freeze firmware."
        )
        self.sb_watchdog_s = QDoubleSpinBox()
        self.sb_watchdog_s.setRange(1.0, 30.0)
        self.sb_watchdog_s.setSingleStep(0.5)
        self.sb_watchdog_s.setDecimals(1)
        self.sb_watchdog_s.setSuffix(" s")
        self.sb_watchdog_s.setToolTip(
            "Délai sans status report avant déclenchement. "
            "3 s = recommandé (status normal toutes les 200 ms)."
        )

        form = QFormLayout()
        form.addRow(self.cb_autoconnect)
        form.addRow(self.cb_pause_on_error)
        form.addRow(self.cb_watchdog)
        form.addRow(tr("Délai watchdog :"), self.sb_watchdog_s)
        form.addRow(tr("Intervalle status :"), self.sb_poll_ms)
        form.addRow(tr("Silence bootloader :"), self.sb_boot_delay)
        form.addRow(tr("Thème :"), self.cb_theme)
        form.addRow(tr("Langue :"), self.cb_lang)

        self.btn_apply = QPushButton(tr("Appliquer"))
        self.btn_apply.setProperty("variant", "primary")
        self.btn_apply.setMinimumHeight(30)
        self.btn_apply.clicked.connect(self._apply)

        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(self.btn_apply)

        v = QVBoxLayout(self)
        v.addLayout(form)
        v.addLayout(actions)

        self._load()

    def _load(self) -> None:
        self.cb_autoconnect.setChecked(persistence.get_bool("prefs/autoconnect", False))
        self.cb_pause_on_error.setChecked(persistence.get_bool("prefs/pause_on_error", True))
        self.cb_watchdog.setChecked(persistence.get_bool("prefs/watchdog", True))
        self.sb_watchdog_s.setValue(persistence.get_float("prefs/watchdog_s", 3.0))
        self.sb_poll_ms.setValue(persistence.get_int("prefs/poll_ms", 200))
        self.sb_boot_delay.setValue(persistence.get_float("prefs/boot_delay_s", 3.0))
        theme = persistence.get_str("prefs/theme", "light")
        idx = self.cb_theme.findData(theme)
        if idx >= 0:
            self.cb_theme.setCurrentIndex(idx)
        lang = persistence.get_str("prefs/language", "fr")
        idx = self.cb_lang.findData(lang)
        if idx >= 0:
            self.cb_lang.setCurrentIndex(idx)

    def _apply(self) -> None:
        prefs = self.get_prefs()
        persistence.set_("prefs/autoconnect", prefs["autoconnect"])
        persistence.set_("prefs/pause_on_error", prefs["pause_on_error"])
        persistence.set_("prefs/watchdog", prefs["watchdog"])
        persistence.set_("prefs/watchdog_s", prefs["watchdog_s"])
        persistence.set_("prefs/poll_ms", prefs["poll_ms"])
        persistence.set_("prefs/boot_delay_s", prefs["boot_delay_s"])
        persistence.set_("prefs/theme", prefs["theme"])
        persistence.set_("prefs/language", prefs["language"])
        self.settings_applied.emit(prefs)

    def get_prefs(self) -> dict:
        return {
            "autoconnect": self.cb_autoconnect.isChecked(),
            "pause_on_error": self.cb_pause_on_error.isChecked(),
            "watchdog": self.cb_watchdog.isChecked(),
            "watchdog_s": self.sb_watchdog_s.value(),
            "poll_ms": self.sb_poll_ms.value(),
            "boot_delay_s": self.sb_boot_delay.value(),
            "theme": self.cb_theme.currentData() or "light",
            "language": self.cb_lang.currentData() or "fr",
        }


def load_prefs() -> dict:
    """Helper pour lire les préférences au démarrage de l'app."""
    return {
        "autoconnect": persistence.get_bool("prefs/autoconnect", False),
        "pause_on_error": persistence.get_bool("prefs/pause_on_error", True),
        "watchdog": persistence.get_bool("prefs/watchdog", True),
        "watchdog_s": persistence.get_float("prefs/watchdog_s", 3.0),
        "poll_ms": persistence.get_int("prefs/poll_ms", 200),
        "boot_delay_s": persistence.get_float("prefs/boot_delay_s", 3.0),
        "theme": persistence.get_str("prefs/theme", "light"),
        "language": persistence.get_str("prefs/language", "fr"),
    }
