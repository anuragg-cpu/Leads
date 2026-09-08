"""Dialog for adding a lead by hand - for ones you find some other way
(a phone call, a referral, a walk-in, a business card) that none of the
automated sources would ever surface on their own.
"""

import uuid
from typing import Optional

from PyQt6.QtCore import QDate, Qt
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
from ..google_maps_link import parse_google_maps_link, split_links
from ..models import STAGES, LeadCandidate
from ..remote_db import RemoteDatabase


class AddLeadDialog(QDialog):
    def __init__(self, db: Database | RemoteDatabase, parent=None):
        super().__init__(parent)
        self.db = db

        self.setWindowTitle("Add Lead")
        self.resize(480, 560)
        self._lat: Optional[float] = None
        self._lon: Optional[float] = None

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Google Maps link(s) - one per line to add several places at once:"))
        gmaps_row = QHBoxLayout()
        self.gmaps_link_edit = QPlainTextEdit()
        self.gmaps_link_edit.setPlaceholderText(
            "Paste a Google Maps link for the place (optional)...\n"
            "Paste several, one per line, to add them all as separate leads at once."
        )
        self.gmaps_link_edit.setMaximumHeight(70)
        gmaps_row.addWidget(self.gmaps_link_edit, stretch=1)
        gmaps_fetch_button = QPushButton("Fetch")
        gmaps_fetch_button.clicked.connect(self._fetch_from_google_maps_link)
        gmaps_row.addWidget(gmaps_fetch_button)
        layout.addLayout(gmaps_row)

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

    def _fetch_from_google_maps_link(self):
        links = split_links(self.gmaps_link_edit.toPlainText())
        if not links:
            return

        if len(links) > 1:
            self._bulk_add_from_links(links)
            return

        self.setCursor(Qt.CursorShape.WaitCursor)
        try:
            parsed = parse_google_maps_link(links[0])
        finally:
            self.unsetCursor()

        if not parsed.company and parsed.lat is None:
            QMessageBox.information(
                self,
                "Couldn't read that link",
                "No place name or coordinates found in that link. This works best with a full "
                "Google Maps place link (open the place, then Share -> Copy link) - a plain "
                "search-results or already-shortened business listing link may not have "
                "enough encoded in the URL itself. You can still fill in the fields by hand.",
            )
            return

        if parsed.company and not self.company_edit.text().strip():
            self.company_edit.setText(parsed.company)
        if not self.url_edit.text().strip():
            self.url_edit.setText(parsed.url)
        self._lat, self._lon = parsed.lat, parsed.lon

    def _bulk_add_from_links(self, links: list[str]):
        """Several links pasted at once - each becomes its own lead
        immediately (there's no single Company/Contact for the rest of
        this form to apply to N different places), sharing whatever
        Stage/Notes/follow-up is currently set in the form. Unlike the
        single-link case, this commits right away rather than waiting
        for Save, since there's nothing left on this form for the user
        to fill in per-lead."""
        stage = self.stage_combo.currentText()
        notes = self.notes_edit.toPlainText()
        follow_up = self.follow_up_edit.date().toString("yyyy-MM-dd") if self.follow_up_check.isChecked() else None

        self.setCursor(Qt.CursorShape.WaitCursor)
        added, skipped = 0, []
        try:
            for link in links:
                parsed = parse_google_maps_link(link)
                if not parsed.company and parsed.lat is None:
                    skipped.append(link)
                    continue

                candidate = LeadCandidate(
                    source="manual",
                    source_detail=f"manual-{uuid.uuid4().hex}",
                    company=parsed.company,
                    url=parsed.url,
                    raw_text="Added by hand from a pasted Google Maps link.",
                    lat=parsed.lat,
                    lon=parsed.lon,
                )
                lead_id, _ = self.db.upsert_candidate(candidate, score=0)
                if stage != "New" or notes or follow_up:
                    self.db.update_lead(
                        lead_id, stage=stage, notes=notes, next_follow_up=follow_up, clear_follow_up=follow_up is None
                    )
                added += 1
        finally:
            self.unsetCursor()

        message = f"Added {added} lead(s) from {len(links)} link(s)."
        if skipped:
            message += (
                f"\n\n{len(skipped)} link(s) had no name or coordinates and were skipped "
                "(works best with a full place link - open the place, then Share -> Copy link):\n"
                + "\n".join(skipped)
            )
        QMessageBox.information(self, "Bulk add complete", message)

        if added:
            self.accept()

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
            lat=self._lat,
            lon=self._lon,
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
