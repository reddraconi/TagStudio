# Copyright (C) 2025 Travis Abendshien (CyanVoxel).
# Licensed under the GPL-3.0 License.
# Created for TagStudio: https://github.com/CyanVoxel/TagStudio


from typing import TYPE_CHECKING, override

from PySide6 import QtCore, QtGui
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from tagstudio.qt.mixed.tag_widget import TagWidget

if TYPE_CHECKING:
    from tagstudio.core.library.alchemy.library import Library


class PasteTagsDialog(QWidget):
    """Dialog for choosing merge or replace when pasting tags."""

    mode_selected = Signal(str)  # Emits "merge" or "replace"

    def __init__(
        self,
        tags_clipboard: set[int],
        selected_entries: list,
        library: "Library",
        preset_mode: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Window)
        self.setWindowTitle("Paste Tags")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumSize(500, 300)
        self.selected_mode = preset_mode
        self.remember_choice = False
        self.preset_mode = preset_mode

        # Store data for delta calculation
        self.tags_clipboard = tags_clipboard
        self.selected_entries = selected_entries
        self.library = library

        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(6, 6, 6, 6)

        if preset_mode:
            mode_text = "merge" if preset_mode == "merge" else "replace"
            self.desc_label = QLabel(f"The following changes will be made ({mode_text} mode):")
        else:
            self.desc_label = QLabel("How would you like to paste the tags?")
        self.desc_label.setWordWrap(True)
        self.root_layout.addWidget(self.desc_label)

        if not preset_mode:
            self.button_group = QButtonGroup(self)

            self.merge_radio = QRadioButton("Merge - Add copied tags to existing tags")
            self.merge_radio.setChecked(True)
            self.merge_radio.toggled.connect(self._update_delta_display)
            self.button_group.addButton(self.merge_radio)
            self.root_layout.addWidget(self.merge_radio)

            self.replace_radio = QRadioButton("Replace - Remove existing tags and add copied tags")
            self.replace_radio.toggled.connect(self._update_delta_display)
            self.button_group.addButton(self.replace_radio)
            self.root_layout.addWidget(self.replace_radio)

            self.root_layout.addSpacing(12)

            self.remember_checkbox = QCheckBox("Remember my choice and don't ask again")
            self.root_layout.addWidget(self.remember_checkbox)

        self._build_delta_display()

        self.root_layout.addStretch()

        self.button_widget = QWidget()
        self.button_layout = QHBoxLayout(self.button_widget)
        self.button_layout.setContentsMargins(6, 6, 6, 6)
        self.button_layout.addStretch(1)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        self.button_layout.addWidget(self.cancel_button)

        self.ok_button = QPushButton("OK")
        self.ok_button.setDefault(True)
        self.ok_button.clicked.connect(self.accept_choice)
        self.button_layout.addWidget(self.ok_button)

        self.root_layout.addWidget(self.button_widget)

    def _build_delta_display(self):
        """Build the scrollable delta display showing tag changes."""
        self.delta_scroll = QScrollArea()
        self.delta_scroll.setWidgetResizable(True)
        self.delta_scroll.setFrameShape(QFrame.Shape.StyledPanel)
        self.delta_scroll.setMinimumHeight(150)
        self.delta_scroll.setMaximumHeight(400)

        self.delta_container = QWidget()
        self.delta_layout = QVBoxLayout(self.delta_container)
        self.delta_layout.setContentsMargins(6, 6, 6, 6)
        self.delta_layout.setSpacing(12)

        self._populate_delta_display()

        self.delta_scroll.setWidget(self.delta_container)
        self.root_layout.insertWidget(1, self.delta_scroll)

    def _populate_delta_display(self):
        """Populate delta display with entry changes."""
        while self.delta_layout.count():
            child = self.delta_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if self.preset_mode:
            mode = self.preset_mode
        else:
            mode = "merge" if self.merge_radio.isChecked() else "replace"

        for entry in self.selected_entries:
            entry_widget = self._create_entry_delta_widget(entry, mode)
            self.delta_layout.addWidget(entry_widget)

        self.delta_layout.addStretch()

    def _create_entry_delta_widget(self, entry, mode: str):
        """Create widget showing tag changes for entry."""
        entry_widget = QFrame()
        entry_widget.setFrameShape(QFrame.Shape.StyledPanel)
        entry_layout = QVBoxLayout(entry_widget)
        entry_layout.setContentsMargins(8, 8, 8, 8)
        entry_layout.setSpacing(6)

        entry_label = QLabel(f"<b>{entry.filename}</b>")
        entry_layout.addWidget(entry_label)

        current_tag_ids = {tag.id for tag in entry.tags}

        tags_to_add = self.tags_clipboard - current_tag_ids
        tags_to_remove = current_tag_ids - self.tags_clipboard if mode == "replace" else set()

        if tags_to_add:
            add_container = QWidget()
            add_layout = QHBoxLayout(add_container)
            add_layout.setContentsMargins(0, 0, 0, 0)
            add_layout.setSpacing(4)

            add_label = QLabel("+ Add:")
            add_label.setStyleSheet("color: green; font-weight: bold;")
            add_layout.addWidget(add_label)

            tags_flow = QWidget()
            tags_flow_layout = QHBoxLayout(tags_flow)
            tags_flow_layout.setContentsMargins(0, 0, 0, 0)
            tags_flow_layout.setSpacing(4)

            for tag_id in sorted(tags_to_add):
                tag = self.library.get_tag(tag_id)
                if tag:
                    tag_widget = TagWidget(
                        tag=tag,
                        has_edit=False,
                        has_remove=False,
                        library=self.library,
                    )
                    tags_flow_layout.addWidget(tag_widget)

            tags_flow_layout.addStretch()
            add_layout.addWidget(tags_flow)
            entry_layout.addWidget(add_container)

        if tags_to_remove:
            remove_container = QWidget()
            remove_layout = QHBoxLayout(remove_container)
            remove_layout.setContentsMargins(0, 0, 0, 0)
            remove_layout.setSpacing(4)

            remove_label = QLabel("- Remove:")
            remove_label.setStyleSheet("color: red; font-weight: bold;")
            remove_layout.addWidget(remove_label)

            tags_flow = QWidget()
            tags_flow_layout = QHBoxLayout(tags_flow)
            tags_flow_layout.setContentsMargins(0, 0, 0, 0)
            tags_flow_layout.setSpacing(4)

            for tag_id in sorted(tags_to_remove):
                tag = self.library.get_tag(tag_id)
                if tag:
                    tag_widget = TagWidget(
                        tag=tag,
                        has_edit=False,
                        has_remove=False,
                        library=self.library,
                    )
                    tags_flow_layout.addWidget(tag_widget)

            tags_flow_layout.addStretch()
            remove_layout.addWidget(tags_flow)
            entry_layout.addWidget(remove_container)

        if not tags_to_add and not tags_to_remove:
            no_change_label = QLabel("No changes")
            no_change_label.setStyleSheet("color: gray; font-style: italic;")
            entry_layout.addWidget(no_change_label)

        return entry_widget

    def _update_delta_display(self):
        """Update the delta display when mode changes."""
        self._populate_delta_display()

    def accept_choice(self):
        """Accept the dialog and emit the selected mode."""
        if self.preset_mode:
            self.selected_mode = self.preset_mode
            self.remember_choice = False
        else:
            self.selected_mode = "merge" if self.merge_radio.isChecked() else "replace"
            self.remember_choice = self.remember_checkbox.isChecked()
        self.mode_selected.emit(self.selected_mode)
        self.close()

    def reject(self):
        """Cancel the dialog."""
        self.selected_mode = None
        self.close()

    @override
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:  # noqa N802
        if event.key() == QtCore.Qt.Key.Key_Escape:
            self.reject()
        elif event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
            self.accept_choice()
        else:
            return super().keyPressEvent(event)
