"""Detail/edit dialog for a single lead."""

from typing import Optional

from PyQt6.QtCore import QDate, Qt, QUrl
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
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from ..db import Database
from ..google_maps_link import parse_google_maps_link
from ..models import STAGES
from ..remote_db import RemoteDatabase


class LeadDetailDialog(QDialog):
    """Full view/edit screen for one lead - opened by double-clicking a
    row, pressing Enter on a selected row, or the table's right-click
    menu. Every field a source might have gotten wrong or left blank
    (company name, contact, email, phone, URL) is editable here, since
    OSM/news sources rarely have a phone number - you fill that in once
    you've actually called or visited the place.
    """

    def __init__(self, db: Database | RemoteDatabase, lead_id: int, parent=None):
        super().__init__(parent)
        self.db = db
        self.lead_id = lead_id
        lead = db.get_lead(lead_id)

        self.setWindowTitle(f"Lead #{lead_id} - {lead['company'] or lead['contact_name'] or lead['source']}")
        self.resize(560, 660)
        self._lat: Optional[float] = lead["lat"]
        self._lon: Optional[float] = lead["lon"]

        layout = QVBoxLayout(self)

        gmaps_row = QHBoxLayout()
        self.gmaps_link_edit = QLineEdit()
        self.gmaps_link_edit.setPlaceholderText("Paste a Google Maps link to add/update this lead's location...")
        gmaps_row.addWidget(self.gmaps_link_edit, stretch=1)
        gmaps_fetch_button = QPushButton("Fetch")
        gmaps_fetch_button.clicked.connect(self._fetch_from_google_maps_link)
        gmaps_row.addWidget(gmaps_fetch_button)
        layout.addLayout(gmaps_row)

        self.location_label = QLabel()
        self._update_location_label()
        layout.addWidget(self.location_label)

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

    def _update_location_label(self):
        if self._lat is not None and self._lon is not None:
            self.location_label.setText(f"Location: {self._lat:.5f}, {self._lon:.5f}")
        else:
            self.location_label.setText("Location: not set")

    def _fetch_from_google_maps_link(self):
        link = self.gmaps_link_edit.text().strip()
        if not link:
            return

        self.setCursor(Qt.CursorShape.WaitCursor)
        try:
            parsed = parse_google_maps_link(link)
        finally:
            self.unsetCursor()

        if not parsed.company and parsed.lat is None:
            QMessageBox.information(
                self,
                "Couldn't read that link",
                "No place name or coordinates found in that link. This works best with a full "
                "Google Maps place link (open the place, then Share -> Copy link) - a plain "
                "search-results or already-shortened business listing link may not have "
                "enough encoded in the URL itself.",
            )
            return

        # Never overwrite fields this lead already has - the link is here
        # to backfill what's missing (usually just the location), not to
        # silently replace a company name you or a source already set.
        if parsed.company and not self.company_edit.text().strip():
            self.company_edit.setText(parsed.company)
        if parsed.url and not self.url_edit.text().strip():
            self.url_edit.setText(parsed.url)
        if parsed.lat is not None and parsed.lon is not None:
            self._lat, self._lon = parsed.lat, parsed.lon
            self._update_location_label()

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
            lat=self._lat,
            lon=self._lon,
        )
        self.accept()
