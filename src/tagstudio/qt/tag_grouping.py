# Copyright (C) 2025
# Licensed under the GPL-3.0 License.
# Created for TagStudio: https://github.com/CyanVoxel/TagStudio

"""Client-side grouping of entries by tag for the thumbnail grid.

Each unique tag becomes a group; entries with multiple tags appear in
each of their tags' groups. Entries with no tags collect into a trailing
'None'-keyed group. Sort modes live in the 'TAG_SORT_KEYS' registry.
"""

import colorsys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from tagstudio.core.library.alchemy.models import Tag


@dataclass(frozen=True)
class TagSortKey:
    """An ordering over 'Tag' objects.

    'always_trailing' tags (e.g. uncolored tags when sorting by color)
    stay after the rest regardless of asc/desc direction.
    """

    id: str
    label_translation_key: str
    key_fn: Callable[[Tag], Any]
    always_trailing: Callable[[Tag], bool] | None = None


@dataclass(frozen=True)
class TagGroup:
    """One section of the grouped view. 'tag' is 'None' for Untagged."""

    tag: Tag | None
    entries: list[Any]


def _hsl(hex_color: str) -> tuple[float, float, float] | None:
    """Convert '#RRGGBB' to '(hue, saturation, lightness)' in [0.0, 1.0]. 'None' if malformed."""
    cleaned = hex_color.lstrip("#")
    if len(cleaned) != 6:
        return None
    try:
        r = int(cleaned[0:2], 16) / 255.0
        g = int(cleaned[2:4], 16) / 255.0
        b = int(cleaned[4:6], 16) / 255.0
    except ValueError:
        return None
    # colorsys returns HLS, not HSL.
    h, lightness, s = colorsys.rgb_to_hls(r, g, b)
    return h, s, lightness


def _color_sort_key(tag: Tag) -> tuple[float, ...]:
    """HSL of fill color, then border color as tiebreaker."""
    if tag.color is None:
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    primary = _hsl(tag.color.primary)
    if primary is None:
        # Malformed primary: the always_trailing hook groups this with uncolored tags.
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    ph, ps, pl = primary
    secondary = _hsl(tag.color.secondary) if tag.color.secondary else None
    if secondary is not None:
        sh, ss, sl = secondary
    else:
        sh = ss = sl = 0.0
    return (ph, ps, pl, sh, ss, sl)


def _is_uncolored(tag: Tag) -> bool:
    # Malformed primaries share the uncolored bucket so they don't sort ahead of
    # real colors on an all-zero key.
    return tag.color is None or _hsl(tag.color.primary) is None


TAG_SORT_KEYS: list[TagSortKey] = [
    TagSortKey(
        id="title",
        label_translation_key="sorting.tag.title",
        key_fn=lambda t: t.name.casefold(),
    ),
    TagSortKey(
        id="color",
        label_translation_key="sorting.tag.color",
        key_fn=_color_sort_key,
        always_trailing=_is_uncolored,
    ),
]


def get_tag_sort_key(key_id: str) -> TagSortKey:
    """Look up a sort key by id. Falls back to the first registered key."""
    for key in TAG_SORT_KEYS:
        if key.id == key_id:
            return key
    return TAG_SORT_KEYS[0]


def sort_tags(
    tags: Iterable[Tag],
    sort_key: TagSortKey,
    ascending: bool = True,
) -> list[Tag]:
    """Sort tags by 'sort_key', keeping 'always_trailing' tags after the rest."""
    trailing_predicate = sort_key.always_trailing or (lambda _t: False)
    primary = [t for t in tags if not trailing_predicate(t)]
    trailing = [t for t in tags if trailing_predicate(t)]
    primary.sort(key=sort_key.key_fn, reverse=not ascending)
    trailing.sort(key=sort_key.key_fn, reverse=not ascending)
    return primary + trailing


def group_entries_by_tag(
    entries: Iterable[Any],
    sort_key: TagSortKey,
    ascending: bool = True,
) -> list[TagGroup]:
    """Group entries by their tags, ordered by 'sort_key'. Within-group order follows input order."""  # noqa: E501
    tag_to_entries: dict[Tag, list[Any]] = {}
    untagged: list[Any] = []

    for entry in entries:
        if not entry.tags:
            untagged.append(entry)
            continue
        for tag in entry.tags:
            tag_to_entries.setdefault(tag, []).append(entry)

    groups: list[TagGroup] = [
        TagGroup(tag=t, entries=tag_to_entries[t])
        for t in sort_tags(tag_to_entries, sort_key, ascending=ascending)
    ]
    if untagged:
        groups.append(TagGroup(tag=None, entries=untagged))
    return groups
