# Copyright (C) 2025
# Licensed under the GPL-3.0 License.
# Created for TagStudio: https://github.com/CyanVoxel/TagStudio

"""Dialog for managing library source folders."""

from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tagstudio.qt.translations import Translations

if TYPE_CHECKING:
    from tagstudio.qt.ts_qt import QtDriver

logger = structlog.get_logger(__name__)


class ManageFoldersDialog(QWidget):
    """Dialog for managing library source folders."""

    def __init__(self, driver: "QtDriver"):
        super().__init__()
        self.driver = driver

        # Window setup
        self.setWindowTitle(Translations["manage_folders.title"])
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumSize(600, 400)

        # Main layout
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(12, 12, 12, 12)
        self.root_layout.setSpacing(12)

        # Description
        self.desc_label = QLabel(Translations["manage_folders.description"])
        self.desc_label.setWordWrap(True)
        self.desc_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        # List view for folders
        self.list_view = QListView()
        self.model = QStandardItemModel()
        self.list_view.setModel(self.model)
        self.list_view.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
        self.list_view.setSelectionMode(QListView.SelectionMode.SingleSelection)

        # Connect selection changed signal to update button states
        self.list_view.selectionModel().selectionChanged.connect(self.update_button_states)

        # Button container for folder actions
        self.action_button_container = QWidget()
        self.action_button_layout = QHBoxLayout(self.action_button_container)
        self.action_button_layout.setContentsMargins(0, 0, 0, 0)

        self.add_button = QPushButton(Translations["manage_folders.add_folder"])
        self.add_button.clicked.connect(self.add_folder)
        self.action_button_layout.addWidget(self.add_button)

        self.remove_button = QPushButton(Translations["manage_folders.remove_folder"])
        self.remove_button.clicked.connect(self.remove_folder)
        self.action_button_layout.addWidget(self.remove_button)

        self.refresh_button = QPushButton(Translations["manage_folders.refresh_folder"])
        self.refresh_button.clicked.connect(self.refresh_selected_folder)
        self.action_button_layout.addWidget(self.refresh_button)

        self.action_button_layout.addStretch(1)

        # Bottom button container
        self.button_container = QWidget()
        self.button_layout = QHBoxLayout(self.button_container)
        self.button_layout.setContentsMargins(0, 0, 0, 0)
        self.button_layout.addStretch(1)

        self.refresh_all_button = QPushButton(Translations["manage_folders.refresh_all"])
        self.refresh_all_button.clicked.connect(self.refresh_all_folders)
        self.button_layout.addWidget(self.refresh_all_button)

        self.close_button = QPushButton(Translations["generic.close"])
        self.close_button.clicked.connect(self.close)
        self.button_layout.addWidget(self.close_button)

        # Add widgets to layout
        self.root_layout.addWidget(self.desc_label)
        self.root_layout.addWidget(self.list_view)
        self.root_layout.addWidget(self.action_button_container)
        self.root_layout.addWidget(self.button_container)

        # Populate the list
        self.refresh_list()

    def refresh_list(self):
        """Refresh the list of source folders."""
        self.model.clear()
        folders = self.driver.lib.get_source_folders()

        for folder in folders:
            item = QStandardItem(str(folder.path))
            item.setData(folder.id, Qt.ItemDataRole.UserRole)
            self.model.appendRow(item)

        # Update button states
        self.update_button_states()

    def update_button_states(self):
        """Update button enabled/disabled states based on selection."""
        has_selection = len(self.list_view.selectedIndexes()) > 0
        has_folders = self.model.rowCount() > 0

        self.remove_button.setEnabled(has_selection)
        self.refresh_button.setEnabled(has_selection)
        self.refresh_all_button.setEnabled(has_folders)

    def add_folder(self):
        """Add a new source folder to the library."""
        dir_path = QFileDialog.getExistingDirectory(
            parent=self,
            caption=Translations["manage_folders.select_folder"],
            dir=str(Path.home()),
            options=QFileDialog.Option.ShowDirsOnly,
        )

        if dir_path:
            folder_path = Path(dir_path)
            try:
                self.driver.lib.add_source_folder(folder_path)
                logger.info(f"[ManageFolders] Added source folder: {folder_path}")
                self.refresh_list()

                # Ask if user wants to scan the folder now
                msg_box = QMessageBox()
                msg_box.setWindowTitle(Translations["library.scan_folder.title"])
                msg_box.setText(
                    Translations.format(
                        "library.scan_folder.message", folder_path=folder_path.name
                    )
                )
                msg_box.setStandardButtons(
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                msg_box.setDefaultButton(QMessageBox.StandardButton.Yes)

                if msg_box.exec() == QMessageBox.StandardButton.Yes:
                    self.driver.add_new_files_callback()

            except Exception as e:
                logger.error(f"[ManageFolders] Failed to add source folder: {e}")
                QMessageBox.critical(
                    self,
                    Translations["manage_folders.error_add_title"],
                    Translations.format("manage_folders.error_add_message", error=str(e)),
                )

    def remove_folder(self):
        """Remove the selected source folder from the library."""
        selected_indexes = self.list_view.selectedIndexes()
        if not selected_indexes:
            return

        index = selected_indexes[0]
        folder_id = self.model.data(index, Qt.ItemDataRole.UserRole)
        folder_path = self.model.data(index, Qt.ItemDataRole.DisplayRole)

        # Confirm removal
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setWindowTitle(Translations["manage_folders.confirm_remove_title"])
        msg_box.setText(
            Translations.format("manage_folders.confirm_remove_message", path=folder_path)
        )
        msg_box.setInformativeText(Translations["manage_folders.confirm_remove_info"])
        msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg_box.setDefaultButton(QMessageBox.StandardButton.No)

        if msg_box.exec() == QMessageBox.StandardButton.Yes:
            try:
                self.driver.lib.remove_source_folder(folder_id)
                logger.info(f"[ManageFolders] Removed source folder: {folder_path}")
                self.refresh_list()
                # Refresh the main library view to show removed entries
                self.driver.update_browsing_state()
            except Exception as e:
                logger.error(f"[ManageFolders] Failed to remove source folder: {e}")
                QMessageBox.critical(
                    self,
                    Translations["manage_folders.error_remove_title"],
                    Translations.format("manage_folders.error_remove_message", error=str(e)),
                )

    def refresh_selected_folder(self):
        """Refresh the selected source folder."""
        selected_indexes = self.list_view.selectedIndexes()
        if not selected_indexes:
            return

        index = selected_indexes[0]
        folder_id = self.model.data(index, Qt.ItemDataRole.UserRole)

        # Get the folder object
        folders = self.driver.lib.get_source_folders()
        folder = next((f for f in folders if f.id == folder_id), None)

        if folder:
            logger.info(f"[ManageFolders] Refreshing folder: {folder.path}")
            self.driver.add_new_files_callback()

    def refresh_all_folders(self):
        """Refresh all source folders."""
        logger.info("[ManageFolders] Refreshing all folders")
        self.driver.add_new_files_callback()
