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
    "ALLUMER LE VENTILATEUR": {"en": "TURN FAN ON"},
    "COUPER LE VENTILATEUR": {"en": "TURN FAN OFF"},
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
    "Ventilateur RAMPS": {"en": "RAMPS fan"},
    "Active la sortie 12V D10 du RAMPS via M8 (coolant flood). Branche le ventilateur sur cette sortie.":
        {"en": "Turns on RAMPS 12V D10 output via M8 (coolant flood). Wire the fan to that output."},
    "MDI": {"en": "MDI"},
    "Préférences": {"en": "Preferences"},
    "Source": {"en": "Source"},

    # === Header bar ===
    "HotWire Sender": {"en": "HotWire Sender"},
    "CNC fil chaud · 4 axes XYZA": {"en": "Hot-wire CNC · 4 axes XYZA"},
    "Non connecté": {"en": "Not connected"},
    "Connecté": {"en": "Connected"},

    # === HotWire panel ===
    "Puissance": {"en": "Power"},

    # === Control panel ===
    "Cycle référencement": {"en": "Homing cycle"},
    "Débloq.": {"en": "Unlock"},
    "Réinit.": {"en": "Reset"},
    "Retiens": {"en": "Hold"},
    "Départ": {"en": "Resume"},
    "Vérifie": {"en": "Check"},

    # === Position panel ===
    "Position (G28 / G30)": {"en": "Position (G28 / G30)"},
    "Mémoriser ici → G28": {"en": "Memorize here → G28"},
    "Aller à G28": {"en": "Go to G28"},
    "Mémoriser ici → G30": {"en": "Memorize here → G30"},
    "Aller à G30": {"en": "Go to G30"},
    "Mémoires": {"en": "Memories"},
    "Zéro tout (XYZA)": {"en": "Zero all (XYZA)"},
    "Zéro X": {"en": "Zero X"},
    "Zéro Y": {"en": "Zero Y"},
    "Zéro Z": {"en": "Zero Z"},
    "Zéro A": {"en": "Zero A"},
    "Zéros (WCO)": {"en": "Zeros (WCO)"},

    # === Jog pad ===
    "Distance": {"en": "Distance"},
    "Vit. Avance": {"en": "Feed rate"},
    "Métrique": {"en": "Metric"},
    "Activer le clavier": {"en": "Enable keyboard"},
    "Aller à 0": {"en": "Go to 0"},
    "Aller à 0 (tout)": {"en": "Go to 0 (all)"},
    "Déplace les 4 axes au zéro WCO actuel": {"en": "Moves all 4 axes to current WCO zero"},
    "Reset affichage": {"en": "Reset display"},
    "Remet la position à zéro côté affichage uniquement": {"en": "Resets position to zero on display only"},
    "jogger les deux chariots": {"en": "jog both towers"},
    "Chariot gauche": {"en": "Left tower"},
    "Chariot droit": {"en": "Right tower"},
    "Aller à\n0 XY": {"en": "Go to\n0 XY"},
    "Aller à\n0 ZA": {"en": "Go to\n0 ZA"},

    # === Preferences panel ===
    "Connecter automatiquement à l'ouverture": {"en": "Auto-connect on startup"},
    "Pause automatique sur erreur Grbl": {"en": "Auto-pause on Grbl error"},
    "Watchdog de sécurité": {"en": "Safety watchdog"},
    "Clair": {"en": "Light"},
    "Sombre": {"en": "Dark"},
    "Délai watchdog :": {"en": "Watchdog delay:"},
    "Intervalle status :": {"en": "Status interval:"},
    "Silence bootloader :": {"en": "Bootloader silence:"},
    "Thème :": {"en": "Theme:"},
    "Langue :": {"en": "Language:"},

    # === MDI panel ===
    "Commande manuelle…": {"en": "Manual command…"},
    "Envoyer": {"en": "Send"},
    "Slice": {"en": "Slice"},

    # === Status / log panel ===
    "Verbeux": {"en": "Verbose"},
    "Afficher également les rapports d'état périodiques et les ack 'ok'.":
        {"en": "Also show periodic status reports and 'ok' acks."},

    # === Overrides panel ===
    "Remplacer le taux d'avance": {"en": "Override feed rate"},
    "Remplacer le paramètre actuel": {"en": "Override current setting"},
    "Réinit": {"en": "Reset"},

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
