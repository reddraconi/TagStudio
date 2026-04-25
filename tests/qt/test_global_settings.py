# Copyright (C) 2025
# Licensed under the GPL-3.0 License.
# Created for TagStudio: https://github.com/CyanVoxel/TagStudio


from pathlib import Path

from tagstudio.qt.global_settings import GlobalSettings, Theme


def test_read_settings(library_dir: Path):
    settings_path = library_dir / "settings.toml"
    with open(settings_path, "w", encoding="utf-8") as settings_file:
        settings_file.write("""
            language = "de"
            open_last_loaded_on_startup = true
            autoplay = true
            show_filenames_in_grid = true
            page_size = 1337
            show_filepath = 0
            dark_mode = 2
            date_format = "%x"
            hour_format = true
            zero_padding = true
        """)

    settings = GlobalSettings.read_settings(settings_path)
    assert settings.language == "de"
    assert settings.open_last_loaded_on_startup
    assert settings.autoplay
    assert settings.show_filenames_in_grid
    assert settings.page_size == 1337
    assert settings.show_filepath == 0
    assert settings.theme == Theme.SYSTEM
    assert settings.date_format == "%x"
    assert settings.hour_format
    assert settings.zero_padding


def test_read_settings_with_unicode_value_roundtrips(library_dir: Path):
    """A non-ASCII string value (e.g., a Japanese library path) round-trips through UTF-8."""
    settings_path = library_dir / "settings.toml"
    # "写真" is Japanese for "photos"; "Привет" is Russian for "hello".
    with open(settings_path, "w", encoding="utf-8") as f:
        f.write('language = "ja"\ndate_format = "%x 写真 Привет"\n')

    settings = GlobalSettings.read_settings(settings_path)
    assert settings.language == "ja"
    assert settings.date_format == "%x 写真 Привет"


def test_read_settings_recovers_from_legacy_codepage_bytes(library_dir: Path):
    """A settings file written under a non-UTF-8 Windows ANSI codepage must not crash startup.

    The realistic scenario: a user on Japanese Windows (cp932) saved settings with a
    previous TagStudio version that wrote the file using the system default encoding.
    Loading that file with strict UTF-8 would raise `UnicodeDecodeError` and break app
    startup. We use `errors="replace"` so any undecodable bytes become U+FFFD and the
    surrounding ASCII keys/values still parse normally.
    """
    settings_path = library_dir / "settings.toml"
    # Build a TOML file whose ASCII structure is intact but whose string *value* contains
    # raw cp932 bytes that are not valid UTF-8. This mirrors the on-disk shape of a
    # legacy-encoded settings file.
    legacy_value = "写真".encode("cp932")  # b"\x8e\xca\x90^" — invalid UTF-8
    payload = b'language = "ja"\ndate_format = "' + legacy_value + b'"\n'
    settings_path.write_bytes(payload)

    # The critical assertion is "does not raise". A previous strict-UTF-8 read would
    # raise UnicodeDecodeError here.
    settings = GlobalSettings.read_settings(settings_path)
    assert settings.language == "ja"
    # The mojibake value contains replacement characters but the field is still populated.
    assert "�" in settings.date_format


def test_save_writes_utf8(library_dir: Path, tmp_path: Path):
    """Saved settings must be valid UTF-8 regardless of the OS default encoding.

    Reading the file back as raw bytes and decoding strictly as UTF-8 must succeed.
    """
    settings_path = tmp_path / "settings.toml"
    settings = GlobalSettings(language="ja", date_format="写真 Привет", loaded_from=settings_path)
    settings.save()

    # Strict UTF-8 decode of the bytes on disk must succeed.
    raw = settings_path.read_bytes()
    decoded = raw.decode("utf-8")
    assert "写真" in decoded
    assert "Привет" in decoded

    # And it round-trips through read_settings.
    reloaded = GlobalSettings.read_settings(settings_path)
    assert reloaded.language == "ja"
    assert reloaded.date_format == "写真 Привет"
