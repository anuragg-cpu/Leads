"""Detail/edit dialog for a single lead."""

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
)

from ..db import Database
from ..models import STAGES


class LeadDetailDialog(QDialog):
    def __init__(self, db: Database, lead_id: int, parent=None):
        super().__init__(parent)
        self.db = db
        self.lead_id = lead_id
        lead = db.get_lead(lead_id)

        self.setWindowTitle(f"Lead #{lead_id} - {lead['company'] or lead['contact_name'] or lead['source']}")
        self.resize(520, 520)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        form.addRow("Company:", QLabel(lead["company"] or "-"))
        form.addRow("Contact:", QLabel(lead["contact_name"] or "-"))
        form.addRow("Title:", QLabel(lead["title"] or "-"))
        form.addRow("Email:", QLabel(lead["email"] or "-"))
        form.addRow("Phone:", QLabel(lead["phone"] or "-"))
        url_label = QLabel(f'<a href="{lead["url"]}">{lead["url"]}</a>' if lead["url"] else "-")
        url_label.setOpenExternalLinks(True)
        form.addRow("URL:", url_label)
        form.addRow("Source:", QLabel(f"{lead['source']} ({lead['source_detail']})"))
        form.addRow("Keywords matched:", QLabel(lead["keyword_matched"] or "-"))
        form.addRow("Score:", QLabel(str(lead["score"])))
        form.addRow("First seen:", QLabel(lead["created_at"]))
        form.addRow("Last seen:", QLabel(lead["last_seen_at"]))

        self.stage_combo = QComboBox()
        self.stage_combo.addItems(STAGES)
        self.stage_combo.setCurrentText(lead["stage"])
        form.addRow("Stage:", self.stage_combo)

        self.follow_up_check = QCheckBox("Set follow-up date")
        self.follow_up_edit = QDateEdit()
        self.follow_up_edit.setCalendarPopup(True)
        self.follow_up_edit.setDate(QDate.currentDate())
        if lead["next_follow_up"]:
            self.follow_up_check.setChecked(True)
            y, m, d = (int(p) for p in lead["next_follow_up"][:10].split("-"))
            self.follow_up_edit.setDate(QDate(y, m, d))
        form.addRow(self.follow_up_check, self.follow_up_edit)

        layout.addLayout(form)

        layout.addWidget(QLabel("Raw text from source:"))
        raw_text_view = QPlainTextEdit(lead["raw_text"])
        raw_text_view.setReadOnly(True)
        raw_text_view.setMaximumHeight(100)
        layout.addWidget(raw_text_view)

        layout.addWidget(QLabel("Notes:"))
        self.notes_edit = QPlainTextEdit(lead["notes"])
        layout.addWidget(self.notes_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self):
        follow_up = None
        clear_follow_up = False
        if self.follow_up_check.isChecked():
            follow_up = self.follow_up_edit.date().toString("yyyy-MM-dd")
        else:
            clear_follow_up = True

        self.db.update_lead(
            self.lead_id,
            stage=self.stage_combo.currentText(),
            notes=self.notes_edit.toPlainText(),
            next_follow_up=follow_up,
            clear_follow_up=clear_follow_up,
        )
        self.accept()
