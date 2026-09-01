"""Dialog for adding a lead by hand - for ones you find some other way
(a phone call, a referral, a walk-in, a business card) that none of the
automated sources would ever surface on their own.
"""

import uuid

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
)

from ..db import Database
from ..models import STAGES, LeadCandidate


class AddLeadDialog(QDialog):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db

        self.setWindowTitle("Add Lead")
        self.resize(480, 520)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.company_edit = QLineEdit()
        form.addRow("Company:", self.company_edit)

        self.contact_edit = QLineEdit()
        form.addRow("Contact name:", self.contact_edit)

        self.title_edit = QLineEdit()
        form.addRow("Title:", self.title_edit)

        self.email_edit = QLineEdit()
        form.addRow("Email:", self.email_edit)

        self.phone_edit = QLineEdit()
        form.addRow("Phone:", self.phone_edit)

        self.url_edit = QLineEdit()
        form.addRow("URL:", self.url_edit)

        self.stage_combo = QComboBox()
        self.stage_combo.addItems(STAGES)
        form.addRow("Stage:", self.stage_combo)

        self.follow_up_check = QCheckBox("Set follow-up date")
        self.follow_up_edit = QDateEdit()
        self.follow_up_edit.setCalendarPopup(True)
        self.follow_up_edit.setDate(QDate.currentDate())
        form.addRow(self.follow_up_check, self.follow_up_edit)

        layout.addLayout(form)

        layout.addWidget(QLabel("Notes:"))
        self.notes_edit = QPlainTextEdit()
        layout.addWidget(self.notes_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.company_edit.setFocus()

    def _save(self):
        company = self.company_edit.text().strip()
        contact = self.contact_edit.text().strip()
        if not company and not contact:
            QMessageBox.warning(self, "Missing info", "Enter at least a company name or a contact name.")
            return

        # A random source_detail keeps every manual entry unique, so two
        # leads you add by hand never accidentally dedupe against each
        # other the way re-discovering the same OSM place would.
        candidate = LeadCandidate(
            source="manual",
            source_detail=f"manual-{uuid.uuid4().hex}",
            company=company,
            contact_name=contact,
            title=self.title_edit.text().strip(),
            email=self.email_edit.text().strip(),
            phone=self.phone_edit.text().strip(),
            url=self.url_edit.text().strip(),
            raw_text="Added by hand.",
        )
        lead_id, _ = self.db.upsert_candidate(candidate, score=0)

        stage = self.stage_combo.currentText()
        notes = self.notes_edit.toPlainText()
        follow_up = self.follow_up_edit.date().toString("yyyy-MM-dd") if self.follow_up_check.isChecked() else None

        if stage != "New" or notes or follow_up:
            self.db.update_lead(
                lead_id,
                stage=stage,
                notes=notes,
                next_follow_up=follow_up,
                clear_follow_up=follow_up is None,
            )

        self.accept()
