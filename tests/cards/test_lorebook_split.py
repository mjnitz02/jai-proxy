"""Splitting a card's embedded book back into its source lorebooks."""

from __future__ import annotations

from proxy.cards import lorebook_split


def _entry(title: str, content: str, keys: list[str] | None = None, **extra) -> dict:
    return {"comment": title, "content": content, "keys": keys or [title.lower()], **extra}


def test_entry_hash_ignores_whitespace_case_and_bookkeeping():
    a = _entry("Town", "A  small town.\n", ["Town", "village"], id=1, insertion_order=10)
    b = _entry("[World] Town", "a small town.", ["village", "town"], id=7, insertion_order=90)
    assert lorebook_split.entry_hash(a) == lorebook_split.entry_hash(b)


def test_entry_hash_changes_with_text_or_keys():
    base = _entry("Town", "A small town.", ["town"])
    assert lorebook_split.entry_hash(base) != lorebook_split.entry_hash(_entry("Town", "A large town.", ["town"]))
    assert lorebook_split.entry_hash(base) != lorebook_split.entry_hash(_entry("Town", "A small town.", ["city"]))


def test_jai_sources_split_the_concatenation_exactly():
    book = {
        "name": "Riot — JanitorAI lorebooks",
        "extensions": {
            "jai_sources": [
                {"id": "aaa", "title": "World", "entry_count": 2},
                {"id": "bbb", "title": "People", "entry_count": 1},
            ]
        },
        "entries": [
            _entry("[World] Town", "A town."),
            _entry("[World] River", "A river."),
            _entry("[People] Mayor", "The mayor."),
        ],
    }
    parts = lorebook_split.split_book(book)
    assert [(p.title, p.refs, len(p.entries)) for p in parts] == [
        ("World", ("jai:aaa",), 2),
        ("People", ("jai:bbb",), 1),
    ]
    # The `[Title] ` prefix the mapper added is undone, so the entry reads the
    # same as on a card that attached this book alone.
    assert lorebook_split.entry_title(parts[0].entries[0], parts[0].comment_prefix) == "Town"


def test_single_jai_source_has_no_prefix_to_strip():
    book = {
        "extensions": {"jai_sources": [{"id": "aaa", "title": "World", "entry_count": 1}]},
        "entries": [_entry("[OOC] Rules", "Be nice.")],
    }
    (part,) = lorebook_split.split_book(book)
    assert lorebook_split.entry_title(part.entries[0], part.comment_prefix) == "[OOC] Rules"


def test_jai_sources_that_no_longer_tile_the_entries_are_not_trusted():
    book = {
        "name": "Edited",
        "extensions": {"jai_sources": [{"id": "aaa", "title": "World", "entry_count": 5}]},
        "entries": [_entry("Town", "A town.")],
    }
    (part,) = lorebook_split.split_book(book)
    assert part.refs == () and part.kind == "embedded" and part.title == "Edited"


def test_chub_linked_book_takes_both_paths_as_identity():
    book = {
        "name": "Alteyra",
        "extensions": {"chub": {"full_path": "lorebooks/someone/alteyra-new"}},
        "entries": [_entry("Town", "A town.", extensions={"linked": True})],
    }
    card_ext = {"chub": {"related_lorebooks": [{"path": "lorebooks/lorebooks/someone/alteyra-old"}]}}
    (part,) = lorebook_split.split_book(book, card_ext)
    assert part.kind == "chub"
    assert part.refs == ("chub:lorebooks/someone/alteyra-new", "chub:lorebooks/someone/alteyra-old")


def test_chub_related_book_is_not_claimed_by_an_embedded_only_book():
    book = {"name": "Own", "entries": [_entry("Town", "A town.", extensions={"linked": False, "embedded": True})]}
    card_ext = {"chub": {"related_lorebooks": [{"path": "lorebooks/someone/world"}]}}
    (part,) = lorebook_split.split_book(book, card_ext)
    assert part.refs == () and part.kind == "embedded"


def test_empty_and_malformed_books_yield_nothing():
    assert lorebook_split.split_book(None) == []
    assert lorebook_split.split_book({"entries": []}) == []
    assert lorebook_split.split_book({"entries": [{"content": "", "keys": []}, "junk"]}) == []


def test_entries_keyed_by_index_are_read():
    book = {"name": "ST", "entries": {"0": _entry("Town", "A town."), "1": _entry("River", "A river.")}}
    (part,) = lorebook_split.split_book(book)
    assert len(part.entries) == 2
