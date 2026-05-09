"""Descriptions FR des réglages `$N` de Grbl 1.1 + extensions Mega-5X.

Couvre les 6 axes possibles (X Y Z A B C) pour les indices $100..$135.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SettingInfo:
    id: int
    label: str          # nom court FR
    unit: str = ""
    description: str = ""  # description longue


def _axis_letter(idx: int) -> str:
    return ("X", "Y", "Z", "A", "B", "C")[idx]


_BASE: dict[int, SettingInfo] = {
    0: SettingInfo(0, "Largeur impulsion pas", "µs",
                   "Durée d'une impulsion STEP. 10 µs convient pour la plupart des drivers."),
    1: SettingInfo(1, "Délai inactivité pas", "ms",
                   "Délai avant désactivation des moteurs après dernier mouvement. 255 = jamais."),
    2: SettingInfo(2, "Inversion masque impulsion", "bool",
                   "Inverse le signal STEP par axe (bit 0=X, 1=Y, …)."),
    3: SettingInfo(3, "Inversion masque direction", "bool",
                   "Inverse le signal DIR par axe (bit 0=X, 1=Y, …)."),
    4: SettingInfo(4, "Inversion enable pas", "bool",
                   "Inverse la sortie ENABLE des drivers."),
    5: SettingInfo(5, "Inversion fins de course", "bool",
                   "Inverse la lecture des fdc (1 = NC, 0 = NO avec pull-up)."),
    6: SettingInfo(6, "Inversion sonde", "bool",
                   "Inverse la lecture de la sonde palpeur."),
    10: SettingInfo(10, "Masque rapport statut", "bitmask",
                    "Bit 0 = MPos, bit 1 = WPos, bit 2 = WCO, bit 3 = info plan."),
    11: SettingInfo(11, "Tolérance virage", "mm",
                    "Junction deviation : plus petit = virages plus lents."),
    12: SettingInfo(12, "Tolérance arc", "mm",
                    "Précision de segmentation des arcs G2/G3."),
    13: SettingInfo(13, "Rapport en pouces", "bool",
                    "1 = rapports en pouces, 0 = en mm."),
    20: SettingInfo(20, "Limites logicielles", "bool",
                    "Active la vérification des $130..$135 (nécessite homing)."),
    21: SettingInfo(21, "Limites physiques", "bool",
                    "Active l'arrêt d'urgence sur déclenchement fdc."),
    22: SettingInfo(22, "Cycle de référencement", "bool",
                    "Active la commande $H. Nécessite des fdc câblés."),
    23: SettingInfo(23, "Inversion dir. référencement", "bitmask",
                    "Inverse le sens de homing par axe (bit 0=X, 1=Y, …)."),
    24: SettingInfo(24, "Avance référencement", "mm/min",
                    "Vitesse lente d'approche en homing."),
    25: SettingInfo(25, "Recherche référencement", "mm/min",
                    "Vitesse rapide d'approche en homing."),
    26: SettingInfo(26, "Anti-rebond fdc", "ms",
                    "Délai d'anti-rebond électrique des fdc."),
    27: SettingInfo(27, "Retrait référencement", "mm",
                    "Distance de retrait après contact fdc."),
    30: SettingInfo(30, "Vitesse broche max", "RPM",
                    "Pour fil chaud : valeur S maximale du PWM."),
    31: SettingInfo(31, "Vitesse broche min", "RPM",
                    "Pour fil chaud : valeur S minimale du PWM."),
    32: SettingInfo(32, "Mode laser", "bool",
                    "Active le mode laser/fil chaud (M3/M4 sans pause sur changement S)."),
}


def settings_info(setting_id: int) -> SettingInfo:
    """Retourne les infos pour un $N donné. Calcule à la volée pour les axes."""
    if setting_id in _BASE:
        return _BASE[setting_id]
    if 100 <= setting_id <= 105:
        idx = setting_id - 100
        return SettingInfo(setting_id, f"Pas/mm {_axis_letter(idx)}", "pas/mm",
                           f"Nombre de pas moteur par mm sur l'axe {_axis_letter(idx)}.")
    if 110 <= setting_id <= 115:
        idx = setting_id - 110
        return SettingInfo(setting_id, f"Vitesse max {_axis_letter(idx)}", "mm/min",
                           f"Vitesse de déplacement maximale sur l'axe {_axis_letter(idx)}.")
    if 120 <= setting_id <= 125:
        idx = setting_id - 120
        return SettingInfo(setting_id, f"Accélération {_axis_letter(idx)}", "mm/s²",
                           f"Accélération maximale sur l'axe {_axis_letter(idx)}.")
    if 130 <= setting_id <= 135:
        idx = setting_id - 130
        return SettingInfo(setting_id, f"Course max {_axis_letter(idx)}", "mm",
                           f"Distance de course physique de l'axe {_axis_letter(idx)} (pour soft-limits).")
    return SettingInfo(setting_id, f"$ {setting_id}", "", "Réglage non documenté.")
