# Copyright (C) 2025
# Licensed under the GPL-3.0 License.
# Created for TagStudio: https://github.com/CyanVoxel/TagStudio


from datetime import datetime as dt
from pathlib import Path
from unittest.mock import MagicMock

from tagstudio.core.library.alchemy.library import Library
from tagstudio.core.library.alchemy.models import Entry
from tagstudio.qt.controllers.manage_folders_modal_controller import (
    _PRIMARY_ROLE,
    ManageFoldersModal,
)


def _make_controller(library: Library) -> ManageFoldersModal:
    """Build a controller without invoking the Qt view __init__.

    The view builds real QWidgets which require QApplication; the unit tests
    exercise only the controller's business logic, with Qt-dependent helpers
    replaced by mocks.
    """
    modal = ManageFoldersModal.__new__(ManageFoldersModal)
    modal.lib = library
    modal.driver = MagicMock()
    modal.folder_list = MagicMock()
    modal.add_button = MagicMock()
    modal.remove_button = MagicMock()
    modal.done_button = MagicMock()
    modal._pending_scan = False
    modal._prompt_for_folder = MagicMock(return_value=None)  # pyright: ignore
    modal._confirm_remove = MagicMock(return_value=False)  # pyright: ignore
    modal._show_error = MagicMock()  # pyright: ignore
    return modal


def _trigger_hide(modal: ManageFoldersModal) -> None:
    """Simulate the modal's hideEvent firing (what happens when Done is clicked)."""
    if modal._pending_scan:
        modal._pending_scan = False
        modal.driver.call_if_library_open(modal.driver.add_new_files_callback)


def test_add_folder_callback_cancelled(library: Library):
    modal = _make_controller(library)
    modal._prompt_for_folder = MagicMock(return_value=None)

    before = len(library.folders)
    modal._add_folder_callback()

    assert len(library.folders) == before
    modal.driver.add_new_files_callback.assert_not_called()


def test_add_folder_callback_success_defers_scan(library: Library, tmp_path: Path):
    """Adding a folder must register it immediately but NOT trigger a scan
    synchronously — the scan is deferred until the modal hides, so the user
    can add multiple folders in one session with a single scan at the end,
    and the ProgressWidget never appears under a blocking modal.
    """
    target = tmp_path / "new_root"
    target.mkdir()
    modal = _make_controller(library)
    modal._prompt_for_folder = MagicMock(return_value=target)

    modal._add_folder_callback()

    assert any(f.path == target for f in library.folders)
    assert modal._pending_scan is True
    modal.driver.call_if_library_open.assert_not_called()


def test_add_then_hide_triggers_exactly_one_scan(library: Library, tmp_path: Path):
    """Multiple adds in one modal session collapse into a single scan."""
    first = tmp_path / "first"
    first.mkdir()
    second = tmp_path / "second"
    second.mkdir()

    modal = _make_controller(library)
    modal._prompt_for_folder = MagicMock(side_effect=[first, second])

    modal._add_folder_callback()
    modal._add_folder_callback()
    assert modal._pending_scan is True
    modal.driver.call_if_library_open.assert_not_called()

    _trigger_hide(modal)

    modal.driver.call_if_library_open.assert_called_once_with(
        modal.driver.add_new_files_callback
    )
    assert modal._pending_scan is False


def test_hide_without_adds_does_not_scan(library: Library):
    modal = _make_controller(library)
    _trigger_hide(modal)
    modal.driver.call_if_library_open.assert_not_called()


def test_add_folder_callback_invalid_shows_error(library: Library, tmp_path: Path):
    missing = tmp_path / "does_not_exist"
    modal = _make_controller(library)
    modal._prompt_for_folder = MagicMock(return_value=missing)

    modal._add_folder_callback()

    modal._show_error.assert_called_once()
    modal.driver.call_if_library_open.assert_not_called()


def test_remove_folder_callback_declined(library: Library, tmp_path: Path):
    target = tmp_path / "declined"
    target.mkdir()
    folder = library.add_folder(target)
    folder_id = folder.id
    modal = _make_controller(library)

    item = MagicMock()
    item.data.return_value = folder_id
    modal.folder_list.currentItem.return_value = item
    modal._confirm_remove = MagicMock(return_value=False)

    modal._remove_folder_callback()

    # Folder must still be present.
    assert any(f.id == folder_id for f in library.folders)


def test_remove_folder_callback_confirmed(library: Library, tmp_path: Path):
    target = tmp_path / "confirmed"
    target.mkdir()
    folder = library.add_folder(target)
    folder_id = folder.id
    # Attach an entry so we exercise the cascade delete path.
    library.add_entries([
        Entry(path=Path("file.txt"), folder=folder, fields=[], date_added=dt.now()),
    ])
    entries_before = library.entries_count

    modal = _make_controller(library)
    item = MagicMock()
    item.data.return_value = folder_id
    modal.folder_list.currentItem.return_value = item
    modal._confirm_remove = MagicMock(return_value=True)

    modal._remove_folder_callback()

    assert not any(f.id == folder_id for f in library.folders)
    assert library.entries_count == entries_before - 1
    modal.driver.update_browsing_state.assert_called_once()
    # Confirmation prompt was shown the count correctly:
    _, kwargs_path_count = modal._confirm_remove.call_args
    positional = modal._confirm_remove.call_args[0]
    assert positional[0] == target  # path
    assert positional[1] == 1       # entry count


def test_remove_folder_callback_primary_noop(library: Library):
    modal = _make_controller(library)

    item = MagicMock()
    item.data.return_value = _PRIMARY_ROLE
    modal.folder_list.currentItem.return_value = item

    modal._remove_folder_callback()

    modal._confirm_remove.assert_not_called()
    modal.driver.update_browsing_state.assert_not_called()


def test_remove_folder_callback_no_selection_noop(library: Library):
    modal = _make_controller(library)
    modal.folder_list.currentItem.return_value = None

    modal._remove_folder_callback()

    modal._confirm_remove.assert_not_called()


def test_folder_entry_count_helper(library: Library, tmp_path: Path):
    """The Library helper this controller relies on for the confirmation count."""
    target = tmp_path / "counted"
    target.mkdir()
    folder = library.add_folder(target)

    assert library.folder_entry_count(folder) == 0

    library.add_entries([
        Entry(path=Path("a.txt"), folder=folder, fields=[], date_added=dt.now()),
        Entry(path=Path("b.txt"), folder=folder, fields=[], date_added=dt.now()),
    ])
    assert library.folder_entry_count(folder) == 2
