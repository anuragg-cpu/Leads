"""Main CRM window."""

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..config import load_config
from ..db import Database
from ..models import STAGES
from .detail_dialog import LeadDetailDialog
from .fetch_worker import FetchWorker

COLUMNS = ["ID", "Score", "Stage", "Company", "Contact", "Title", "Source", "Follow-up", "Last seen"]


class MainWindow(QMainWindow):
    def __init__(self, db_path: Path, config_path: Optional[Path] = None):
        super().__init__()
        self.db_path = db_path
        self.config_path = config_path
        self.db = Database(db_path)
        self.worker: Optional[FetchWorker] = None

        self.setWindowTitle("Abhay Leads")
        self.resize(1100, 650)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        layout.addLayout(self._build_toolbar())

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(self._open_selected_lead)
        layout.addWidget(self.table)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.refresh()

    # -- toolbar -----------------------------------------------------------

    def _build_toolbar(self) -> QHBoxLayout:
        row = QHBoxLayout()

        self.fetch_button = QPushButton("Find New Leads")
        self.fetch_button.clicked.connect(self._start_fetch)
        row.addWidget(self.fetch_button)

        row.addWidget(QLabel("Stage:"))
        self.stage_filter = QComboBox()
        self.stage_filter.addItems(["All"] + STAGES)
        self.stage_filter.currentIndexChanged.connect(self.refresh)
        row.addWidget(self.stage_filter)

        row.addWidget(QLabel("Min score:"))
        self.min_score = QSpinBox()
        self.min_score.setRange(0, 100)
        self.min_score.valueChanged.connect(self.refresh)
        row.addWidget(self.min_score)

        self.due_only = QCheckBox("Due for follow-up only")
        self.due_only.stateChanged.connect(self.refresh)
        row.addWidget(self.due_only)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search company / name / title / text...")
        self.search_box.returnPressed.connect(self.refresh)
        row.addWidget(self.search_box, stretch=1)

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh)
        row.addWidget(refresh_button)

        return row

    # -- fetch ---------------------------------------------------------------

    def _start_fetch(self):
        config = load_config(self.config_path)
        self.fetch_button.setEnabled(False)
        self.fetch_button.setText("Searching...")
        self.status_bar.showMessage("Starting fetch...")

        self.worker = FetchWorker(self.db_path, config)
        self.worker.progress.connect(self.status_bar.showMessage)
        self.worker.finished_ok.connect(self._fetch_done)
        self.worker.finished_error.connect(self._fetch_failed)
        self.worker.start()

    def _fetch_done(self, result):
        self.fetch_button.setEnabled(True)
        self.fetch_button.setText("Find New Leads")
        msg = f"Fetch complete: {result.new_leads} new, {result.updated_leads} updated."
        if result.errors:
            msg += f" {len(result.errors)} source error(s) - see below."
        self.status_bar.showMessage(msg, 15000)
        if result.errors:
            QMessageBox.warning(self, "Some sources had errors", "\n".join(result.errors))
        self.refresh()

    def _fetch_failed(self, error: str):
        self.fetch_button.setEnabled(True)
        self.fetch_button.setText("Find New Leads")
        self.status_bar.showMessage("Fetch failed.", 10000)
        QMessageBox.critical(self, "Fetch failed", error)

    # -- table ---------------------------------------------------------------

    def refresh(self):
        stage = self.stage_filter.currentText()
        leads = self.db.list_leads(
            stage=None if stage == "All" else stage,
            min_score=self.min_score.value(),
            due_only=self.due_only.isChecked(),
            search=self.search_box.text() or None,
        )

        self.table.setRowCount(len(leads))
        for row_idx, lead in enumerate(leads):
            values = [
                str(lead["id"]),
                str(lead["score"]),
                lead["stage"],
                lead["company"],
                lead["contact_name"],
                lead["title"],
                lead["source"],
                lead["next_follow_up"] or "",
                lead["last_seen_at"][:10],
            ]
            for col_idx, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, lead["id"])
                self.table.setItem(row_idx, col_idx, item)

        stats = self.db.stats()
        self.status_bar.showMessage(
            f"{stats['total']} total leads | {stats['due_for_follow_up']} due for follow-up | "
            f"showing {len(leads)}"
        )

    def _open_selected_lead(self):
        row = self.table.currentRow()
        if row < 0:
            return
        lead_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        dialog = LeadDetailDialog(self.db, lead_id, self)
        if dialog.exec():
            self.refresh()

    def closeEvent(self, event):
        self.db.close()
        super().closeEvent(event)
