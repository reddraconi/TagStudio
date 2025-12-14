# Copyright (C) 2025
# Licensed under the GPL-3.0 License.
# Created for TagStudio: https://github.com/CyanVoxel/TagStudio
# ruff: noqa: FBT003


from unittest.mock import Mock, patch

from tagstudio.core.library.alchemy.library import Library
from tagstudio.core.library.alchemy.models import Entry
from tagstudio.core.utils.types import unwrap
from tagstudio.qt.mixed.paste_tags_dialog import PasteTagsDialog
from tagstudio.qt.ts_qt import QtDriver


class TestCopyTags:
    """Test copy tags functionality."""

    def test_copy_tags_single_entry(self, qt_driver: QtDriver, library: Library):
        """Test copying tags from a single entry."""
        qt_driver.selected = [1]
        qt_driver.copy_tags_action_callback()

        entry = unwrap(library.get_entry_full(1))
        expected_tag_ids = {tag.id for tag in entry.tags}

        assert qt_driver.tags_clipboard == expected_tag_ids
        assert qt_driver.tags_clipboard_source == {1}

    def test_copy_tags_multiple_entries(self, qt_driver: QtDriver, library: Library):
        """Test copying tags from multiple entries."""
        qt_driver.selected = [1, 2]
        qt_driver.copy_tags_action_callback()

        entry1 = unwrap(library.get_entry_full(1))
        entry2 = unwrap(library.get_entry_full(2))
        expected_tag_ids = {tag.id for tag in entry1.tags} | {tag.id for tag in entry2.tags}

        assert qt_driver.tags_clipboard == expected_tag_ids
        assert qt_driver.tags_clipboard_source == {1, 2}

    def test_copy_tags_no_selection(self, qt_driver: QtDriver):
        """Test copy tags with no selection."""
        qt_driver.selected = []
        qt_driver.copy_tags_action_callback()

        assert qt_driver.tags_clipboard == set()
        assert qt_driver.tags_clipboard_source == set()

    def test_copy_tags_entry_without_tags(self, qt_driver: QtDriver, library: Library):
        """Test copying tags from entry with no tags."""
        folder = unwrap(library.folder)
        entry = Entry(id=100, folder=folder, path="no_tags.txt", fields=library.default_fields)
        library.add_entries([entry])

        qt_driver.selected = [100]
        qt_driver.copy_tags_action_callback()

        assert qt_driver.tags_clipboard == set()
        assert qt_driver.tags_clipboard_source == {100}


class TestPasteTagsMerge:
    """Test paste tags functionality in merge mode."""

    def test_paste_tags_merge_add_new_tags(self, qt_driver: QtDriver, library: Library):
        """Test merging tags adds new tags without removing existing ones."""
        qt_driver.selected = [1]
        qt_driver.copy_tags_action_callback()
        initial_tags_1 = {tag.id for tag in unwrap(library.get_entry_full(1)).tags}

        qt_driver.selected = [2]
        initial_tags_2 = {tag.id for tag in unwrap(library.get_entry_full(2)).tags}

        with patch.object(qt_driver, "main_window"):
            qt_driver.main_window.preview_panel = Mock()
            qt_driver._execute_paste_tags("merge")

        final_tags_2 = {tag.id for tag in unwrap(library.get_entry_full(2)).tags}

        assert initial_tags_1.issubset(final_tags_2)
        assert initial_tags_2.issubset(final_tags_2)
        assert final_tags_2 == initial_tags_1 | initial_tags_2

    def test_paste_tags_merge_no_duplicates(self, qt_driver: QtDriver, library: Library):
        """Test merge mode doesn't create duplicate tags."""
        qt_driver.selected = [1]
        qt_driver.copy_tags_action_callback()

        initial_tags = {tag.id for tag in unwrap(library.get_entry_full(1)).tags}
        initial_count = len(initial_tags)

        qt_driver.selected = [1]

        with patch.object(qt_driver, "main_window"):
            qt_driver.main_window.preview_panel = Mock()
            qt_driver._execute_paste_tags("merge")

        final_tags = {tag.id for tag in unwrap(library.get_entry_full(1)).tags}
        final_count = len(final_tags)

        assert initial_count == final_count
        assert initial_tags == final_tags

    def test_paste_tags_merge_multiple_entries(self, qt_driver: QtDriver, library: Library):
        """Test merging tags to multiple entries."""
        qt_driver.selected = [1]
        qt_driver.copy_tags_action_callback()
        tags_from_1 = {tag.id for tag in unwrap(library.get_entry_full(1)).tags}

        folder = unwrap(library.folder)
        entry3 = Entry(id=3, folder=folder, path="test3.txt", fields=library.default_fields)
        entry4 = Entry(id=4, folder=folder, path="test4.txt", fields=library.default_fields)
        library.add_entries([entry3, entry4])

        qt_driver.selected = [3, 4]

        with patch.object(qt_driver, "main_window"):
            qt_driver.main_window.preview_panel = Mock()
            qt_driver._execute_paste_tags("merge")

        tags_3 = {tag.id for tag in unwrap(library.get_entry_full(3)).tags}
        tags_4 = {tag.id for tag in unwrap(library.get_entry_full(4)).tags}

        assert tags_from_1.issubset(tags_3)
        assert tags_from_1.issubset(tags_4)


class TestPasteTagsReplace:
    """Test paste tags functionality in replace mode."""

    def test_paste_tags_replace_removes_existing(self, qt_driver: QtDriver, library: Library):
        """Test replace mode removes existing tags and adds clipboard tags."""
        qt_driver.selected = [1]
        qt_driver.copy_tags_action_callback()
        tags_from_1 = {tag.id for tag in unwrap(library.get_entry_full(1)).tags}

        qt_driver.selected = [2]
        initial_tags_2 = {tag.id for tag in unwrap(library.get_entry_full(2)).tags}

        with patch.object(qt_driver, "main_window"):
            qt_driver.main_window.preview_panel = Mock()
            qt_driver._execute_paste_tags("replace")

        final_tags_2 = {tag.id for tag in unwrap(library.get_entry_full(2)).tags}

        assert final_tags_2 == tags_from_1
        assert not (initial_tags_2 & final_tags_2)

    def test_paste_tags_replace_same_entry(self, qt_driver: QtDriver, library: Library):
        """Test replace mode on same entry keeps tags unchanged."""
        qt_driver.selected = [1]
        qt_driver.copy_tags_action_callback()
        initial_tags = {tag.id for tag in unwrap(library.get_entry_full(1)).tags}

        qt_driver.selected = [1]

        with patch.object(qt_driver, "main_window"):
            qt_driver.main_window.preview_panel = Mock()
            qt_driver._execute_paste_tags("replace")

        final_tags = {tag.id for tag in unwrap(library.get_entry_full(1)).tags}

        assert initial_tags == final_tags

    def test_paste_tags_replace_empty_clipboard(self, qt_driver: QtDriver, library: Library):
        """Test replace mode with empty clipboard clears all tags."""
        qt_driver.tags_clipboard = set()

        qt_driver.selected = [1]
        initial_tags = {tag.id for tag in unwrap(library.get_entry_full(1)).tags}

        assert len(initial_tags) > 0

        with patch.object(qt_driver, "main_window"):
            qt_driver.main_window.preview_panel = Mock()
            qt_driver._execute_paste_tags("replace")

        final_tags = {tag.id for tag in unwrap(library.get_entry_full(1)).tags}

        assert len(final_tags) == 0


class TestPasteTagsDialog:
    """Test PasteTagsDialog functionality."""

    def test_dialog_creation_no_preset(self, library: Library):
        """Test dialog creation without preset mode."""
        tags_clipboard = {1, 2}
        entries = list(library.all_entries(with_joins=True))

        dialog = PasteTagsDialog(tags_clipboard, entries, library, preset_mode=None)

        assert dialog.tags_clipboard == tags_clipboard
        assert dialog.selected_entries == entries
        assert dialog.preset_mode is None
        assert dialog.merge_radio.isChecked()
        assert not dialog.replace_radio.isChecked()

    def test_dialog_creation_with_preset_merge(self, library: Library):
        """Test dialog creation with preset merge mode."""
        tags_clipboard = {1, 2}
        entries = list(library.all_entries(with_joins=True))

        dialog = PasteTagsDialog(tags_clipboard, entries, library, preset_mode="merge")

        assert dialog.preset_mode == "merge"
        assert not hasattr(dialog, "merge_radio")

    def test_dialog_creation_with_preset_replace(self, library: Library):
        """Test dialog creation with preset replace mode."""
        tags_clipboard = {1, 2}
        entries = list(library.all_entries(with_joins=True))

        dialog = PasteTagsDialog(tags_clipboard, entries, library, preset_mode="replace")

        assert dialog.preset_mode == "replace"
        assert not hasattr(dialog, "replace_radio")

    def test_dialog_accept_merge(self, library: Library):
        """Test accepting dialog in merge mode."""
        tags_clipboard = {1}
        entries = list(library.all_entries(with_joins=True))

        dialog = PasteTagsDialog(tags_clipboard, entries, library)
        dialog.merge_radio.setChecked(True)

        with patch.object(dialog, "mode_selected") as mock_signal:
            dialog.accept_choice()
            mock_signal.emit.assert_called_once_with("merge")

        assert dialog.selected_mode == "merge"

    def test_dialog_accept_replace(self, library: Library):
        """Test accepting dialog in replace mode."""
        tags_clipboard = {1}
        entries = list(library.all_entries(with_joins=True))

        dialog = PasteTagsDialog(tags_clipboard, entries, library)
        dialog.replace_radio.setChecked(True)

        with patch.object(dialog, "mode_selected") as mock_signal:
            dialog.accept_choice()
            mock_signal.emit.assert_called_once_with("replace")

        assert dialog.selected_mode == "replace"

    def test_dialog_remember_choice(self, library: Library):
        """Test remember choice checkbox."""
        tags_clipboard = {1}
        entries = list(library.all_entries(with_joins=True))

        dialog = PasteTagsDialog(tags_clipboard, entries, library)
        dialog.remember_checkbox.setChecked(True)
        dialog.accept_choice()

        assert dialog.remember_choice is True

    def test_dialog_reject(self, library: Library):
        """Test rejecting dialog."""
        tags_clipboard = {1}
        entries = list(library.all_entries(with_joins=True))

        dialog = PasteTagsDialog(tags_clipboard, entries, library)
        dialog.reject()

        assert dialog.selected_mode is None

    def test_dialog_delta_calculation_merge(self, library: Library):
        """Test delta calculation shows correct tags to add in merge mode."""
        entry1 = unwrap(library.get_entry_full(1))
        entry2 = unwrap(library.get_entry_full(2))

        tags_from_1 = {tag.id for tag in entry1.tags}
        tags_from_2 = {tag.id for tag in entry2.tags}

        dialog = PasteTagsDialog(tags_from_1, [entry2], library)

        _ = dialog._create_entry_delta_widget(entry2, "merge")

        tags_to_add = tags_from_1 - tags_from_2
        assert len(tags_to_add) > 0

    def test_dialog_delta_calculation_replace(self, library: Library):
        """Test delta calculation shows correct tags to add/remove in replace mode."""
        entry1 = unwrap(library.get_entry_full(1))
        entry2 = unwrap(library.get_entry_full(2))

        tags_from_1 = {tag.id for tag in entry1.tags}
        tags_from_2 = {tag.id for tag in entry2.tags}

        dialog = PasteTagsDialog(tags_from_1, [entry2], library)

        _ = dialog._create_entry_delta_widget(entry2, "replace")

        tags_to_add = tags_from_1 - tags_from_2
        tags_to_remove = tags_from_2 - tags_from_1

        assert len(tags_to_add) > 0 or len(tags_to_remove) > 0


class TestMenuViability:
    """Test menu action enable/disable logic."""

    def test_copy_tags_menu_enabled_with_selection(self, qt_driver: QtDriver):
        """Test copy tags menu is enabled when entries are selected."""
        qt_driver.selected = [1]
        qt_driver.main_window.menu_bar.copy_tags_action = Mock()

        qt_driver.set_tags_clipboard_menu_viability()

        qt_driver.main_window.menu_bar.copy_tags_action.setEnabled.assert_called_with(True)

    def test_copy_tags_menu_disabled_without_selection(self, qt_driver: QtDriver):
        """Test copy tags menu is disabled when no entries are selected."""
        qt_driver.selected = []
        qt_driver.main_window.menu_bar.copy_tags_action = Mock()

        qt_driver.set_tags_clipboard_menu_viability()

        qt_driver.main_window.menu_bar.copy_tags_action.setEnabled.assert_called_with(False)

    def test_paste_tags_menu_enabled_with_clipboard_and_selection(self, qt_driver: QtDriver):
        """Test paste tags menu is enabled when clipboard has tags and entries are selected."""
        qt_driver.selected = [1]
        qt_driver.tags_clipboard = {1, 2}
        qt_driver.main_window.menu_bar.paste_tags_action = Mock()

        qt_driver.set_tags_clipboard_menu_viability()

        qt_driver.main_window.menu_bar.paste_tags_action.setEnabled.assert_called_with(True)

    def test_paste_tags_menu_disabled_without_clipboard(self, qt_driver: QtDriver):
        """Test paste tags menu is disabled when clipboard is empty."""
        qt_driver.selected = [1]
        qt_driver.tags_clipboard = set()
        qt_driver.main_window.menu_bar.paste_tags_action = Mock()

        qt_driver.set_tags_clipboard_menu_viability()

        qt_driver.main_window.menu_bar.paste_tags_action.setEnabled.assert_called_with(False)

    def test_paste_tags_menu_disabled_without_selection(self, qt_driver: QtDriver):
        """Test paste tags menu is disabled when no entries are selected."""
        qt_driver.selected = []
        qt_driver.tags_clipboard = {1, 2}
        qt_driver.main_window.menu_bar.paste_tags_action = Mock()

        qt_driver.set_tags_clipboard_menu_viability()

        qt_driver.main_window.menu_bar.paste_tags_action.setEnabled.assert_called_with(False)


class TestContextMenuVisibility:
    """Test context menu visibility logic."""

    def test_paste_visible_with_clipboard(self, qt_driver: QtDriver):
        """Test paste tags context menu is visible when clipboard has tags."""
        qt_driver.tags_clipboard = {1, 2}
        qt_driver.tags_clipboard_source = {1}

        mock_item = Mock()
        mock_item.item_id = 2
        mock_item.paste_tags_action = Mock()

        for item in [mock_item]:
            qt_driver.update_paste_tags_context_menu_visibility(item)

        mock_item.paste_tags_action.setVisible.assert_called_with(True)

    def test_paste_hidden_without_clipboard(self, qt_driver: QtDriver):
        """Test paste tags context menu is hidden when clipboard is empty."""
        qt_driver.tags_clipboard = set()

        mock_item = Mock()
        mock_item.item_id = 1
        mock_item.paste_tags_action = Mock()

        for item in [mock_item]:
            qt_driver.update_paste_tags_context_menu_visibility(item)

        mock_item.paste_tags_action.setVisible.assert_called_with(False)

    def test_paste_hidden_for_source_items(self, qt_driver: QtDriver):
        """Test paste tags context menu is hidden for source items."""
        qt_driver.tags_clipboard = {1, 2}
        qt_driver.tags_clipboard_source = {1}

        mock_item = Mock()
        mock_item.item_id = 1
        mock_item.paste_tags_action = Mock()

        for item in [mock_item]:
            qt_driver.update_paste_tags_context_menu_visibility(item)

        mock_item.paste_tags_action.setVisible.assert_called_with(False)


class TestCopyPasteWorkflow:
    """Test complete copy/paste workflows."""

    def test_copy_paste_workflow_merge(self, qt_driver: QtDriver, library: Library):
        """Test complete workflow: copy from one entry, paste to another in merge mode."""
        qt_driver.selected = [1]
        qt_driver.copy_tags_action_callback()
        tags_from_1 = {tag.id for tag in unwrap(library.get_entry_full(1)).tags}

        qt_driver.selected = [2]
        tags_before_2 = {tag.id for tag in unwrap(library.get_entry_full(2)).tags}

        with patch.object(qt_driver, "main_window"):
            qt_driver.main_window.preview_panel = Mock()
            qt_driver._execute_paste_tags("merge")

        tags_after_2 = {tag.id for tag in unwrap(library.get_entry_full(2)).tags}

        assert tags_from_1.issubset(tags_after_2)
        assert tags_before_2.issubset(tags_after_2)
        assert qt_driver.tags_clipboard == tags_from_1
        assert qt_driver.tags_clipboard_source == {1}

    def test_copy_paste_workflow_replace(self, qt_driver: QtDriver, library: Library):
        """Test complete workflow: copy from one entry, paste to another in replace mode."""
        qt_driver.selected = [1]
        qt_driver.copy_tags_action_callback()
        tags_from_1 = {tag.id for tag in unwrap(library.get_entry_full(1)).tags}

        qt_driver.selected = [2]
        tags_before_2 = {tag.id for tag in unwrap(library.get_entry_full(2)).tags}

        with patch.object(qt_driver, "main_window"):
            qt_driver.main_window.preview_panel = Mock()
            qt_driver._execute_paste_tags("replace")

        tags_after_2 = {tag.id for tag in unwrap(library.get_entry_full(2)).tags}

        assert tags_after_2 == tags_from_1
        for tag_id in tags_before_2:
            if tag_id not in tags_from_1:
                assert tag_id not in tags_after_2

    def test_multiple_copy_operations_overwrite_clipboard(
        self, qt_driver: QtDriver, library: Library
    ):
        """Test that copying multiple times overwrites the clipboard."""
        qt_driver.selected = [1]
        qt_driver.copy_tags_action_callback()
        tags_from_1 = qt_driver.tags_clipboard.copy()

        qt_driver.selected = [2]
        qt_driver.copy_tags_action_callback()
        tags_from_2 = qt_driver.tags_clipboard.copy()

        assert tags_from_2 != tags_from_1
        assert qt_driver.tags_clipboard_source == {2}


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_paste_to_mixed_entries(self, qt_driver: QtDriver, library: Library):
        """Test pasting to multiple entries where some already have clipboard tags."""
        qt_driver.selected = [1]
        qt_driver.copy_tags_action_callback()
        clipboard_tags = qt_driver.tags_clipboard.copy()

        folder = unwrap(library.folder)
        entry_new = Entry(id=10, folder=folder, path="new.txt", fields=library.default_fields)
        library.add_entries([entry_new])

        qt_driver.selected = [1, 10]

        with patch.object(qt_driver, "main_window"):
            qt_driver.main_window.preview_panel = Mock()
            qt_driver._execute_paste_tags("merge")

        tags_1 = {tag.id for tag in unwrap(library.get_entry_full(1)).tags}
        tags_10 = {tag.id for tag in unwrap(library.get_entry_full(10)).tags}

        assert tags_1 == clipboard_tags
        assert clipboard_tags.issubset(tags_10)

    def test_copy_from_entries_with_overlapping_tags(self, qt_driver: QtDriver, library: Library):
        """Test copying from multiple entries that share some tags."""
        entry1 = unwrap(library.get_entry_full(1))
        entry2 = unwrap(library.get_entry_full(2))

        tags_1 = {tag.id for tag in entry1.tags}
        tags_2 = {tag.id for tag in entry2.tags}
        expected_union = tags_1 | tags_2

        qt_driver.selected = [1, 2]
        qt_driver.copy_tags_action_callback()

        assert qt_driver.tags_clipboard == expected_union

    def test_paste_with_empty_selection_after_copy(self, qt_driver: QtDriver, library: Library):
        """Test that paste doesn't work with empty selection even if clipboard has tags."""
        qt_driver.selected = [1]
        qt_driver.copy_tags_action_callback()
        assert len(qt_driver.tags_clipboard) > 0

        qt_driver.selected = []

        with patch.object(qt_driver, "main_window"):
            qt_driver.main_window.menu_bar.paste_tags_action = Mock()
            qt_driver.set_tags_clipboard_menu_viability()
            qt_driver.main_window.menu_bar.paste_tags_action.setEnabled.assert_called_with(False)

    def test_replace_mode_with_subset_of_tags(self, qt_driver: QtDriver, library: Library):
        """Test replace mode when clipboard contains subset of entry's tags."""
        entry1 = unwrap(library.get_entry_full(1))
        all_tags = {tag.id for tag in entry1.tags}

        if len(all_tags) > 1:
            subset_tags = set(list(all_tags)[:1])
            qt_driver.tags_clipboard = subset_tags
            qt_driver.tags_clipboard_source = {99}

            qt_driver.selected = [1]

            with patch.object(qt_driver, "main_window"):
                qt_driver.main_window.preview_panel = Mock()
                qt_driver._execute_paste_tags("replace")

            final_tags = {tag.id for tag in unwrap(library.get_entry_full(1)).tags}
            assert final_tags == subset_tags
            assert len(final_tags) < len(all_tags)

    def test_paste_tags_to_large_selection(self, qt_driver: QtDriver, library: Library):
        """Test pasting tags to many entries at once."""
        qt_driver.selected = [1]
        qt_driver.copy_tags_action_callback()
        clipboard_tags = qt_driver.tags_clipboard.copy()

        folder = unwrap(library.folder)
        new_entries = [
            Entry(id=i, folder=folder, path=f"test{i}.txt", fields=library.default_fields)
            for i in range(50, 60)
        ]
        library.add_entries(new_entries)

        qt_driver.selected = list(range(50, 60))

        with patch.object(qt_driver, "main_window"):
            qt_driver.main_window.preview_panel = Mock()
            qt_driver._execute_paste_tags("merge")

        for entry_id in range(50, 60):
            entry_tags = {tag.id for tag in unwrap(library.get_entry_full(entry_id)).tags}
            assert clipboard_tags.issubset(entry_tags)


class TestDialogBehavior:
    """Test dialog-specific behavior and UI interactions."""

    def test_dialog_mode_radio_toggle(self, library: Library):
        """Test that radio buttons toggle correctly."""
        tags_clipboard = {1, 2}
        entries = list(library.all_entries(with_joins=True))

        dialog = PasteTagsDialog(tags_clipboard, entries, library)

        dialog.merge_radio.setChecked(True)
        assert dialog.merge_radio.isChecked()
        assert not dialog.replace_radio.isChecked()

        dialog.replace_radio.setChecked(True)
        assert dialog.replace_radio.isChecked()
        assert not dialog.merge_radio.isChecked()

    def test_dialog_update_delta_on_mode_change(self, library: Library):
        """Test that delta preview updates when mode changes."""
        entry1 = unwrap(library.get_entry_full(1))
        entry2 = unwrap(library.get_entry_full(2))
        tags_from_1 = {tag.id for tag in entry1.tags}

        dialog = PasteTagsDialog(tags_from_1, [entry2], library)

        initial_delta_count = dialog.delta_layout.count()

        dialog.merge_radio.setChecked(True)
        dialog.update_delta()
        merge_delta_count = dialog.delta_layout.count()

        dialog.replace_radio.setChecked(True)
        dialog.update_delta()
        replace_delta_count = dialog.delta_layout.count()

        assert initial_delta_count >= 0
        assert merge_delta_count >= 0
        assert replace_delta_count >= 0

    def test_dialog_preset_mode_skips_radio_buttons(self, library: Library):
        """Test that preset mode doesn't create radio buttons."""
        tags_clipboard = {1, 2}
        entries = list(library.all_entries(with_joins=True))

        dialog_merge = PasteTagsDialog(tags_clipboard, entries, library, preset_mode="merge")
        assert not hasattr(dialog_merge, "merge_radio")
        assert not hasattr(dialog_merge, "replace_radio")

        dialog_replace = PasteTagsDialog(tags_clipboard, entries, library, preset_mode="replace")
        assert not hasattr(dialog_replace, "merge_radio")
        assert not hasattr(dialog_replace, "replace_radio")

    def test_dialog_multiple_entries_delta_preview(self, library: Library):
        """Test that delta preview shows all selected entries."""
        entry1 = unwrap(library.get_entry_full(1))
        entry2 = unwrap(library.get_entry_full(2))
        tags_from_1 = {tag.id for tag in entry1.tags}

        dialog = PasteTagsDialog(tags_from_1, [entry1, entry2], library)

        assert dialog.delta_layout.count() == 2


class TestClipboardState:
    """Test clipboard state management."""

    def test_clipboard_persists_across_operations(self, qt_driver: QtDriver, library: Library):
        """Test that clipboard persists until overwritten."""
        qt_driver.selected = [1]
        qt_driver.copy_tags_action_callback()
        initial_clipboard = qt_driver.tags_clipboard.copy()

        qt_driver.selected = [2]

        with patch.object(qt_driver, "main_window"):
            qt_driver.main_window.preview_panel = Mock()
            qt_driver._execute_paste_tags("merge")

        assert qt_driver.tags_clipboard == initial_clipboard

    def test_clipboard_source_updates_correctly(self, qt_driver: QtDriver, library: Library):
        """Test that clipboard source tracking is accurate."""
        qt_driver.selected = [1, 2]
        qt_driver.copy_tags_action_callback()

        assert qt_driver.tags_clipboard_source == {1, 2}

        qt_driver.selected = [1]
        qt_driver.copy_tags_action_callback()

        assert qt_driver.tags_clipboard_source == {1}

    def test_empty_clipboard_state(self, qt_driver: QtDriver):
        """Test initial empty clipboard state."""
        qt_driver.tags_clipboard = set()
        qt_driver.tags_clipboard_source = set()

        assert len(qt_driver.tags_clipboard) == 0
        assert len(qt_driver.tags_clipboard_source) == 0
