# Copyright (C) 2025
# Licensed under the GPL-3.0 License.
# Created for TagStudio: https://github.com/CyanVoxel/TagStudio


import shutil
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime as dt
from pathlib import Path
from time import time

import structlog
from wcmatch import pathlib

from tagstudio.core.library.alchemy.library import Library
from tagstudio.core.library.alchemy.models import Entry, Folder
from tagstudio.core.library.ignore import PATH_GLOB_FLAGS, Ignore, ignore_to_glob
from tagstudio.core.utils.silent_subprocess import silent_run  # pyright: ignore
from tagstudio.core.utils.types import unwrap

logger = structlog.get_logger(__name__)


@dataclass
class RefreshTracker:
    library: Library
    # Each entry is (folder, relative_path) — the Folder the file belongs to and
    # its path relative to that folder's root.
    files_not_in_library: list[tuple[Folder, Path]] = field(default_factory=list)

    @property
    def files_count(self) -> int:
        return len(self.files_not_in_library)

    def save_new_files(self) -> Iterator[int]:
        """Save the list of files that are not in the library."""
        batch_size = 200

        index = 0
        while index < len(self.files_not_in_library):
            yield index
            end = min(len(self.files_not_in_library), index + batch_size)
            entries = [
                Entry(
                    path=entry_path,
                    folder=folder,
                    fields=[],
                    date_added=dt.now(),
                )
                for folder, entry_path in self.files_not_in_library[index:end]
            ]
            self.library.add_entries(entries)
            index = end
        self.files_not_in_library = []

    def refresh_folders(self, force_internal_tools: bool = False) -> Iterator[int]:
        """Scan every Folder registered in the library, including the primary.

        The primary folder may not yet be present in the `folders` table
        (open_sqlite_library expunges it before commit, so it only lands on
        disk later via cascade), so it must be merged in explicitly or it
        will be silently skipped once any other Folder has been added.
        """
        primary = self.library.folder
        folders: list[Folder] = []
        seen_paths: set[Path] = set()
        if primary is not None:
            folders.append(primary)
            seen_paths.add(primary.path)
        for folder in self.library.folders:
            if folder.path in seen_paths:
                continue
            folders.append(folder)
            seen_paths.add(folder.path)
        for folder in folders:
            # Skip folders whose on-disk root has disappeared (unmounted
            # volume, externally-deleted directory, or a malicious library
            # DB with a fictitious Folder.path). Without this guard the
            # scanner's subprocess call would raise FileNotFoundError on
            # cwd=folder.path and abort the entire refresh.
            if not folder.path.is_dir():
                logger.warning(
                    "[Refresh] Skipping folder whose path is not a directory",
                    path=folder.path,
                )
                continue
            yield from self.refresh_dir(folder, force_internal_tools)

    def refresh_dir(
        self, folder: Folder | Path, force_internal_tools: bool = False
    ) -> Iterator[int]:
        """Scan a single Folder for files, tracking new ones for import.

        Accepts either a Folder instance or a raw Path. When a Path is passed,
        it must match a Folder already registered in the library; the primary
        folder is resolved by path-equality as a convenience for legacy callers.
        """
        if self.library.library_dir is None:
            raise ValueError("No library directory set.")

        resolved_folder = self.__resolve_folder(folder)
        scan_root: Path = resolved_folder.path
        ts_root: Path = unwrap(self.library.library_dir)

        ignore_patterns = Ignore.get_patterns(ts_root)

        if force_internal_tools:
            return self.__wc_add(resolved_folder, ignore_to_glob(ignore_patterns))

        dir_list: list[str] | None = self.__get_dir_list(scan_root, ts_root, ignore_patterns)

        # Use ripgrep if it was found and working, else fallback to wcmatch.
        if dir_list is not None:
            return self.__rg_add(resolved_folder, dir_list)
        else:
            return self.__wc_add(resolved_folder, ignore_to_glob(ignore_patterns))

    def __resolve_folder(self, folder: Folder | Path) -> Folder:
        if isinstance(folder, Folder):
            return folder
        # Legacy callers pass the library directory Path; map to the primary Folder.
        if self.library.folder is not None and folder == self.library.folder.path:
            return self.library.folder
        for f in self.library.folders:
            if f.path == folder:
                return f
        raise ValueError(f"No registered Folder matches path: {folder}")

    def __get_dir_list(
        self, scan_root: Path, ts_root: Path, ignore_patterns: list[str]
    ) -> list[str] | None:
        """Use ripgrep to return a list of matched directories and files.

        Return `None` if ripgrep not found on system.
        """
        rg_path = shutil.which("rg")
        # Use ripgrep if found on system
        if rg_path is not None:
            logger.info("[Refresh: Using ripgrep for scanning]")

            compiled_ignore_path = ts_root / ".TagStudio" / ".compiled_ignore"

            # Write compiled ignore patterns (built-in + user) to a temp file to pass to ripgrep
            with open(compiled_ignore_path, "w") as pattern_file:
                pattern_file.write("\n".join(ignore_patterns))

            # Arguments passed as a list with shell=False so user-controlled
            # path segments (scan_root, compiled_ignore_path) cannot be
            # interpreted as shell syntax (backticks, $(...), quote-escape, etc.).
            # The try/finally ensures the temp pattern file is removed even if
            # silent_run raises (e.g. scan_root disappeared between check and
            # use), so it does not linger inside the library's .TagStudio dir.
            try:
                result = silent_run(
                    [
                        "rg",
                        "--files",
                        "--follow",
                        "--hidden",
                        "--ignore-file",
                        str(compiled_ignore_path),
                    ],
                    cwd=scan_root,
                    capture_output=True,
                    shell=False,
                    encoding="UTF-8",
                )
            finally:
                compiled_ignore_path.unlink(missing_ok=True)

            if result.stderr:
                logger.error(result.stderr)

            return result.stdout.splitlines()  # pyright: ignore [reportReturnType]

        logger.warning("[Refresh: ripgrep not found on system]")
        return None

    def __rg_add(self, folder: Folder, dir_list: list[str]) -> Iterator[int]:
        scan_root = folder.path
        start_time_total = time()
        start_time_loop = time()
        dir_file_count = 0

        for r in dir_list:
            relative = pathlib.Path(r)
            absolute = scan_root / relative

            end_time_loop = time()
            # Yield output every 1/30 of a second
            if (end_time_loop - start_time_loop) > 0.034:
                yield dir_file_count
                start_time_loop = time()

            # Skip if the file/path is already mapped in the Library
            if absolute in self.library.included_files:
                dir_file_count += 1
                continue

            # Ignore if the file is a directory
            if absolute.is_dir():
                continue

            dir_file_count += 1
            self.library.included_files.add(absolute)

            if not self.library.has_path_entry(relative, folder=folder):
                self.files_not_in_library.append((folder, relative))

        end_time_total = time()
        yield dir_file_count
        logger.info(
            "[Refresh]: Directory scan time",
            path=scan_root,
            duration=(end_time_total - start_time_total),
            files_scanned=dir_file_count,
            tool_used="ripgrep (system)",
        )

    def __wc_add(self, folder: Folder, ignore_patterns: list[str]) -> Iterator[int]:
        scan_root = folder.path
        start_time_total = time()
        start_time_loop = time()
        dir_file_count = 0

        logger.info("[Refresh]: Falling back to wcmatch for scanning")

        try:
            for f in pathlib.Path(str(scan_root)).glob(
                "***/*", flags=PATH_GLOB_FLAGS, exclude=ignore_patterns
            ):
                end_time_loop = time()
                # Yield output every 1/30 of a second
                if (end_time_loop - start_time_loop) > 0.034:
                    yield dir_file_count
                    start_time_loop = time()

                # Skip if the file/path is already mapped in the Library
                if f in self.library.included_files:
                    dir_file_count += 1
                    continue

                # Ignore if the file is a directory
                if f.is_dir():
                    continue

                dir_file_count += 1
                self.library.included_files.add(f)

                relative_path = f.relative_to(scan_root)

                if not self.library.has_path_entry(relative_path, folder=folder):
                    self.files_not_in_library.append((folder, relative_path))
        except ValueError:
            logger.info("[Refresh]: ValueError when refreshing directory with wcmatch!")

        end_time_total = time()
        yield dir_file_count
        logger.info(
            "[Refresh]: Directory scan time",
            path=scan_root,
            duration=(end_time_total - start_time_total),
            files_scanned=dir_file_count,
            tool_used="wcmatch (internal)",
        )
