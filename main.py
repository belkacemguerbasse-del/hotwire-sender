"""Point d'entrée HotWire Sender."""

from __future__ import annotations

import sys
from pathlib import Path

# Permet d'exécuter `python main.py` depuis le dossier racine.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow
from ui.theme import apply_theme


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("HotWire Sender")
    app.setOrganizationName("HotWire")
    app.setStyle("Fusion")           # base neutre + cohérente avec QSS

    # Charge la pref de thème AVANT d'appliquer (sinon flash visuel)
    from core import persistence
    from ui.i18n import set_language
    theme_mode = persistence.get_str("prefs/theme", "light")
    lang = persistence.get_str("prefs/language", "fr")
    set_language(lang)
    apply_theme(app, mode=theme_mode)

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
