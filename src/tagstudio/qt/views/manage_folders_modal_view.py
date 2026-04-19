# Copyright (C) 2025
# Licensed under the GPL-3.0 License.
# Created for TagStudio: https://github.com/CyanVoxel/TagStudio


from typing import TYPE_CHECKING, override

from PySide6 import QtCore, QtGui
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tagstudio.core.library.alchemy.library import Library
from tagstudio.qt.translations import Translations

if TYPE_CHECKING:
    from tagstudio.qt.ts_qt import QtDriver


class ManageFoldersModalView(QWidget):
    def __init__(self, library: "Library", driver: "QtDriver"):
        super().__init__()
        self.lib = library
        self.driver = driver

        self.setWindowTitle(Translations["library.folders.title"])
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumSize(480, 320)
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(6, 6, 6, 6)

        self.description_label = QLabel(Translations["library.folders.description"])
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet("text-align:left;")

        self.folder_list = QListWidget()
        self.folder_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)

        self.add_button = QPushButton(Translations["library.folders.add"])
        self.remove_button = QPushButton(Translations["library.folders.remove"])
        self.remove_button.setEnabled(False)

        self.action_container = QWidget()
        self.action_layout = QHBoxLayout(self.action_container)
        self.action_layout.setContentsMargins(0, 0, 0, 0)
        self.action_layout.addWidget(self.add_button)
        self.action_layout.addWidget(self.remove_button)
        self.action_layout.addStretch(1)

        self.button_container = QWidget()
        self.button_layout = QHBoxLayout(self.button_container)
        self.button_layout.setContentsMargins(6, 6, 6, 6)
        self.button_layout.addStretch(1)

        self.done_button = QPushButton(Translations["generic.done_alt"])
        self.done_button.setDefault(True)
        self.button_layout.addWidget(self.done_button)

        self.root_layout.addWidget(self.description_label)
        self.root_layout.addWidget(self.folder_list)
        self.root_layout.addWidget(self.action_container)
        self.root_layout.addStretch(1)
        self.root_layout.addWidget(self.button_container)

    @override
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:  # noqa: N802
        if event.key() == QtCore.Qt.Key.Key_Escape:
            self.done_button.click()
        return super().keyPressEvent(event)
