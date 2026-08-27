"""Detail/edit dialog for a single lead."""

from PyQt6.QtCore import QDate, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from ..db import Database
from ..models import STAGES


class LeadDetailDialog(QDialog):
    """Full view/edit screen for one lead - opened by double-clicking a
    row, pressing Enter on a selected row, or the table's right-click
    menu. Every field a source might have gotten wrong or left blank
    (company name, contact, email, phone, URL) is editable here, since
    OSM/news sources rarely have a phone number - you fill that in once
    you've actually called or visited the place.
    """

    def __init__(self, db: Database, lead_id: int, parent=None):
        super().__init__(parent)
        self.db = db
        self.lead_id = lead_id
        lead = db.get_lead(lead_id)

        self.setWindowTitle(f"Lead #{lead_id} - {lead['company'] or lead['contact_name'] or lead['source']}")
        self.resize(560, 620)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.company_edit = QLineEdit(lead["company"])
        form.addRow("Company:", self.company_edit)

        self.contact_edit = QLineEdit(lead["contact_name"])
        form.addRow("Contact name:", self.contact_edit)

        self.title_edit = QLineEdit(lead["title"])
        form.addRow("Title:", self.title_edit)

        self.email_edit = QLineEdit(lead["email"])
        form.addRow("Email:", self.email_edit)

        self.phone_edit = QLineEdit(lead["phone"])
        form.addRow("Phone:", self.phone_edit)

        url_row = QHBoxLayout()
        self.url_edit = QLineEdit(lead["url"])
        url_row.addWidget(self.url_edit)
        open_url_button = QPushButton("Open")
        open_url_button.clicked.connect(self._open_url)
        url_row.addWidget(open_url_button)
        form.addRow("URL:", url_row)

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

    def _open_url(self):
        url = self.url_edit.text().strip()
        if url:
            QDesktopServices.openUrl(QUrl(url))

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
            company=self.company_edit.text(),
            contact_name=self.contact_edit.text(),
            title=self.title_edit.text(),
            email=self.email_edit.text(),
            phone=self.phone_edit.text(),
            url=self.url_edit.text(),
        )
        self.accept()
