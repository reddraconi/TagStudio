# Copyright (C) 2025
# Licensed under the GPL-3.0 License.
# Created for TagStudio: https://github.com/CyanVoxel/TagStudio

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from tagstudio.core.library.alchemy.library import Library
from tagstudio.core.library.refresh import RefreshTracker
from tagstudio.core.utils.types import unwrap


@pytest.mark.parametrize("library", [TemporaryDirectory()], indirect=True)
def test_refresh_folders_scans_primary(library: Library):
    """refresh_folders must scan the primary library folder even when no
    additional Folder rows have been persisted (fresh libraries populate
    Folder rows lazily)."""
    primary_dir = unwrap(library.library_dir)
    library.included_files.clear()
    (primary_dir / "hello.txt").touch()

    tracker = RefreshTracker(library=library)
    list(tracker.refresh_folders(force_internal_tools=True))

    paths = {p for _, p in tracker.files_not_in_library}
    assert Path("hello.txt") in paths


@pytest.mark.parametrize("library", [TemporaryDirectory()], indirect=True)
def test_refresh_folders_scans_additional(library: Library, tmp_path: Path):
    """A second registered folder is scanned, and its files are tagged with
    the correct Folder in files_not_in_library."""
    primary_dir = unwrap(library.library_dir)
    library.included_files.clear()
    (primary_dir / "primary_file.txt").touch()

    extra_root = tmp_path / "extra"
    extra_root.mkdir()
    (extra_root / "extra_file.txt").touch()
    extra_folder = library.add_folder(extra_root)

    tracker = RefreshTracker(library=library)
    list(tracker.refresh_folders(force_internal_tools=True))

    primary_paths = {
        p for f, p in tracker.files_not_in_library if f.path == primary_dir
    }
    extra_paths = {
        p for f, p in tracker.files_not_in_library if f.id == extra_folder.id
    }
    assert Path("primary_file.txt") in primary_paths
    assert Path("extra_file.txt") in extra_paths
    assert Path("extra_file.txt") not in primary_paths
    assert Path("primary_file.txt") not in extra_paths


@pytest.mark.parametrize("library", [TemporaryDirectory()], indirect=True)
def test_refresh_same_filename_in_two_folders(library: Library, tmp_path: Path):
    """Same relative path under two folders must be tracked as two separate
    (folder, path) entries — not deduped by path."""
    primary_dir = unwrap(library.library_dir)
    library.included_files.clear()
    (primary_dir / "collide.txt").touch()

    extra_root = tmp_path / "extra"
    extra_root.mkdir()
    (extra_root / "collide.txt").touch()
    extra_folder = library.add_folder(extra_root)

    tracker = RefreshTracker(library=library)
    list(tracker.refresh_folders(force_internal_tools=True))

    collisions = [
        (f, p) for f, p in tracker.files_not_in_library if p == Path("collide.txt")
    ]
    assert len(collisions) == 2
    folder_ids = {f.id for f, _ in collisions}
    assert extra_folder.id in folder_ids


@pytest.mark.parametrize("library", [TemporaryDirectory()], indirect=True)
def test_save_new_files_assigns_correct_folder(library: Library, tmp_path: Path):
    """After refresh_folders + save_new_files, entries persist with the right
    folder_id so their absolute_path resolves to the right filesystem location."""
    primary_dir = unwrap(library.library_dir)
    library.included_files.clear()
    (primary_dir / "p.txt").touch()

    extra_root = tmp_path / "extra"
    extra_root.mkdir()
    (extra_root / "e.txt").touch()
    library.add_folder(extra_root)

    tracker = RefreshTracker(library=library)
    list(tracker.refresh_folders(force_internal_tools=True))
    list(tracker.save_new_files())

    abs_paths = {e.absolute_path for e in library.all_entries()}
    assert primary_dir / "p.txt" in abs_paths
    assert extra_root / "e.txt" in abs_paths
