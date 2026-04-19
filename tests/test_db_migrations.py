# Copyright (C) 2025 Travis Abendshien (CyanVoxel).
# Licensed under the GPL-3.0 License.
# Created for TagStudio: https://github.com/CyanVoxel/TagStudio


import shutil
import sqlite3
from datetime import datetime as dt
from pathlib import Path

import pytest

from tagstudio.core.constants import TS_FOLDER_NAME
from tagstudio.core.library.alchemy.constants import (
    SQL_FILENAME,
)
from tagstudio.core.library.alchemy.library import Library
from tagstudio.core.library.alchemy.models import Entry

CWD = Path(__file__)
FIXTURES = "fixtures"
EMPTY_LIBRARIES = "empty_libraries"


@pytest.mark.parametrize(
    "path",
    [
        str(Path(CWD.parent / FIXTURES / EMPTY_LIBRARIES / "DB_VERSION_6")),
        str(Path(CWD.parent / FIXTURES / EMPTY_LIBRARIES / "DB_VERSION_7")),
        str(Path(CWD.parent / FIXTURES / EMPTY_LIBRARIES / "DB_VERSION_8")),
        str(Path(CWD.parent / FIXTURES / EMPTY_LIBRARIES / "DB_VERSION_9")),
        str(Path(CWD.parent / FIXTURES / EMPTY_LIBRARIES / "DB_VERSION_100")),
    ],
)
def test_library_migrations(path: str):
    library = Library()

    # Copy libraries to temp dir so modifications don't show up in version control
    original_path = Path(path)
    temp_path = Path(CWD.parent / FIXTURES / EMPTY_LIBRARIES / "DB_VERSION_TEMP")
    temp_path.mkdir(exist_ok=True)
    temp_path_ts = temp_path / TS_FOLDER_NAME
    temp_path_ts.mkdir(exist_ok=True)
    shutil.copy(
        original_path / TS_FOLDER_NAME / SQL_FILENAME,
        temp_path / TS_FOLDER_NAME / SQL_FILENAME,
    )

    try:
        status = library.open_library(library_dir=temp_path)
        library.close()
        shutil.rmtree(temp_path)
        assert status.success
    except Exception as e:
        library.close()
        shutil.rmtree(temp_path)
        raise (e)


def test_db104_migration_preserves_entries(tmp_path: Path):
    """The v104 entries-table rebuild must preserve every row byte-for-byte.

    A fresh v104 library is populated with entries with distinct paths, a
    child folder, and a mix of set/unset datetime fields. The schema version
    is then forced back to 103 to make open_library re-run the v104 rebuild
    against real data. Every column on every row must survive the rebuild.
    """
    ts_dir = tmp_path / TS_FOLDER_NAME
    ts_dir.mkdir()

    lib = Library()
    assert lib.open_library(tmp_path).success
    assert lib.folder is not None
    primary = lib.folder

    extra_root = tmp_path / "extra"
    extra_root.mkdir()
    extra = lib.add_folder(extra_root)

    seed = [
        Entry(path=Path("a.txt"), folder=primary, fields=[], date_added=dt(2025, 1, 1)),
        Entry(path=Path("nested/b.md"), folder=primary, fields=[]),
        Entry(path=Path("a.txt"), folder=extra, fields=[], date_added=dt(2024, 6, 15)),
    ]
    lib.add_entries(seed)

    expected = sorted(
        (e.id, e.folder_id, e.path.as_posix(), e.filename, e.suffix, e.date_added)
        for e in lib.all_entries()
    )
    expected_count = lib.entries_count
    assert expected_count == 3

    lib.close()

    # Force the stored version back to 103 so the next open triggers the
    # v104 rebuild against real rows.
    db_path = tmp_path / TS_FOLDER_NAME / SQL_FILENAME
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE versions SET value = 103 WHERE key = 'CURRENT'")
        conn.commit()

    lib = Library()
    assert lib.open_library(tmp_path).success
    try:
        assert lib.entries_count == expected_count

        actual = sorted(
            (e.id, e.folder_id, e.path.as_posix(), e.filename, e.suffix, e.date_added)
            for e in lib.all_entries()
        )
        assert actual == expected
    finally:
        lib.close()
