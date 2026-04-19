# Copyright (C) 2025
# Licensed under the GPL-3.0 License.
# Created for TagStudio: https://github.com/CyanVoxel/TagStudio


from datetime import datetime as dt
from pathlib import Path

import pytest

from tagstudio.core.library.alchemy.library import Library
from tagstudio.core.library.alchemy.models import Entry


def test_folders_initial(library: Library):
    folders = library.folders
    assert len(folders) == 1
    assert folders[0].path == library.library_dir


def test_primary_folder_persisted_on_open(library: Library):
    """open_library must persist the primary Folder immediately.

    Regression guard for a quirk where session.expunge(folder) was called
    BEFORE session.commit(), cancelling the pending INSERT. The primary
    would then only land on disk later via cascade from the first Entry,
    which silently broke refresh_folders and anything else that depends
    on lib.folders containing the primary.
    """
    assert library.folder is not None
    persisted = library.folders
    assert any(f.path == library.folder.path for f in persisted)


def test_add_folder(library: Library, tmp_path: Path):
    new_root = tmp_path / "extra"
    new_root.mkdir()

    folder = library.add_folder(new_root)

    assert folder.path == new_root
    assert folder.uuid
    assert len(library.folders) == 2


def test_add_folder_missing_path(library: Library, tmp_path: Path):
    missing = tmp_path / "does-not-exist"
    with pytest.raises(ValueError, match="does not exist"):
        library.add_folder(missing)


def test_add_folder_not_a_directory(library: Library, tmp_path: Path):
    file_path = tmp_path / "a_file.txt"
    file_path.write_text("hi")
    with pytest.raises(ValueError, match="not a directory"):
        library.add_folder(file_path)


def test_add_folder_duplicate(library: Library, tmp_path: Path):
    new_root = tmp_path / "dup"
    new_root.mkdir()
    library.add_folder(new_root)
    with pytest.raises(ValueError, match="already registered"):
        library.add_folder(new_root)


def test_remove_primary_folder_rejected(library: Library):
    primary = library.folders[0]
    with pytest.raises(ValueError, match="primary"):
        library.remove_folder(primary)


def test_remove_empty_folder(library: Library, tmp_path: Path):
    new_root = tmp_path / "empty"
    new_root.mkdir()
    folder = library.add_folder(new_root)

    library.remove_folder(folder)

    assert all(f.id != folder.id for f in library.folders)


def test_remove_folder_with_entries_rejected(library: Library, tmp_path: Path):
    new_root = tmp_path / "withentries"
    new_root.mkdir()
    folder = library.add_folder(new_root)
    entry = Entry(
        path=Path("a.txt"),
        folder=folder,
        fields=[],
        date_added=dt.now(),
    )
    library.add_entries([entry])

    with pytest.raises(ValueError, match="delete_entries=True"):
        library.remove_folder(folder, delete_entries=False)


def test_remove_folder_cascade_deletes_entries(library: Library, tmp_path: Path):
    new_root = tmp_path / "cascade"
    new_root.mkdir()
    folder = library.add_folder(new_root)
    # Snapshot the id before add_entries expires the instance.
    folder_id = folder.id
    entry = Entry(
        path=Path("a.txt"),
        folder=folder,
        fields=[],
        date_added=dt.now(),
    )
    library.add_entries([entry])
    before = library.entries_count

    library.remove_folder(folder, delete_entries=True)

    assert library.entries_count == before - 1
    assert all(f.id != folder_id for f in library.folders)


def test_folder_for_path_matches_registered_folder(library: Library, tmp_path: Path):
    extra_root = tmp_path / "other"
    extra_root.mkdir()
    extra = library.add_folder(extra_root)

    primary = library.folder
    assert primary is not None

    primary_match = library.folder_for_path(primary.path / "x.txt")
    assert primary_match is not None
    assert primary_match.id == primary.id

    extra_match = library.folder_for_path(extra_root / "y.txt")
    assert extra_match is not None
    assert extra_match.id == extra.id


def test_folder_for_path_returns_none_when_unregistered(library: Library, tmp_path: Path):
    unrelated = tmp_path / "not_a_library_folder"
    unrelated.mkdir()
    assert library.folder_for_path(unrelated / "foo.txt") is None


def test_get_entry_full_by_path_scoped_to_folder(library: Library, tmp_path: Path):
    """Two folders with same relative path; folder=... disambiguates the lookup."""
    extra_root = tmp_path / "other"
    extra_root.mkdir()
    extra = library.add_folder(extra_root)
    primary = library.folder
    assert primary is not None

    library.add_entries([
        Entry(path=Path("foo.txt"), folder=extra, fields=[], date_added=dt.now()),
    ])

    # Unscoped lookup returns some match (arbitrary), but both scoped
    # lookups must return entries whose folder matches the requested scope.
    primary_entry = library.get_entry_full_by_path(Path("foo.txt"), folder=primary)
    extra_entry = library.get_entry_full_by_path(Path("foo.txt"), folder=extra)
    assert primary_entry is not None
    assert extra_entry is not None
    assert primary_entry.folder_id != extra_entry.folder_id
    assert extra_entry.folder_id == extra.id


def test_same_relative_path_across_folders(library: Library, tmp_path: Path):
    """Two folders can each hold an entry at the same relative path."""
    other_root = tmp_path / "other"
    other_root.mkdir()
    other_folder = library.add_folder(other_root)
    primary_root = library.library_dir

    # The primary folder already has an entry at foo.txt from the fixture.
    # Adding foo.txt under the new folder must not collide on the old
    # single-column unique constraint (v104 relaxed it to composite).
    collision = Entry(
        path=Path("foo.txt"),
        folder=other_folder,
        fields=[],
        date_added=dt.now(),
    )
    library.add_entries([collision])

    all_entries = list(library.all_entries())
    foo_entries = [e for e in all_entries if e.path == Path("foo.txt")]
    assert len(foo_entries) == 2
    abs_paths = {e.absolute_path for e in foo_entries}
    assert abs_paths == {primary_root / "foo.txt", other_root / "foo.txt"}
