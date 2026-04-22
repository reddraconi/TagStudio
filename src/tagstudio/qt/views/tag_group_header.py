# Copyright (C) 2025
# Licensed under the GPL-3.0 License.
# Created for TagStudio: https://github.com/CyanVoxel/TagStudio

"""Full-width section header shown between groups of thumbnails in Group-by-Tag mode."""

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from tagstudio.core.library.alchemy.models import Tag
from tagstudio.qt.mixed.tag_widget import (
    get_border_color,
    get_highlight_color,
    get_primary_color,
    get_text_color,
)
from tagstudio.qt.translations import Translations

if TYPE_CHECKING:
    from tagstudio.core.library.alchemy.library import Library


class TagGroupHeader(QWidget):
    """Row-wide header rendered above each tag group. 'tag' is 'None' for Untagged."""

    def __init__(
        self,
        tag: Tag | None,
        children: list[Tag] | None = None,
        lib: "Library | None" = None,
    ) -> None:
        super().__init__()
        self.tag = tag
        self.children_tags = list(children or [])
        self.lib = lib

        # Class-scoped selector so the border doesn't cascade to QLabel children.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, on=True)
        self.setStyleSheet(
            "TagGroupHeader{"
            "border-top: 2px solid rgb(160, 160, 160);"
            "border-bottom: 2px solid rgb(160, 160, 160);"
            "}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        if tag is None:
            chip = QLabel(Translations["grouping.untagged"])
            chip.setStyleSheet(
                "QLabel{font-weight: 600;font-size: 13px;color: #888888;padding: 3px 8px;}"
            )
        else:
            chip = QLabel(self._display_name(tag))
            chip.setStyleSheet(self._pill_style(tag))

        # PlainText prevents QLabel from interpreting user-authored tag names as rich text.
        chip.setTextFormat(Qt.TextFormat.PlainText)
        chip.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(chip)

        for child in self.children_tags:
            child_chip = QLabel(self._display_name(child))
            child_chip.setStyleSheet(self._pill_style(child))
            child_chip.setTextFormat(Qt.TextFormat.PlainText)
            child_chip.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            layout.addWidget(child_chip)

        layout.addStretch(1)

        self.chip = chip

    def _display_name(self, tag: Tag) -> str:
        """Honor the library's disambiguation logic when a Library is available."""
        return self.lib.tag_display_name(tag) if self.lib else tag.name

    @staticmethod
    def _pill_style(tag: Tag) -> str:
        """Stylesheet mirroring TagWidget's fill/border/text derivation."""
        primary = get_primary_color(tag)
        border = (
            get_border_color(primary)
            if not (tag.color and tag.color.secondary and tag.color.color_border)
            else QColor(tag.color.secondary)
        )
        highlight = get_highlight_color(
            primary if not (tag.color and tag.color.secondary) else QColor(tag.color.secondary)
        )
        text = (
            QColor(tag.color.secondary)
            if tag.color and tag.color.secondary
            else get_text_color(primary, highlight)
        )
        return (
            "QLabel{"
            f"background: rgba{primary.toTuple()};"
            f"color: rgba{text.toTuple()};"
            "font-weight: 600;"
            "font-size: 13px;"
            f"border: 2px solid rgba{border.toTuple()};"
            "border-radius: 6px;"
            "padding: 3px 8px;"
            "}"
        )
