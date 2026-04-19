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


def test_add_folder_trailing_slash_same_as_no_slash(library: Library, tmp_path: Path):
    """Path('/foo/') and Path('/foo') are equal after Python's own
    normalization, so the second add must be rejected as duplicate."""
    target = tmp_path / "with_slash"
    target.mkdir()
    library.add_folder(target)
    with pytest.raises(ValueError, match="already registered"):
        library.add_folder(Path(str(target) + "/"))


def test_add_folder_symlink_resolves_to_existing(library: Library, tmp_path: Path):
    """Adding a symlink that points at an already-registered folder must
    be rejected as duplicate — resolved paths are what's compared."""
    target = tmp_path / "real_target"
    target.mkdir()
    library.add_folder(target)

    link = tmp_path / "link_to_target"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="already registered"):
        library.add_folder(link)


def test_add_folder_ancestor_of_existing_rejected(library: Library, tmp_path: Path):
    child = tmp_path / "parent" / "child"
    child.mkdir(parents=True)
    library.add_folder(child)
    with pytest.raises(ValueError, match="contains an already-registered folder"):
        library.add_folder(tmp_path / "parent")


def test_add_folder_descendant_of_existing_rejected(library: Library, tmp_path: Path):
    parent = tmp_path / "parent"
    parent.mkdir()
    library.add_folder(parent)
    child = parent / "child"
    child.mkdir()
    with pytest.raises(ValueError, match="inside an already-registered folder"):
        library.add_folder(child)


def test_remove_folder_cascade_leaves_no_orphans(library: Library, tmp_path: Path):
    """remove_folder(delete_entries=True) must not leave orphan rows in
    text_fields / datetime_fields / boolean_fields / tag_entries.

    Regression guard for the class of bug where SQLAlchemy ORM-level
    cascades were bypassed by bulk Query.delete(). v104 adds ON DELETE
    CASCADE at the DB level so the child rows are cleaned up regardless.
    """
    from sqlalchemy import text as sql_text
    from sqlalchemy.orm import Session

    from tagstudio.core.library.alchemy.fields import TextField

    extra_root = tmp_path / "cascade_test"
    extra_root.mkdir()
    folder = library.add_folder(extra_root)

    entry = Entry(path=Path("a.txt"), folder=folder, fields=[], date_added=dt.now())
    library.add_entries([entry])

    # Attach a text field directly so the orphan-prone relationship is
    # actually populated.
    with Session(library.engine) as session:
        persisted = next(
            iter(session.scalars(
                sql_text("SELECT * FROM entries WHERE folder_id = :fid").bindparams(
                    fid=folder.id
                )
            ))
        )
        tf = TextField(type_key="TITLE", position=0, value="hello")
        tf.entry_id = persisted
        session.add(tf)
        session.commit()

    library.remove_folder(folder, delete_entries=True)

    # No child rows may reference a deleted entry.
    with Session(library.engine) as session:
        for child_table in (
            "text_fields",
            "datetime_fields",
            "boolean_fields",
            "tag_entries",
        ):
            orphan_count = session.scalar(
                sql_text(
                    f"SELECT COUNT(*) FROM {child_table} "
                    "WHERE entry_id NOT IN (SELECT id FROM entries)"
                )
            )
            assert orphan_count == 0, (
                f"{child_table} retained {orphan_count} rows pointing at deleted entries"
            )


def test_entry_rejects_absolute_path(library: Library, tmp_path: Path):
    """An absolute path on an Entry is nonsensical — Entry.path is always
    relative to the parent Folder's root. Accepting an absolute path would
    make Entry.absolute_path silently discard the Folder and read files
    outside the library. Reject at construction time."""
    folder = library.folder
    assert folder is not None
    with pytest.raises(ValueError, match="relative to its parent Folder"):
        Entry(path=Path("/etc/passwd"), folder=folder, fields=[])


def test_entry_rejects_parent_traversal(library: Library, tmp_path: Path):
    """A relative path with '..' segments lets Entry.absolute_path escape
    the parent Folder's root (Python's Path division does not normalize),
    which would let a crafted library DB read arbitrary files on the host
    filesystem."""
    folder = library.folder
    assert folder is not None
    with pytest.raises(ValueError, match="must not contain '..'"):
        Entry(path=Path("../../etc/passwd"), folder=folder, fields=[])
    with pytest.raises(ValueError, match="must not contain '..'"):
        Entry(path=Path("subdir/../../../etc/passwd"), folder=folder, fields=[])


def test_add_folder_sibling_accepted(library: Library, tmp_path: Path):
    first = tmp_path / "a"
    first.mkdir()
    second = tmp_path / "b"
    second.mkdir()
    library.add_folder(first)
    # Unrelated sibling directory should add cleanly with no overlap.
    added = library.add_folder(second)
    assert added.path == second.resolve()


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
