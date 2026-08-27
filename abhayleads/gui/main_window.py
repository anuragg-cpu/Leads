"""Main CRM window."""

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QActionGroup, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
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
from ..profiles import (
    create_profile,
    delete_profile,
    list_profiles,
    profile_paths,
    set_active_profile,
)
from .config_editor_dialog import ConfigEditorDialog
from .detail_dialog import LeadDetailDialog
from .fetch_worker import FetchWorker

COLUMNS = ["ID", "Score", "Stage", "Company", "Contact", "Title", "Source", "Follow-up", "Last seen"]


class MainWindow(QMainWindow):
    def __init__(self, db_path: Path, config_path: Optional[Path] = None, profile_name: Optional[str] = None):
        super().__init__()
        self.db_path = db_path
        self.config_path = config_path
        self.profile_name = profile_name
        self.db = Database(db_path)
        self.worker: Optional[FetchWorker] = None

        self.resize(1100, 650)
        self._update_window_title()

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
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_table_context_menu)
        layout.addWidget(self.table)

        open_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Return), self.table)
        open_shortcut.activated.connect(self._open_selected_lead)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self._build_menu()
        self.refresh()

    def _update_window_title(self):
        suffix = f" - {self.profile_name}" if self.profile_name else ""
        self.setWindowTitle(f"Abhay Leads{suffix}")

    # -- menu bar --------------------------------------------------------------

    def _build_menu(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&File")

        edit_config_action = QAction("Edit Config (keywords, sources)...", self)
        edit_config_action.triggered.connect(self._edit_config)
        file_menu.addAction(edit_config_action)

        file_menu.addSeparator()

        reset_action = QAction("Reset All Leads (start over)...", self)
        reset_action.triggered.connect(self._reset_leads)
        file_menu.addAction(reset_action)

        file_menu.addSeparator()
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        self.profile_menu = menu_bar.addMenu("&Profile")
        self._rebuild_profile_menu()

    def _rebuild_profile_menu(self):
        self.profile_menu.clear()
        group = QActionGroup(self)
        group.setExclusive(True)

        for name in list_profiles():
            action = QAction(name, self, checkable=True)
            action.setChecked(name == self.profile_name)
            action.triggered.connect(lambda checked, n=name: self._switch_profile(n))
            group.addAction(action)
            self.profile_menu.addAction(action)

        self.profile_menu.addSeparator()

        new_action = QAction("New Profile...", self)
        new_action.triggered.connect(self._new_profile)
        self.profile_menu.addAction(new_action)

        delete_action = QAction("Delete Current Profile...", self)
        delete_action.triggered.connect(self._delete_current_profile)
        self.profile_menu.addAction(delete_action)

    def _switch_profile(self, name: str):
        if name == self.profile_name:
            return
        config_path, db_path = profile_paths(name)
        set_active_profile(name)

        self.db.close()
        self.db_path = db_path
        self.config_path = config_path
        self.profile_name = name
        self.db = Database(db_path)

        self._update_window_title()
        self._rebuild_profile_menu()
        self.refresh()

    def _new_profile(self):
        name, ok = QInputDialog.getText(
            self, "New Profile", "Name for the new product/company (its own keywords + leads):"
        )
        if not ok or not name.strip():
            return
        try:
            create_profile(name.strip())
        except ValueError as exc:
            QMessageBox.warning(self, "Couldn't create profile", str(exc))
            return
        self._switch_profile(name.strip())
        QMessageBox.information(
            self,
            "Profile created",
            f'"{name.strip()}" is ready with a blank config. Use File -> Edit Config to add its keywords.',
        )

    def _delete_current_profile(self):
        if not self.profile_name:
            return
        confirm = QMessageBox.question(
            self,
            "Delete profile?",
            f'Remove "{self.profile_name}" from the profile list?\n\n'
            "Its config.yaml and leads.db are kept on disk unless you choose to also delete them.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        also_delete_files = QMessageBox.question(
            self,
            "Delete its files too?",
            "Also permanently delete its config.yaml and leads.db? This can't be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes

        deleted_name = self.profile_name
        delete_profile(deleted_name, delete_files=also_delete_files)

        remaining = list_profiles()
        if remaining:
            self._switch_profile(remaining[0])
        else:
            create_profile("default")
            self._switch_profile("default")

    def _edit_config(self):
        if self.config_path is None:
            QMessageBox.information(
                self, "No profile config", "This window wasn't opened with a profile - nothing to edit here."
            )
            return
        dialog = ConfigEditorDialog(self.config_path, self)
        if dialog.exec():
            self.status_bar.showMessage("Config saved.", 5000)

    def _reset_leads(self):
        confirm = QMessageBox.question(
            self,
            "Delete ALL leads?",
            f"This permanently deletes every lead in this profile{f' ({self.profile_name})' if self.profile_name else ''}.\n"
            "This can't be undone. Your config.yaml is not affected.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        count = self.db.delete_all_leads()
        self.status_bar.showMessage(f"Deleted {count} lead(s). Run Find New Leads to start over.", 8000)
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

    def _show_table_context_menu(self, position):
        if self.table.itemAt(position) is None:
            return
        menu = QMenu(self)
        open_action = menu.addAction("Open / Edit Lead...")
        action = menu.exec(self.table.viewport().mapToGlobal(position))
        if action == open_action:
            self._open_selected_lead()

    def closeEvent(self, event):
        self.db.close()
        super().closeEvent(event)
