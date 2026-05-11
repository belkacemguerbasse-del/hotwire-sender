"""Thème visuel global de l'application.

Palette claire, plate et accessible. Chaque couleur a un rôle sémantique
défini ici et utilisé dans le QSS et les widgets pour rester cohérents.

Usage :
    from ui.theme import apply_theme, COLORS
    apply_theme(app)
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect, QWidget


COLORS = {
    # Fond / surfaces
    "bg":           "#f3f5f8",   # fond global
    "surface":      "#ffffff",   # cartes, group boxes, tables
    "surface_alt":  "#fafbfc",   # zones secondaires
    "border":       "#d6dde6",   # bordures fines
    "border_strong":"#aab3bf",   # bordures contrastées
    # Texte
    "text":         "#1f2933",
    "text_muted":   "#637381",
    "text_subtle":  "#9aa3ad",
    # Marque / accents
    "primary":      "#1f6feb",   # action principale
    "primary_hi":   "#388bfd",
    "primary_lo":   "#0d52c2",
    "danger":       "#d6363d",   # arrêt d'urgence, erreurs
    "danger_hi":    "#e85460",
    "warning":      "#f59f00",   # hold, override actif
    "success":      "#1f9d55",   # idle / opérationnel
    # États machine (Grbl)
    "state_idle":   "#1f9d55",
    "state_run":    "#1f6feb",
    "state_hold":   "#f59f00",
    "state_alarm":  "#d6363d",
    "state_jog":    "#7950f2",
    "state_door":   "#fab005",
    "state_check":  "#fab005",
    "state_home":   "#7950f2",
    "state_sleep":  "#868e96",
    "state_unknown":"#adb5bd",
}


# Noms de fonte qu'on essaie en cascade. Segoe UI = défaut Windows 11.
PREFERRED_UI_FONT = ("Segoe UI Variable", "Segoe UI", "Inter", "Roboto", "Arial")
PREFERRED_MONO_FONT = ("Cascadia Mono", "Cascadia Code", "Consolas", "Menlo", "Courier New")


def best_font(family_list, point_size: int = 10, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    """Retourne la première fonte du tableau réellement installée."""
    available = set(QFontDatabase.families())
    for name in family_list:
        if name in available:
            f = QFont(name, point_size)
            f.setWeight(weight)
            return f
    f = QFont()
    f.setPointSize(point_size)
    f.setWeight(weight)
    return f


def ui_font(point_size: int = 10, bold: bool = False) -> QFont:
    return best_font(
        PREFERRED_UI_FONT,
        point_size,
        QFont.Weight.DemiBold if bold else QFont.Weight.Normal,
    )


def mono_font(point_size: int = 11, bold: bool = False) -> QFont:
    return best_font(
        PREFERRED_MONO_FONT,
        point_size,
        QFont.Weight.Bold if bold else QFont.Weight.Normal,
    )


def stylesheet() -> str:
    c = COLORS
    return f"""
/* ===== Base ===== */
/* On NE met PAS de background-color sur QWidget : ça polluerait tous les
   sous-widgets (labels, checkboxes…) qui doivent hériter du parent. */
QWidget {{
    color: {c['text']};
    font-family: "Segoe UI Variable", "Segoe UI", "Inter", "Roboto", sans-serif;
    font-size: 10pt;
}}

QMainWindow, QDialog {{
    background-color: {c['bg']};
}}

/* Widgets "passifs" : transparents, héritent du fond du conteneur. */
QLabel, QCheckBox, QRadioButton, QFrame {{
    background: transparent;
}}

QToolTip {{
    background-color: {c['text']};
    color: {c['surface']};
    border: 1px solid {c['border_strong']};
    padding: 4px 8px;
    border-radius: 4px;
}}

/* ===== GroupBox (cartes) =====
   Titre AU-DESSUS de la carte (sans encoche dans le bord), plus moderne. */
QGroupBox {{
    background-color: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    margin-top: 22px;
    padding: 14px 12px 12px 12px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 4px;
    top: 2px;
    padding: 0 4px;
    color: {c['text_muted']};
    background: transparent;
    font-size: 9pt;
    font-weight: 700;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}}

/* ===== Boutons =====
   Effet 3D doux : dégradé top→bottom, hover plus clair, pressed inversé
   pour donner l'impression que le bouton s'enfonce. */
QPushButton {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 #ffffff,
        stop:1 #e9edf2
    );
    border: 1px solid {c['border_strong']};
    border-radius: 6px;
    padding: 6px 14px;
    color: {c['text']};
    min-height: 22px;
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 #ffffff,
        stop:1 #f3f6fa
    );
    border-color: {c['primary']};
}}
QPushButton:pressed {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 #d8dde4,
        stop:1 #e9edf2
    );
    border-color: {c['primary_lo']};
    padding-top: 7px;
    padding-bottom: 5px;
}}
QPushButton:disabled {{
    background-color: {c['surface_alt']};
    color: {c['text_subtle']};
    border-color: {c['border']};
}}
QPushButton:focus {{
    outline: none;
    border: 1px solid {c['primary']};
}}
QPushButton:checked {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 {c['primary_hi']},
        stop:1 {c['primary']}
    );
    color: white;
    border: 1px solid {c['primary_lo']};
    font-weight: 600;
}}
QPushButton:checked:hover {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 #4ea0ff,
        stop:1 {c['primary_hi']}
    );
}}

/* === Disabled : ECRASE les gradients colores pour griser correctement ===
   Sans cette regle, [variant="primary"]:disabled reste bleu car le selecteur
   d'attribut a plus de specificite que :disabled. */
QPushButton[variant="primary"]:disabled,
QPushButton[variant="danger"]:disabled,
QPushButton[variant="success"]:disabled,
QPushButton[variant="warning"]:disabled,
QPushButton:checked:disabled {{
    background-color: {c['surface_alt']};
    color: {c['text_subtle']};
    border: 1px solid {c['border']};
    font-weight: 500;
}}

/* === Action principale (bleu) === */
/* Triple stop pour un highlight glossy en haut. */
QPushButton[variant="primary"] {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 #5fa8ff,
        stop:0.5 {c['primary_hi']},
        stop:1 {c['primary']}
    );
    color: white;
    border: 1px solid {c['primary_lo']};
    font-weight: 600;
}}
QPushButton[variant="primary"]:hover {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 #4ea0ff,
        stop:1 {c['primary_hi']}
    );
}}
QPushButton[variant="primary"]:pressed {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 {c['primary_lo']},
        stop:1 {c['primary']}
    );
    padding-top: 7px;
    padding-bottom: 5px;
}}

/* === Danger (rouge) === */
QPushButton[variant="danger"] {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 #ff7a85,
        stop:0.5 {c['danger_hi']},
        stop:1 {c['danger']}
    );
    color: white;
    border: 1px solid #aa2a30;
    font-weight: 700;
    letter-spacing: 0.5px;
}}
QPushButton[variant="danger"]:hover {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 #f06672,
        stop:1 {c['danger_hi']}
    );
}}
QPushButton[variant="danger"]:pressed {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 #aa2a30,
        stop:1 {c['danger']}
    );
    padding-top: 7px;
    padding-bottom: 5px;
}}

/* === Succès (vert) === */
QPushButton[variant="success"] {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 #2bb868,
        stop:1 {c['success']}
    );
    color: white;
    border: 1px solid #156d3a;
    font-weight: 600;
}}
QPushButton[variant="success"]:hover {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 #3acf76,
        stop:1 #2bb868
    );
}}

/* === Warning (jaune) === */
QPushButton[variant="warning"] {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 #ffb84d,
        stop:1 {c['warning']}
    );
    color: {c['text']};
    border: 1px solid #c87900;
    font-weight: 600;
}}

/* === Variante compacte === */
QPushButton[compact="true"] {{
    padding: 4px 6px;
    min-width: 0;
    min-height: 18px;
}}
QPushButton[compact="true"]:pressed {{
    padding-top: 5px;
    padding-bottom: 3px;
}}

/* === Pavs jog (carrés type "key") === */
QPushButton[pad="true"] {{
    padding: 2px 0;
    min-width: 0;
    font-weight: 700;
    font-size: 11pt;
    color: {c['text']};
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 #ffffff,
        stop:1 #e0e6ee
    );
    border: 1px solid {c['border_strong']};
    border-bottom-width: 2px;
    border-bottom-color: #8e98a7;
}}
QPushButton[pad="true"]:hover {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 #f0f7ff,
        stop:1 #d8e6f8
    );
    border-color: {c['primary']};
    border-bottom-color: {c['primary_lo']};
    color: {c['primary_lo']};
}}
QPushButton[pad="true"]:pressed {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 {c['primary_lo']},
        stop:1 {c['primary']}
    );
    color: white;
    border-color: {c['primary_lo']};
    border-bottom-width: 1px;
    padding-top: 3px;
    padding-bottom: 1px;
}}

/* ===== Champs de saisie ===== */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background-color: {c['surface']};
    border: 1px solid {c['border_strong']};
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: {c['primary']};
    selection-color: white;
}}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{
    border-color: #7a8593;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 2px solid {c['primary']};
    padding: 4px 7px;
    background-color: #fafcff;
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    background-color: {c['surface_alt']};
    color: {c['text_subtle']};
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 5px solid {c['text_muted']};
    width: 0; height: 0;
    margin-right: 6px;
}}

/* ===== Texte multilignes ===== */
QPlainTextEdit, QTextEdit {{
    background-color: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 6px;
    padding: 4px;
    selection-background-color: {c['primary']};
    selection-color: white;
}}

/* ===== Tables ===== */
QTableWidget, QTableView {{
    background-color: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 6px;
    gridline-color: {c['border']};
    selection-background-color: {c['primary']};
    selection-color: white;
    alternate-background-color: {c['surface_alt']};
}}
QHeaderView::section {{
    background-color: {c['surface_alt']};
    border: none;
    border-bottom: 1px solid {c['border_strong']};
    padding: 6px 8px;
    font-weight: 600;
    color: {c['text_muted']};
}}
QHeaderView::section:first {{ border-top-left-radius: 6px; }}
QHeaderView::section:last  {{ border-top-right-radius: 6px; }}

/* ===== Onglets ===== */
QTabWidget::pane {{
    border: none;
    background: transparent;
    padding-top: 6px;
}}
QTabBar {{ qproperty-drawBase: 0; }}
QTabBar::tab {{
    background-color: transparent;
    color: {c['text_muted']};
    padding: 9px 20px;
    margin: 0 2px;
    border: none;
    font-weight: 500;
    border-bottom: 3px solid transparent;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}}
QTabBar::tab:hover {{
    color: {c['text']};
    background-color: rgba(31, 111, 235, 0.06);
}}
QTabBar::tab:selected {{
    color: {c['primary']};
    border-bottom: 3px solid {c['primary']};
    background-color: rgba(31, 111, 235, 0.08);
    font-weight: 700;
}}

/* ===== Cases à cocher / boutons radio ===== */
QCheckBox, QRadioButton {{
    spacing: 8px;
    color: {c['text']};
}}

/* --- Checkbox --- */
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1.5px solid {c['border_strong']};
    border-radius: 4px;
    background-color: {c['surface']};
}}
QCheckBox::indicator:hover {{
    border-color: {c['primary']};
    background-color: #f0f6ff;
}}
QCheckBox::indicator:checked {{
    /* Croix dessinée via un dégradé radial : un point bleu foncé sur fond bleu */
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 {c['primary_hi']},
        stop:1 {c['primary_lo']}
    );
    border: 1.5px solid {c['primary_lo']};
    image: none;
}}
QCheckBox::indicator:checked:hover {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 #4ea0ff,
        stop:1 {c['primary']}
    );
}}
QCheckBox::indicator:disabled {{
    background-color: {c['surface_alt']};
    border-color: {c['border']};
}}

/* --- Radio button --- */
QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 1.5px solid {c['border_strong']};
    border-radius: 9px;
    background-color: {c['surface']};
}}
QRadioButton::indicator:hover {{
    border-color: {c['primary']};
    background-color: #f0f6ff;
}}
QRadioButton::indicator:checked {{
    /* Cercle plein bleu dégradé, avec un anneau blanc au milieu pour
       l'effet radio classique. Le radial gradient donne ce résultat. */
    background-color: qradialgradient(
        cx:0.5, cy:0.5, radius:0.5,
        fx:0.5, fy:0.5,
        stop:0 {c['primary']},
        stop:0.45 {c['primary']},
        stop:0.5 {c['surface']},
        stop:0.85 {c['surface']},
        stop:1 {c['primary_lo']}
    );
    border: 1.5px solid {c['primary_lo']};
}}
QRadioButton::indicator:checked:hover {{
    background-color: qradialgradient(
        cx:0.5, cy:0.5, radius:0.5,
        fx:0.5, fy:0.5,
        stop:0 {c['primary_hi']},
        stop:0.45 {c['primary_hi']},
        stop:0.5 {c['surface']},
        stop:0.85 {c['surface']},
        stop:1 {c['primary']}
    );
}}
QRadioButton::indicator:disabled {{
    background-color: {c['surface_alt']};
    border-color: {c['border']};
}}

/* ===== Slider ===== */
QSlider::groove:horizontal {{
    border: 1px solid #c0c7d2;
    height: 6px;
    background: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 #d4dae2,
        stop:1 #e9eef4
    );
    border-radius: 4px;
}}
QSlider::sub-page:horizontal {{
    background: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 {c['primary_hi']},
        stop:1 {c['primary_lo']}
    );
    border: 1px solid {c['primary_lo']};
    border-radius: 4px;
}}
QSlider::handle:horizontal {{
    background: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 #ffffff,
        stop:1 #d8dde4
    );
    border: 1px solid {c['border_strong']};
    width: 16px; height: 16px;
    margin: -7px 0;
    border-radius: 9px;
}}
QSlider::handle:horizontal:hover {{
    background: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 #ffffff,
        stop:1 #cfe1ff
    );
    border: 2px solid {c['primary']};
    width: 18px; height: 18px;
    margin: -8px 0;
    border-radius: 10px;
}}
QSlider::handle:horizontal:pressed {{
    background: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 {c['primary_hi']},
        stop:1 {c['primary_lo']}
    );
    border-color: {c['primary_lo']};
}}

/* ===== Statusbar ===== */
QStatusBar {{
    background-color: {c['surface']};
    border-top: 1px solid {c['border']};
    color: {c['text_muted']};
}}
QStatusBar::item {{ border: none; }}

/* ===== Scrollbars ===== */
QScrollBar:vertical {{
    background: transparent;
    width: 12px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {c['border_strong']};
    border-radius: 6px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {c['text_subtle']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; background: none; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
QScrollBar:horizontal {{
    background: transparent;
    height: 12px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {c['border_strong']};
    border-radius: 6px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{ background: {c['text_subtle']}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; background: none; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}

/* ===== Splitter ===== */
QSplitter::handle {{ background: {c['border']}; }}
QSplitter::handle:horizontal {{ width: 2px; }}
QSplitter::handle:vertical   {{ height: 2px; }}

/* ===== Header bar ===== */
QFrame#headerBar {{
    background-color: {c['surface']};
    border-bottom: 1px solid {c['border']};
    border-radius: 0;
}}

/* ===== State pill ===== */
QLabel#statePill {{
    border-radius: 12px;
    padding: 4px 16px;
    color: white;
    font-weight: 700;
    letter-spacing: 1px;
    font-size: 11pt;
}}

/* ===== Connection dot ===== */
QLabel#connectionDot {{
    font-size: 12pt;
}}

/* ===== DRO ===== */
QFrame#droCell {{
    background-color: {c['surface_alt']};
    border: none;
    border-left: 3px solid transparent;
    border-radius: 8px;
}}
QFrame#droCell[active="true"] {{
    background-color: #eef4ff;
    border-left: 3px solid {c['primary']};
}}

QLabel#droValue {{
    color: {c['text']};
}}
QLabel#droAxis {{
    color: {c['primary']};
}}
QLabel#droSub {{
    color: {c['text_muted']};
}}

QProgressBar {{
    background-color: {c['border']};
    border: none;
    border-radius: 6px;
    text-align: center;
    color: white;
    font-weight: 600;
    height: 14px;
}}
QProgressBar::chunk {{
    background-color: {c['primary']};
    border-radius: 6px;
}}
"""


def apply_theme(app: QApplication) -> None:
    app.setFont(ui_font(10))
    app.setStyleSheet(stylesheet())


def card_shadow(
    widget: QWidget,
    blur: int = 14,
    offset_y: int = 2,
    alpha: int = 28,
    color: str | QColor | None = None,
) -> QGraphicsDropShadowEffect:
    """Attache une ombre portée douce au widget et la retourne.

    Le widget devient propriétaire de l'effet (pas besoin de garder la
    référence). Si `color` est fourni, l'ombre prend cette teinte (utile
    pour les pastilles d'état colorées). Sinon noir transparent.
    """
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(blur)
    eff.setOffset(0, offset_y)
    if color is None:
        eff.setColor(QColor(0, 0, 0, alpha))
    else:
        c = QColor(color) if isinstance(color, str) else QColor(color)
        c.setAlpha(alpha)
        eff.setColor(c)
    widget.setGraphicsEffect(eff)
    return eff


def update_shadow_color(eff: QGraphicsDropShadowEffect, color: str, alpha: int = 120) -> None:
    """Change la couleur (et alpha) d'une ombre déjà attachée à un widget.

    Utilisé pour la pastille d'état du header qui change de teinte selon
    l'état machine (vert quand Idle, rouge quand Alarm, …).
    """
    c = QColor(color)
    c.setAlpha(alpha)
    eff.setColor(c)
