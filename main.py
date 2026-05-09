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
    apply_theme(app)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
