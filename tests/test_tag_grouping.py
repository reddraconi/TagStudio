# Copyright (C) 2025
# Licensed under the GPL-3.0 License.
# Created for TagStudio: https://github.com/CyanVoxel/TagStudio

"""Unit tests for 'tag_grouping'. Duck-typed stand-ins for Entry / Tag."""

from dataclasses import dataclass, field

import pytest

from tagstudio.qt.tag_grouping import (
    TAG_SORT_KEYS,
    TagGroup,
    TagSortKey,
    get_tag_sort_key,
    group_entries_by_tag,
)


@dataclass(eq=False)
class _FakeColor:
    primary: str
    secondary: str | None = None


@dataclass(eq=False)
class _FakeTag:
    name: str
    color: _FakeColor | None = None


@dataclass(eq=False)
class _FakeEntry:
    id: int
    tags: set[_FakeTag] = field(default_factory=set)


def _tag(name: str, primary: str | None = None, secondary: str | None = None) -> _FakeTag:
    color = _FakeColor(primary=primary, secondary=secondary) if primary else None
    return _FakeTag(name=name, color=color)


def _sort_by_title() -> TagSortKey:
    return get_tag_sort_key("title")


def _sort_by_color() -> TagSortKey:
    return get_tag_sort_key("color")


# --- Registry basics ---------------------------------------------------------


def test_builtin_registry_has_title_and_color():
    ids = [k.id for k in TAG_SORT_KEYS]
    assert "title" in ids
    assert "color" in ids


def test_get_tag_sort_key_falls_back_to_first_when_id_unknown():
    assert get_tag_sort_key("does-not-exist").id == TAG_SORT_KEYS[0].id


# --- Title sort --------------------------------------------------------------


def test_title_sort_ascending_groups_tags_alphabetically():
    red = _tag("Red")
    blue = _tag("Blue")
    green = _tag("Green")
    entries = [
        _FakeEntry(1, tags={red}),
        _FakeEntry(2, tags={blue}),
        _FakeEntry(3, tags={green}),
    ]

    groups = group_entries_by_tag(entries, _sort_by_title(), ascending=True)

    assert [g.tag.name for g in groups] == ["Blue", "Green", "Red"]


def test_title_sort_is_case_insensitive():
    alpha = _tag("alpha")
    beta = _tag("Beta")
    gamma = _tag("GAMMA")
    entries = [_FakeEntry(i, tags={t}) for i, t in enumerate([gamma, beta, alpha], start=1)]

    groups = group_entries_by_tag(entries, _sort_by_title(), ascending=True)

    assert [g.tag.name for g in groups] == ["alpha", "Beta", "GAMMA"]


def test_title_sort_descending_reverses_order():
    a = _tag("apple")
    b = _tag("banana")
    entries = [_FakeEntry(1, tags={a}), _FakeEntry(2, tags={b})]

    groups = group_entries_by_tag(entries, _sort_by_title(), ascending=False)

    assert [g.tag.name for g in groups] == ["banana", "apple"]


# --- Multi-tag duplication ---------------------------------------------------


def test_multi_tag_entry_appears_in_every_groups_entry_list():
    red = _tag("Red")
    blue = _tag("Blue")
    e = _FakeEntry(1, tags={red, blue})

    groups = group_entries_by_tag([e], _sort_by_title(), ascending=True)

    names = [g.tag.name for g in groups]
    assert sorted(names) == ["Blue", "Red"]
    for g in groups:
        assert g.entries == [e]


def test_within_group_order_preserves_input_order():
    red = _tag("Red")
    e1 = _FakeEntry(1, tags={red})
    e2 = _FakeEntry(2, tags={red})
    e3 = _FakeEntry(3, tags={red})

    groups = group_entries_by_tag([e3, e1, e2], _sort_by_title(), ascending=True)

    assert len(groups) == 1
    assert [e.id for e in groups[0].entries] == [3, 1, 2]


# --- Untagged bucket ---------------------------------------------------------


def test_untagged_entries_land_in_a_trailing_none_tag_group():
    red = _tag("Red")
    tagged = _FakeEntry(1, tags={red})
    orphan = _FakeEntry(2)

    groups = group_entries_by_tag([tagged, orphan], _sort_by_title(), ascending=True)

    assert len(groups) == 2
    assert groups[0].tag is red
    assert groups[-1].tag is None
    assert groups[-1].entries == [orphan]


def test_untagged_group_remains_last_even_when_descending():
    a = _tag("alpha")
    orphan = _FakeEntry(2)
    tagged = _FakeEntry(1, tags={a})

    groups = group_entries_by_tag([tagged, orphan], _sort_by_title(), ascending=False)

    assert groups[-1].tag is None


def test_no_untagged_group_when_every_entry_is_tagged():
    a = _tag("Alpha")
    e = _FakeEntry(1, tags={a})
    groups = group_entries_by_tag([e], _sort_by_title(), ascending=True)
    assert all(g.tag is not None for g in groups)


# --- Color sort --------------------------------------------------------------


@pytest.mark.parametrize(
    ("ascending", "expected_order"),
    [
        (True, ["red", "yellow", "green", "cyan", "blue", "magenta"]),
        (False, ["magenta", "blue", "cyan", "green", "yellow", "red"]),
    ],
)
def test_color_sort_orders_by_hue(ascending: bool, expected_order: list[str]):
    tags = {
        "red": _tag("red-tag", primary="#ff0000"),
        "yellow": _tag("yellow-tag", primary="#ffff00"),
        "green": _tag("green-tag", primary="#00ff00"),
        "cyan": _tag("cyan-tag", primary="#00ffff"),
        "blue": _tag("blue-tag", primary="#0000ff"),
        "magenta": _tag("magenta-tag", primary="#ff00ff"),
    }
    entries = [_FakeEntry(i, tags={t}) for i, t in enumerate(tags.values(), start=1)]

    groups = group_entries_by_tag(entries, _sort_by_color(), ascending=ascending)
    ordered = [g.tag.name.removesuffix("-tag") for g in groups]

    assert ordered == expected_order


def test_color_sort_puts_uncolored_tags_after_colored_in_ascending():
    red = _tag("Red", primary="#ff0000")
    blue = _tag("Blue", primary="#0000ff")
    uncolored = _tag("Zebra")
    entries = [_FakeEntry(i, tags={t}) for i, t in enumerate([uncolored, red, blue], start=1)]

    groups = group_entries_by_tag(entries, _sort_by_color(), ascending=True)

    assert [g.tag.name for g in groups] == ["Red", "Blue", "Zebra"]


def test_color_sort_keeps_uncolored_tags_trailing_when_descending():
    red = _tag("Red", primary="#ff0000")
    blue = _tag("Blue", primary="#0000ff")
    uncolored = _tag("Zebra")
    entries = [_FakeEntry(i, tags={t}) for i, t in enumerate([uncolored, red, blue], start=1)]

    groups = group_entries_by_tag(entries, _sort_by_color(), ascending=False)

    # Colored tags reverse; uncolored stays at the end.
    assert [g.tag.name for g in groups] == ["Blue", "Red", "Zebra"]


def test_color_sort_uses_secondary_as_tiebreaker_on_equal_primary():
    a = _tag("A", primary="#ff0000", secondary="#000000")
    b = _tag("B", primary="#ff0000", secondary="#ffffff")
    entries = [_FakeEntry(1, tags={a}), _FakeEntry(2, tags={b})]

    groups = group_entries_by_tag(entries, _sort_by_color(), ascending=True)

    # Identical primaries; secondary lightness breaks the tie (black < white).
    assert [g.tag.name for g in groups] == ["A", "B"]


@pytest.mark.parametrize("bad_primary", ["", "#", "#xyz", "not-a-color", "#12345"])
def test_color_sort_groups_malformed_colors_with_uncolored(bad_primary: str):
    red = _tag("Red", primary="#ff0000")
    broken = _tag("Broken", primary=bad_primary)
    entries = [_FakeEntry(1, tags={red}), _FakeEntry(2, tags={broken})]

    # Malformed colors must not crash the sort and must trail behind real colors.
    groups = group_entries_by_tag(entries, _sort_by_color(), ascending=True)

    assert [g.tag.name for g in groups] == ["Red", "Broken"]


# --- Extensibility -----------------------------------------------------------


def test_registry_is_extensible_without_touching_existing_code():
    by_length = TagSortKey(
        id="name-length",
        label_translation_key="sort.tag.name_length",
        key_fn=lambda t: len(t.name),
    )

    short = _tag("Hi")
    medium = _tag("Hello")
    long_tag = _tag("Salutations")
    entries = [_FakeEntry(i, tags={t}) for i, t in enumerate([long_tag, short, medium], start=1)]

    groups = group_entries_by_tag(entries, by_length, ascending=True)

    assert [g.tag.name for g in groups] == ["Hi", "Hello", "Salutations"]


def test_tag_group_is_frozen():
    g = TagGroup(tag=_tag("Alpha"), entries=[])
    with pytest.raises(AttributeError):
        g.tag = None  # type: ignore[misc]
