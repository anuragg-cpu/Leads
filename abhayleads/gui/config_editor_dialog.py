"""In-app editor for a profile's config.yaml - so adding keywords, turning
sources on/off, or tuning scoring doesn't require leaving the app or
knowing where the file lives on disk.
"""

from pathlib import Path

import yaml
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
)


class ConfigEditorDialog(QDialog):
    def __init__(self, config_path: Path, parent=None):
        super().__init__(parent)
        self.config_path = config_path

        self.setWindowTitle(f"Edit config - {config_path}")
        self.resize(760, 640)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Raw config.yaml for this profile. Saving re-parses it as YAML first - "
                "if there's a syntax error, nothing is written and you'll see what's wrong."
            )
        )

        self.editor = QPlainTextEdit()
        self.editor.setFont(QFont("Consolas", 10) if _font_available("Consolas") else QFont("Courier New", 10))
        if config_path.exists():
            self.editor.setPlainText(config_path.read_text(encoding="utf-8"))
        else:
            self.editor.setPlainText("product:\n  name: \"\"\n  keywords: []\n  exclude_keywords: []\n")
        layout.addWidget(self.editor)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self):
        text = self.editor.toPlainText()
        try:
            yaml.safe_load(text)
        except yaml.YAMLError as exc:
            QMessageBox.critical(self, "Invalid YAML", f"Couldn't parse this as YAML, nothing was saved:\n\n{exc}")
            return

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(text, encoding="utf-8")
        self.accept()


def _font_available(family: str) -> bool:
    from PyQt6.QtGui import QFontDatabase

    return family in QFontDatabase.families()
