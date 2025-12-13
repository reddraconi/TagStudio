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
    files_not_in_library: list[Path] = field(default_factory=list)
    current_folder: "Folder | None" = None
    _duplicate_files: dict[str, list[Path]] = field(default_factory=dict)

    @property
    def files_count(self) -> int:
        return len(self.files_not_in_library)

    def save_new_files(self) -> Iterator[int]:
        """Save the list of files that are not in the library."""
        batch_size = 200
        folder = self.current_folder or unwrap(self.library.folder)

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
                for entry_path in self.files_not_in_library[index:end]
            ]
            self.library.add_entries(entries)
            index = end
        self.files_not_in_library = []

    def __check_duplicate_filename(self, filename: str, path: Path) -> None:
        """Track files with duplicate names for potential duplicate detection."""
        if filename not in self._duplicate_files:
            self._duplicate_files[filename] = []
        self._duplicate_files[filename].append(path)

    def refresh_dir(
        self, source: Path | Folder, force_internal_tools: bool = False
    ) -> Iterator[int]:
        """Scan a directory for files, and add those relative filenames to internal variables.

        Args:
            source: Either a Path (for backward compat) or a Folder object to scan.
            force_internal_tools: Force use of internal tools (wcmatch) vs system tools (ripgrep).
        """
        # Handle backward compatibility: Path or Folder
        if isinstance(source, Path):
            # Legacy mode: Path provided directly
            scan_dir = source
            self.current_folder = self.library.folder
        else:
            # New mode: Folder object provided
            scan_dir = source.path
            self.current_folder = source

        if scan_dir is None:
            raise ValueError("No scan directory provided.")

        ignore_patterns = Ignore.get_patterns(scan_dir)

        if force_internal_tools:
            return self.__wc_add(scan_dir, ignore_to_glob(ignore_patterns))

        dir_list: list[str] | None = self.__get_dir_list(scan_dir, ignore_patterns)

        # Use ripgrep if it was found and working, else fallback to wcmatch.
        if dir_list is not None:
            return self.__rg_add(scan_dir, dir_list)
        else:
            return self.__wc_add(scan_dir, ignore_to_glob(ignore_patterns))

    def refresh_all_folders(
        self, force_internal_tools: bool = False
    ) -> Iterator[tuple[int, Folder, int, int]]:
        """Scan all source folders in the library.

        Yields:
            Tuple of (files_scanned, current_folder, folder_index, total_folders)
        """
        folders = self.library.get_source_folders()
        total_folders = len(folders)

        if total_folders == 0:
            logger.warning("[RefreshTracker] No source folders to scan")
            return

        for folder_index, folder in enumerate(folders):
            logger.info(
                "[RefreshTracker] Scanning folder",
                folder_path=folder.path,
                folder_num=folder_index + 1,
                total=total_folders,
            )
            for files_scanned in self.refresh_dir(folder, force_internal_tools):
                yield (files_scanned, folder, folder_index, total_folders)

    def __get_dir_list(self, library_dir: Path, ignore_patterns: list[str]) -> list[str] | None:
        """Use ripgrep to return a list of matched directories and files.

        Return `None` if ripgrep not found on system.
        """
        rg_path = shutil.which("rg")
        # Use ripgrep if found on system
        if rg_path is not None:
            logger.info("[Refresh: Using ripgrep for scanning]")

            compiled_ignore_path = library_dir / ".TagStudio" / ".compiled_ignore"

            # Write compiled ignore patterns (built-in + user) to a temp file to pass to ripgrep
            with open(compiled_ignore_path, "w") as pattern_file:
                pattern_file.write("\n".join(ignore_patterns))

            result = silent_run(
                " ".join(
                    [
                        "rg",
                        "--files",
                        "--follow",
                        "--hidden",
                        "--ignore-file",
                        f'"{str(compiled_ignore_path)}"',
                    ]
                ),
                cwd=library_dir,
                capture_output=True,
                text=True,
                shell=True,
            )
            compiled_ignore_path.unlink()

            if result.stderr:
                logger.error(result.stderr)

            return result.stdout.splitlines()  # pyright: ignore [reportReturnType]

        logger.warning("[Refresh: ripgrep not found on system]")
        return None

    def __rg_add(self, library_dir: Path, dir_list: list[str]) -> Iterator[int]:
        start_time_total = time()
        start_time_loop = time()
        dir_file_count = 0
        self.files_not_in_library = []

        for r in dir_list:
            f = pathlib.Path(r)

            end_time_loop = time()
            # Yield output every 1 second
            if (end_time_loop - start_time_loop) > 1.0:
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

            # Track potential duplicates
            self.__check_duplicate_filename(f.name, f)

            if not self.library.has_path_entry(f):
                self.files_not_in_library.append(f)

        end_time_total = time()
        yield dir_file_count
        logger.info(
            "[Refresh]: Directory scan time",
            path=library_dir,
            duration=(end_time_total - start_time_total),
            files_scanned=dir_file_count,
            tool_used="ripgrep (system)",
        )

    def __wc_add(self, library_dir: Path, ignore_patterns: list[str]) -> Iterator[int]:
        start_time_total = time()
        start_time_loop = time()
        dir_file_count = 0
        self.files_not_in_library = []

        logger.info("[Refresh]: Falling back to wcmatch for scanning")

        try:
            for f in pathlib.Path(str(library_dir)).glob(
                "***/*", flags=PATH_GLOB_FLAGS, exclude=ignore_patterns
            ):
                end_time_loop = time()
                # Yield output every 1 second
                if (end_time_loop - start_time_loop) > 1.0:
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

                relative_path = f.relative_to(library_dir)

                # Track potential duplicates
                self.__check_duplicate_filename(relative_path.name, relative_path)

                if not self.library.has_path_entry(relative_path):
                    self.files_not_in_library.append(relative_path)
        except ValueError:
            logger.info("[Refresh]: ValueError when refreshing directory with wcmatch!")

        end_time_total = time()
        yield dir_file_count
        logger.info(
            "[Refresh]: Directory scan time",
            path=library_dir,
            duration=(end_time_total - start_time_total),
            files_scanned=dir_file_count,
            tool_used="wcmatch (internal)",
        )
