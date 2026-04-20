# Copyright (C) 2025
# Licensed under the GPL-3.0 License.
# Created for TagStudio: https://github.com/CyanVoxel/TagStudio


from pathlib import Path
from typing import TYPE_CHECKING, override

import structlog
from PySide6 import QtGui
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QListWidgetItem, QMessageBox

from tagstudio.core.library.alchemy.library import Library
from tagstudio.core.library.alchemy.models import Folder
from tagstudio.qt.translations import Translations
from tagstudio.qt.views.manage_folders_modal_view import ManageFoldersModalView

if TYPE_CHECKING:
    from tagstudio.qt.ts_qt import QtDriver

logger = structlog.get_logger(__name__)

_PRIMARY_ROLE = "primary"


class ManageFoldersModal(ManageFoldersModalView):
    def __init__(self, library: "Library", driver: "QtDriver"):
        super().__init__(library, driver)

        self.add_button.clicked.connect(self._add_folder_callback)
        self.remove_button.clicked.connect(self._remove_folder_callback)
        self.done_button.clicked.connect(self.hide)
        self.folder_list.itemSelectionChanged.connect(self._on_selection_changed)

        # Tracks whether a folder was added during this session; the library
        # scan is deferred until the dialog closes so the modal stays open
        # while the user adds multiple folders in one go, and only one scan
        # is performed at the end rather than one per add.
        self._pending_scan = False

        self._refresh_folder_list()

    def _refresh_folder_list(self) -> None:
        self.folder_list.clear()
        primary_path = self.lib.library_dir

        rows: list[tuple[Folder | None, str, object]] = []
        if self.lib.folder is not None:
            rows.append((None, f"{self.lib.folder.path}  —  primary", _PRIMARY_ROLE))

        for folder in sorted(self.lib.folders, key=lambda f: f.path.as_posix()):
            if folder.path == primary_path:
                continue
            rows.append((folder, str(folder.path), folder.id))

        for _, label, role in rows:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, role)
            if role == _PRIMARY_ROLE:
                flags = item.flags() & ~Qt.ItemFlag.ItemIsSelectable
                item.setFlags(flags)
            self.folder_list.addItem(item)

        self.remove_button.setEnabled(False)

    def _on_selection_changed(self) -> None:
        item = self.folder_list.currentItem()
        if item is None:
            self.remove_button.setEnabled(False)
            return
        role = item.data(Qt.ItemDataRole.UserRole)
        self.remove_button.setEnabled(role != _PRIMARY_ROLE)

    # --- Qt-isolated helpers (stubbed in tests) ------------------------------

    def _prompt_for_folder(self) -> Path | None:
        start_dir = str(self.lib.library_dir) if self.lib.library_dir else "/"
        chosen = QFileDialog.getExistingDirectory(
            parent=self,
            caption=Translations["library.folders.add"],
            dir=start_dir,
            options=QFileDialog.Option.ShowDirsOnly,
        )
        if chosen in (None, ""):
            return None
        return Path(chosen)

    def _confirm_remove(self, path: Path, entry_count: int) -> bool:
        message = Translations.format(
            "library.folders.confirm_remove",
            path=str(path),
            count=entry_count,
        )
        reply = QMessageBox.question(
            self,
            Translations["library.folders.remove"],
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _show_error(self, text: str) -> None:
        QMessageBox.warning(self, Translations["library.folders.title"], text)

    # --- Core business logic (unit-testable) ---------------------------------

    def _add_folder_callback(self) -> None:
        path = self._prompt_for_folder()
        if path is None:
            return
        try:
            self.lib.add_folder(path)
        except ValueError as e:
            self._show_error(str(e))
            return
        self._refresh_folder_list()
        self._pending_scan = True

    def _remove_folder_callback(self) -> None:
        item = self.folder_list.currentItem()
        if item is None:
            return
        role = item.data(Qt.ItemDataRole.UserRole)
        if role == _PRIMARY_ROLE:
            return

        folder = next((f for f in self.lib.folders if f.id == role), None)
        if folder is None:
            self._refresh_folder_list()
            return

        entry_count = self.lib.folder_entry_count(folder)
        if not self._confirm_remove(folder.path, entry_count):
            return

        try:
            self.lib.remove_folder(folder, delete_entries=True)
        except ValueError as e:
            self._show_error(str(e))
            return

        self._refresh_folder_list()
        self.driver.update_browsing_state()

    @override
    def showEvent(self, event: QtGui.QShowEvent) -> None:  # type: ignore
        self._refresh_folder_list()
        return super().showEvent(event)

    @override
    def hideEvent(self, event: QtGui.QHideEvent) -> None:  # type: ignore
        # Trigger the deferred scan only after the modal is off-screen so the
        # scan's ProgressWidget becomes the top-level window cleanly. Running
        # it while an application-modal dialog is still visible has caused
        # popup-parenting segfaults under Wayland.
        super().hideEvent(event)
        if self._pending_scan:
            self._pending_scan = False
            self.driver.call_if_library_open(self.driver.add_new_files_callback)
