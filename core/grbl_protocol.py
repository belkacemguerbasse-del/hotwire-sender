"""Grbl 1.1 + Mega-5X protocol constants and lookup tables."""

# Taille standard du buffer RX Grbl. Sur grbl-Mega-5X la valeur réelle est plus
# grande (255 octets observés via la chaîne d'options "VNMGZHL,35,255,64") car
# le Mega a beaucoup plus de SRAM. La valeur effective est mise à jour à la
# volée dès qu'on détecte la ligne `[OPT:...,N,M]` au boot.
GRBL_RX_BUFFER_SIZE = 128

CMD_RESET = b"\x18"
CMD_STATUS_REPORT = b"?"
CMD_CYCLE_START = b"~"
CMD_FEED_HOLD = b"!"
CMD_SAFETY_DOOR = b"\x84"
CMD_JOG_CANCEL = b"\x85"

CMD_FEED_OVR_RESET = b"\x90"
CMD_FEED_OVR_COARSE_PLUS = b"\x91"
CMD_FEED_OVR_COARSE_MINUS = b"\x92"
CMD_FEED_OVR_FINE_PLUS = b"\x93"
CMD_FEED_OVR_FINE_MINUS = b"\x94"

CMD_RAPID_OVR_RESET = b"\x95"
CMD_RAPID_OVR_MEDIUM = b"\x96"
CMD_RAPID_OVR_LOW = b"\x97"

CMD_SPINDLE_OVR_RESET = b"\x99"
CMD_SPINDLE_OVR_COARSE_PLUS = b"\x9A"
CMD_SPINDLE_OVR_COARSE_MINUS = b"\x9B"
CMD_SPINDLE_OVR_FINE_PLUS = b"\x9C"
CMD_SPINDLE_OVR_FINE_MINUS = b"\x9D"
CMD_SPINDLE_STOP = b"\x9E"

CMD_COOLANT_FLOOD_TOGGLE = b"\xA0"
CMD_COOLANT_MIST_TOGGLE = b"\xA1"

ALARM_CODES = {
    1: "Hard limit déclenché. Position machine probablement perdue.",
    2: "G-code: déplacement hors enveloppe (soft limit).",
    3: "Reset pendant un cycle. Position perdue, refaire homing.",
    4: "Probe fail: probe pas dans l'état attendu.",
    5: "Probe fail: probe n'a pas touché.",
    6: "Reset pendant un cycle de homing.",
    7: "Safety door ouverte pendant un cycle.",
    8: "Échec homing: cycle non lancé.",
    9: "Échec homing: pas de contact dans la course.",
    10: "Échec homing: dual-motor non aligné.",
    11: "Buffer série RX overflow.",
}

ERROR_CODES = {
    1: "Lettre G-code attendue.",
    2: "Mauvaise valeur numérique.",
    3: "Commande $ non reconnue.",
    4: "Valeur négative interdite.",
    5: "Homing désactivé.",
    6: "Step pulse trop court.",
    7: "EEPROM read failed.",
    8: "Settings: Grbl pas en idle.",
    9: "Verrouillage: settings interdits pendant cycle.",
    10: "Soft limit nécessite homing activé.",
    11: "Ligne trop longue.",
    12: "Step rate trop élevé.",
    13: "Vérification mode actif.",
    14: "Build info ou startup line trop long.",
    15: "Jog: dépassement course.",
    16: "Jog: commande mal formée.",
    17: "Laser mode: PWM nécessaire.",
    20: "Commande G-code non supportée.",
    21: "Mots G-code modaux en conflit.",
    22: "Feed rate manquant.",
    23: "Valeur entière requise.",
    24: "Deux commandes G-code requièrent un mot d'axe.",
    25: "Mot G-code répété.",
    26: "Mot d'axe manquant.",
    27: "Numéro de ligne hors plage 1-9999999.",
    28: "Valeur P ou L requise manquante.",
    29: "G59.x non supporté.",
    30: "G53 nécessite G0 ou G1.",
    31: "Mots d'axes inutilisés.",
    32: "G2/G3 nécessite mot d'axe dans le plan.",
    33: "Cible motion invalide.",
    34: "Géométrie d'arc invalide.",
    35: "Arc en mode offset: I/J/K manquants.",
    36: "Mots non utilisés.",
    37: "G43.1 dynamic offset: mot d'axe Z manquant.",
    38: "Tool number invalide.",
}

# Spindle PWM range observed on grbl-Mega-5X (16-bit on D8, 8-bit on D9 selon config).
DEFAULT_SPINDLE_MIN_RPM = 0
DEFAULT_SPINDLE_MAX_RPM = 1000
