import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, override

from PySide6.QtCore import QPoint, QRect, QSize, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLayout, QLayoutItem, QScrollArea, QWidget

from tagstudio.core.constants import TAG_ARCHIVED, TAG_FAVORITE
from tagstudio.core.library.alchemy.enums import ItemType
from tagstudio.core.library.alchemy.models import Entry, Tag
from tagstudio.core.utils.types import unwrap
from tagstudio.qt.mixed.item_thumb import BadgeType, ItemThumb
from tagstudio.qt.previews.renderer import ThumbRenderer
from tagstudio.qt.views.tag_group_header import TagGroupHeader

if TYPE_CHECKING:
    from tagstudio.qt.ts_qt import QtDriver


@dataclass(frozen=True)
class GridEntry:
    """A single thumbnail cell in the grid."""

    entry_id: int


@dataclass(frozen=True)
class GridHeader:
    """A full-width section header between thumbnail cells.

    'tag' is 'None' for the Untagged group. 'children' is the list
    of direct child tags (empty when the header tag has none).
    """

    tag: Tag | None
    children: tuple[Tag, ...] = ()


GridItem = GridEntry | GridHeader


# Header rows are shorter than thumbnail rows so sections don't leave
# large whitespace. Layout spacing is added on top at render time.
_HEADER_ROW_HEIGHT = 40


def compute_grid_layout(
    items: Sequence[GridItem], per_row: int
) -> tuple[list[tuple[int, int]], int]:
    """Return per-item '(col, row)' positions plus the total row count.

    Entries flow left-to-right, wrapping at 'per_row'. Headers always
    start a new row and consume it entirely.
    """
    if per_row <= 0:
        return [(0, i) for i, _ in enumerate(items)], len(items)
    positions: list[tuple[int, int]] = []
    row = 0
    col = 0
    for item in items:
        if isinstance(item, GridHeader):
            if col > 0:
                row += 1
                col = 0
            positions.append((0, row))
            row += 1
        else:
            if col >= per_row:
                row += 1
                col = 0
            positions.append((col, row))
            col += 1
    total_rows = row if col == 0 else row + 1
    return positions, total_rows


class ThumbGridLayout(QLayout):
    # Id of first visible entry
    visible_changed = Signal(int)

    def __init__(self, driver: "QtDriver", scroll_area: QScrollArea) -> None:
        super().__init__(None)
        self.driver: QtDriver = driver
        self.scroll_area: QScrollArea = scroll_area

        self._item_thumbs: list[ItemThumb] = []
        self._items: list[QLayoutItem] = []

        self._grid_items: list[GridItem] = []
        self._entry_ids: list[int] = []
        self._entries: dict[int, Entry] = {}
        # Tag.id -> {Entry.id}
        self._tag_entries: dict[int, set[int]] = {}
        self._entry_paths: dict[Path, int] = {}
        # Entry.id -> thumb widget indices. Ancestor expansion can place
        # one entry under multiple headers, so it may occupy several
        # widgets at once.
        self._entry_items: dict[int, list[int]] = {}

        # grid-item index -> header widget.
        self._header_widgets: dict[int, QWidget] = {}

        self._render_results: dict[Path, Any] = {}
        self._renderer: ThumbRenderer = ThumbRenderer(self.driver)
        self._renderer.updated.connect(self._on_rendered)
        self._render_cutoff: float = 0.0

        # (item_start, item_end, per_row, width_offset, tuple(row_heights)).
        self._last_page_update: tuple | None = None

        self._scroll_to: int | None = None

    def scroll_to(self, entry_id: int):
        self._scroll_to = entry_id

    def set_entries(self, entry_ids: list[int]):
        """Flat grid of thumbnails, no section headers."""
        self.set_items([GridEntry(eid) for eid in entry_ids])

    def set_items(self, items: Iterable[GridItem]):
        """Mixed grid: thumbnails interspersed with section headers."""
        new_items = list(items)
        # Fast path for unchanged content (e.g. a thumb-size change).
        # Rebuilding headers would stall thumbnail repainting.
        if new_items == self._grid_items:
            self._render_results.clear()
            self.driver.thumb_job_queue.queue.clear()
            self._render_cutoff = time.time()
            self._last_page_update = None
            self._queue_loading_placeholder()
            return

        self.scroll_area.verticalScrollBar().setValue(0)

        for header in self._header_widgets.values():
            header.setParent(None)
            header.deleteLater()
        self._header_widgets.clear()

        self._grid_items = new_items
        self._entry_ids = [it.entry_id for it in self._grid_items if isinstance(it, GridEntry)]
        self._entries.clear()
        self._tag_entries.clear()
        self._entry_paths.clear()

        # Parent headers to the layout's owner and position them from
        # setGeometry. Adding them to the QLayout would trigger a
        # recursive relayout inside set_items.
        parent = self.parentWidget()
        for index, item in enumerate(self._grid_items):
            if isinstance(item, GridHeader):
                header = TagGroupHeader(item.tag, list(item.children), lib=self.driver.lib)
                if parent is not None:
                    header.setParent(parent)
                    header.show()
                self._header_widgets[index] = header

        self._entry_items.clear()
        self._render_results.clear()
        self.driver.thumb_job_queue.queue.clear()
        self._render_cutoff = time.time()

        self._queue_loading_placeholder()

        self._last_page_update = None

    def _queue_loading_placeholder(self):
        """Queue the empty-path render used to fill in-progress thumbnails."""
        base_size: tuple[int, int] = (
            self.driver.main_window.thumb_size,
            self.driver.main_window.thumb_size,
        )
        self.driver.thumb_job_queue.put(
            (
                self._renderer.render,
                (
                    self._render_cutoff,
                    Path(),
                    base_size,
                    self.driver.main_window.devicePixelRatio(),
                    True,
                    True,
                ),
            )
        )

    def update_selected(self):
        for item_thumb in self._item_thumbs:
            value = item_thumb.item_id in self.driver._selected
            item_thumb.thumb_button.set_selected(value)

    def add_tags(self, entry_ids: Iterable[int], tag_ids: Iterable[int]):
        for tag_id in tag_ids:
            self._tag_entries.setdefault(tag_id, set()).update(entry_ids)

    def remove_tags(self, entry_ids: Iterable[int], tag_ids: Iterable[int]):
        for tag_id in tag_ids:
            self._tag_entries.setdefault(tag_id, set()).difference_update(entry_ids)

    def _fetch_entries(self, ids: Iterable[int]):
        ids = [id for id in ids if id not in self._entries]
        entries = self.driver.lib.get_entries(ids)
        for entry in entries:
            self._entry_paths[unwrap(self.driver.lib.library_dir) / entry.path] = entry.id
            self._entries[entry.id] = entry

        tag_ids = [TAG_ARCHIVED, TAG_FAVORITE]
        tag_entries = self.driver.lib.get_tag_entries(tag_ids, ids)
        for tag_id, entries in tag_entries.items():
            self._tag_entries.setdefault(tag_id, set()).update(entries)

    def _on_rendered(self, timestamp: float, image: QPixmap, size: QSize, file_path: Path):
        if timestamp < self._render_cutoff:
            return
        self._render_results[file_path] = (timestamp, image, size, file_path)

        # If this is the loading image update all item_thumbs with pending thumbnails
        if file_path == Path():
            for path, entry_id in self._entry_paths.items():
                if self._render_results.get(path, None) is None:
                    self._update_thumb(entry_id, image, size, file_path)
            return

        if file_path not in self._entry_paths:
            return
        entry_id = self._entry_paths[file_path]
        self._update_thumb(entry_id, image, size, file_path)

    def _update_thumb(self, entry_id: int, image: QPixmap, size: QSize, file_path: Path):
        indices = self._entry_items.get(entry_id)
        if not indices:
            return
        for index in indices:
            if index < 0 or index >= len(self._item_thumbs):
                continue
            item_thumb = self._item_thumbs[index]
            # Intentionally no rendered_path-match skip here: paths don't change when the
            # thumb size does, so a path-only check would drop the fresh render and leave
            # the widget stretching its previous-size pixmap until the user scrolls.
            item_thumb.update_thumb(image, file_path)
            item_thumb.update_size(size)
            item_thumb.set_filename_text(file_path)
            item_thumb.set_extension(file_path)

    def _item_thumb(self, index: int) -> ItemThumb:
        if w := getattr(self.driver, "main_window", None):
            base_size = (w.thumb_size, w.thumb_size)
        else:
            base_size = (128, 128)
        while index >= len(self._item_thumbs):
            show_filename = self.driver.settings.show_filenames_in_grid
            item = ItemThumb(
                ItemType.ENTRY,
                self.driver.lib,
                self.driver,
                base_size,
                show_filename_label=show_filename,
            )
            self._item_thumbs.append(item)
            self.addWidget(item)
        return self._item_thumbs[index]

    def _size(self, width: int) -> tuple[int, int, int]:
        if len(self._entry_ids) == 0:
            return 0, 0, 0
        spacing = self.spacing()

        _item_thumb = self._item_thumb(0)
        item = self._items[0]
        item_size = item.sizeHint()
        item_width = item_size.width()
        item_height = item_size.height()

        width_offset = item_width + spacing
        height_offset = item_height + spacing

        if width_offset == 0:
            return 0, 0, height_offset
        per_row = int(width / width_offset)

        return per_row, width_offset, height_offset

    def _layout_cache(
        self, width: int
    ) -> tuple[list[tuple[int, int]], list[int], list[int], int, int]:
        """Return per-item positions, row heights, cumulative y per row, per_row, and width_offset."""  # noqa: E501
        per_row, width_offset, entry_row_height = self._size(width)
        if per_row == 0:
            return [], [], [], 0, width_offset
        positions, total_rows = compute_grid_layout(self._grid_items, per_row)
        row_kinds: list[bool] = [False] * total_rows
        for (_col, row), item in zip(positions, self._grid_items, strict=True):
            if isinstance(item, GridHeader):
                row_kinds[row] = True
        spacing = self.spacing()
        header_row_height = _HEADER_ROW_HEIGHT + spacing
        row_heights = [
            header_row_height if is_header else entry_row_height for is_header in row_kinds
        ]
        row_y: list[int] = [0] * total_rows
        for i in range(1, total_rows):
            row_y[i] = row_y[i - 1] + row_heights[i - 1]
        return positions, row_heights, row_y, per_row, width_offset

    @override
    def heightForWidth(self, arg__1: int) -> int:
        width = arg__1
        if len(self._grid_items) == 0:
            return 0
        _, row_heights, _, per_row, _ = self._layout_cache(width)
        if per_row == 0:
            _, _, height_offset = self._size(width)
            return height_offset
        return sum(row_heights)

    @override
    def setGeometry(self, arg__1: QRect) -> None:
        super().setGeometry(arg__1)
        rect = arg__1
        if len(self._grid_items) == 0:
            for item in self._item_thumbs:
                item.setGeometry(32_000, 32_000, 0, 0)
            for header in self._header_widgets.values():
                header.setGeometry(32_000, 32_000, 0, 0)
            return

        positions, row_heights, row_y, per_row, width_offset = self._layout_cache(rect.right())
        if per_row == 0:
            return
        total_rows = len(row_heights)
        spacing = self.spacing()

        view_height = self.parentWidget().parentWidget().height()
        offset = self.scroll_area.verticalScrollBar().value()

        if self._scroll_to is not None:
            for grid_idx, item in enumerate(self._grid_items):
                if isinstance(item, GridEntry) and item.entry_id == self._scroll_to:
                    value = row_y[positions[grid_idx][1]]
                    self.scroll_area.verticalScrollBar().setMaximum(value)
                    self.scroll_area.verticalScrollBar().setSliderPosition(value)
                    offset = value
                    break
            self._scroll_to = None

        row_start = 0
        while row_start < total_rows and row_y[row_start] + row_heights[row_start] <= offset:
            row_start += 1
        row_end = row_start
        while row_end < total_rows and row_y[row_end] < offset + view_height:
            row_end += 1
        # First entry at or after the current scroll row, skipping any leading header.
        # Drives page_positions so returning to this page restores the scroll anchor.
        for grid_idx, (_col, row) in enumerate(positions):
            if row < row_start:
                continue
            item = self._grid_items[grid_idx]
            if isinstance(item, GridEntry):
                self.visible_changed.emit(item.entry_id)
                break
        # Preload 3 rows on each side.
        row_start = max(0, row_start - 3)
        row_end = min(total_rows, row_end + 3)

        item_start = 0
        while item_start < len(positions) and positions[item_start][1] < row_start:
            item_start += 1
        item_end = item_start
        while item_end < len(positions) and positions[item_end][1] < row_end:
            item_end += 1

        cache_key = (item_start, item_end, per_row, width_offset, tuple(row_heights))
        if cache_key == self._last_page_update:
            return
        self._last_page_update = cache_key

        visible_entry_ids: list[int] = [
            it.entry_id for it in self._grid_items[item_start:item_end] if isinstance(it, GridEntry)
        ]

        # Drain the queue if it has piled up past two screens' worth.
        visible_rows = row_end - row_start
        if len(self.driver.thumb_job_queue.queue) > (per_row * max(visible_rows, 1) * 2):
            self.driver.thumb_job_queue.queue.clear()
            pending = [k for k, v in self._render_results.items() if v is None and k != Path()]
            for k in pending:
                self._render_results.pop(k)

        # Rotate widgets so previously-rendered entries reuse them (avoids re-decode).
        if visible_entry_ids:
            _ = self._item_thumb(len(visible_entry_ids) - 1)
        for thumb_idx, entry_id in enumerate(visible_entry_ids):
            prev_indices = self._entry_items.get(entry_id)
            if not prev_indices:
                continue
            prev_item_index = prev_indices[0]
            if thumb_idx == prev_item_index:
                break
            diff = prev_item_index - thumb_idx
            self._items = self._items[diff:] + self._items[:diff]
            self._item_thumbs = self._item_thumbs[diff:] + self._item_thumbs[:diff]
            break
        self._entry_items.clear()

        # Park unused thumb widgets off-screen.
        for item in self._item_thumbs[len(visible_entry_ids) :]:
            item.setGeometry(32_000, 32_000, 0, 0)

        for grid_idx, header in self._header_widgets.items():
            _, row = positions[grid_idx]
            if row_start <= row < row_end:
                header_height = row_heights[row] - spacing
                header.setGeometry(QRect(0, row_y[row], rect.width(), header_height))
            else:
                header.setGeometry(32_000, 32_000, 0, 0)

        missing = set(visible_entry_ids) - self._entries.keys()
        if missing:
            self._fetch_entries(missing)

        ratio = self.driver.main_window.devicePixelRatio()
        base_size: tuple[int, int] = (
            self.driver.main_window.thumb_size,
            self.driver.main_window.thumb_size,
        )
        library_dir = unwrap(self.driver.lib.library_dir)
        timestamp = time.time()
        thumb_idx = 0
        for grid_idx in range(item_start, item_end):
            item = self._grid_items[grid_idx]
            if not isinstance(item, GridEntry):
                continue
            entry_id = item.entry_id
            entry = self._entries[entry_id]
            col, row = positions[grid_idx]
            self._entry_items.setdefault(entry_id, []).append(thumb_idx)
            item_thumb = self._item_thumb(thumb_idx)
            layout_item = self._items[thumb_idx]
            thumb_idx += 1

            item_x = width_offset * col
            item_y = row_y[row]
            item_thumb.setGeometry(QRect(QPoint(item_x, item_y), layout_item.sizeHint()))
            file_path = library_dir / entry.path
            item_thumb.set_item(entry)

            if result := self._render_results.get(file_path):
                _t, im, s, p = result
                if item_thumb.rendered_path == p:
                    continue
                self._update_thumb(entry_id, im, s, p)
            else:
                if Path() in self._render_results:
                    _t, im, s, p = self._render_results[Path()]
                    self._update_thumb(entry_id, im, s, p)

                if file_path not in self._render_results:
                    self._render_results[file_path] = None
                    self.driver.thumb_job_queue.put(
                        (
                            self._renderer.render,
                            (timestamp, file_path, base_size, ratio, False, True),
                        )
                    )

        # Set selection and badges after positioning to avoid first-frame flicker.
        # _fetch_entries populates these keys; guard in case no entries are in view.
        archived = self._tag_entries.setdefault(TAG_ARCHIVED, set())
        favorite = self._tag_entries.setdefault(TAG_FAVORITE, set())
        selected = self.driver._selected
        for entry_id, thumb_indices in self._entry_items.items():
            is_selected = entry_id in selected
            is_archived = entry_id in archived
            is_favorite = entry_id in favorite
            for thumb_index in thumb_indices:
                if thumb_index < 0 or thumb_index >= len(self._item_thumbs):
                    continue
                item_thumb = self._item_thumbs[thumb_index]
                item_thumb.thumb_button.set_selected(is_selected)
                item_thumb.assign_badge(BadgeType.ARCHIVED, is_archived)
                item_thumb.assign_badge(BadgeType.FAVORITE, is_favorite)

    @override
    def addItem(self, arg__1: QLayoutItem) -> None:
        self._items.append(arg__1)

    @override
    def count(self) -> int:
        return len(self._items)

    @override
    def hasHeightForWidth(self) -> bool:
        return True

    @override
    def itemAt(self, index: int) -> QLayoutItem:
        if 0 <= index < len(self._items):
            return self._items[index]
        return None  # pyright: ignore[reportReturnType]

    @override
    def takeAt(self, index: int) -> QLayoutItem:
        # Required for Qt's setParent(None) detach path; default raises NotImplementedError.
        if 0 <= index < len(self._items):
            item = self._items.pop(index)
            widget = item.widget() if item else None
            if isinstance(widget, ItemThumb) and widget in self._item_thumbs:
                self._item_thumbs.remove(widget)
            return item
        return None  # pyright: ignore[reportReturnType]

    @override
    def sizeHint(self) -> QSize:
        self._item_thumb(0)
        return self._items[0].minimumSize()
