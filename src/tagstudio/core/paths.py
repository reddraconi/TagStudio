"""XDG-compliant path utilities for TagStudio library metadata storage."""

from pathlib import Path

from platformdirs import user_data_dir


def get_default_data_dir() -> Path:
    r"""Get XDG-compliant default data directory.

    Returns platform-appropriate directory:
    - Linux: ~/.local/share/TagStudio
    - macOS: ~/Library/Application Support/TagStudio
    - Windows: C:\Users\<user>\AppData\Local\TagStudio\TagStudio

    Returns:
        Path to default data directory
    """
    return Path(user_data_dir("TagStudio", "TagStudio"))


def get_default_library_dir(library_name: str = "default") -> Path:
    """Get default library metadata directory.

    Args:
        library_name: Name of the library (used as subdirectory name)

    Returns:
        Path to library metadata directory (e.g., ~/.local/share/TagStudio/libraries/default)
    """
    return get_default_data_dir() / "libraries" / library_name
