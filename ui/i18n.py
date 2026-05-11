"""Internationalisation légère (Python dict).

Approche pragmatique : on évite la lourdeur Qt Linguist (.ts/.qm/lrelease)
et on utilise un dict Python `TRANSLATIONS` indexé par langue. Les widgets
appellent `tr("texte original français")` qui retourne la version traduite.

Limitation : nécessite un redémarrage pour changer de langue (les strings
sont copiées dans les widgets à la construction). Acceptable pour un app
desktop qui ne change pas de langue à chaud.

Si plus tard on veut une traduction live, on basculera sur Qt Linguist.
"""

from __future__ import annotations


# Langue active (modifiée par set_language au démarrage)
_LANG = "fr"


# Dictionnaire des traductions. Clé = texte original français, valeur = dict
# par code de langue. Si une langue manque pour une clé, on retombe sur le FR.
TRANSLATIONS: dict[str, dict[str, str]] = {
    # === Boutons & actions principaux ===
    "Ouvrir…": {"en": "Open…"},
    "🎬  Simuler": {"en": "🎬  Simulate"},
    "▶  Lancer": {"en": "▶  Run"},
    "⏸  Pause": {"en": "⏸  Pause"},
    "⏹  Stop": {"en": "⏹  Stop"},
    "↻  Recharger": {"en": "↻  Reload"},
    "📋  Historique": {"en": "📋  History"},
    "📂  Ouvrir projet…": {"en": "📂  Open project…"},
    "💾  Sauver projet…": {"en": "💾  Save project…"},
    "Rafraîchir l'aperçu": {"en": "Refresh preview"},
    "Générer & sauver…": {"en": "Generate & save…"},
    "Générer & charger dans l'app": {"en": "Generate & load in app"},
    "Fermer": {"en": "Close"},
    "Annuler": {"en": "Cancel"},
    "Continuer": {"en": "Continue"},
    "Appliquer": {"en": "Apply"},
    "Effacer": {"en": "Clear"},
    "Recharger": {"en": "Reload"},
    "📂 Recharger": {"en": "📂 Reload"},
    "🗑  Tout effacer": {"en": "🗑  Clear all"},
    "Connecter": {"en": "Connect"},
    "Déconnecter": {"en": "Disconnect"},
    "Re-Scan": {"en": "Re-scan"},
    "+ Ajouter une section": {"en": "+ Add a section"},
    "🆕  Nouveau": {"en": "🆕  New"},
    "ALLUMER LE FIL": {"en": "TURN WIRE ON"},
    "COUPER LE FIL": {"en": "TURN WIRE OFF"},
    "ARRÊT D'URGENCE": {"en": "EMERGENCY STOP"},
    "Caméra": {"en": "Camera"},
    "Démarrer": {"en": "Start"},
    "Arrêter": {"en": "Stop"},
    "Capturer": {"en": "Capture"},
    "▶  Exécuter cette macro": {"en": "▶  Run this macro"},
    "➕  Ajouter": {"en": "➕  Add"},
    "🗑  Supprimer": {"en": "🗑  Delete"},

    # === Onglets ===
    "Pilotage": {"en": "Control"},
    "Vue 3D": {"en": "3D View"},
    "Réglages": {"en": "Settings"},
    "Macros": {"en": "Macros"},

    # === Titres de cartes ===
    "Grbl": {"en": "Grbl"},
    "Référencement": {"en": "Homing"},
    "Contrôle": {"en": "Control"},
    "Journal Grbl": {"en": "Grbl Log"},
    "GCode": {"en": "GCode"},
    "Position": {"en": "Position"},
    "Jogging": {"en": "Jogging"},
    "Fil chaud": {"en": "Hot wire"},
    "MDI": {"en": "MDI"},
    "Préférences": {"en": "Preferences"},
    "Source": {"en": "Source"},

    # === Header bar ===
    "HotWire Sender": {"en": "HotWire Sender"},
    "CNC fil chaud · 4 axes XYZA": {"en": "Hot-wire CNC · 4 axes XYZA"},
    "Non connecté": {"en": "Not connected"},

    # === États machine (compatible avec STATE_LABELS) ===
    "PRÊT": {"en": "READY"},
    "EN COURS": {"en": "RUNNING"},
    "PAUSE": {"en": "PAUSED"},
    "JOG": {"en": "JOG"},
    "ALARME": {"en": "ALARM"},
    "PORTE": {"en": "DOOR"},
    "VÉRIF": {"en": "CHECK"},
    "HOMING": {"en": "HOMING"},
    "VEILLE": {"en": "SLEEP"},
    "INCONNU": {"en": "UNKNOWN"},
}


def set_language(lang: str) -> None:
    """Change la langue active. Doit être appelé AVANT de créer les widgets."""
    global _LANG
    _LANG = lang if lang in ("fr", "en") else "fr"


def current_language() -> str:
    return _LANG


def tr(text: str) -> str:
    """Retourne la traduction du texte original français dans la langue
    active. Si la traduction n'existe pas, retourne le texte original."""
    if _LANG == "fr":
        return text
    entry = TRANSLATIONS.get(text)
    if entry is None:
        return text
    return entry.get(_LANG, text)
