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
