"""GUI entry point."""

import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import QApplication

from .main_window import MainWindow


def launch(db_path: Path, config_path: Optional[Path] = None):
    app = QApplication(sys.argv)
    app.setApplicationName("Abhay Leads")
    window = MainWindow(db_path, config_path)
    window.show()
    sys.exit(app.exec())
