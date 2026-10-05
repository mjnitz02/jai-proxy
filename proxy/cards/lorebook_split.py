"""Taking a card's embedded `character_book` back apart.

A card embeds exactly one lorebook -- the V2/V3 spec has a single
`character_book` -- so every importer flattens whatever the source attached into
one list of entries. This module is the inverse: given the book as it sits on a
card, recover the lorebooks it was assembled from, and give each one the
identity keys the archive-wide index (`proxy.archive.lorebooks`) groups on.

Pure functions over plain dicts, no I/O and no pydantic: the books come off
cards written by five importers, and a Chub book in particular carries entry
fields our own models would drop (see `proxy.sources.chub`).

How much can be recovered depends on what the importer stamped:

* **JanitorAI** -- `LorebookMapper` records `extensions.jai_sources` (script id,
  title, entry count per attached lorebook) on the book, in entry order. The
  counts tile the entry list exactly, so the split is lossless and each part
  has the provider's own id.
* **Chub** -- the book is one lorebook whole (a linked lorebook *replaces* the
  embedded one in `chub.build_v2_from_chub`, it is never appended), identified
  by the linked project's path when there is one.
* **Everything else** (saucepan, hand-dropped PNGs) -- one part, no provider id.
  It is still deduplicated, but only against books with identical entries.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


def norm_text(value: Any) -> str:
    """Whitespace-collapsed and case-folded. Two copies of an entry routinely
    differ by a trailing newline or a re-wrapped paragraph and nothing else."""
    return " ".join(value.split()).casefold() if isinstance(value, str) else ""


def _key_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [k.strip() for k in value if isinstance(k, str) and k.strip()]


def digest(text: str) -> str:
    """A short stable id for `text`."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def entry_hash(entry: dict[str, Any]) -> str:
    """What makes two entries the same *version*: the prose and what triggers
    it. Deliberately not the title, ordering or any per-card bookkeeping
    (`id`, `display_index`), which differ between two cards carrying the very
    same entry."""
    keys = sorted(norm_text(k) for k in _key_list(entry.get("keys")))
    secondary = sorted(norm_text(k) for k in _key_list(entry.get("secondary_keys")))
    return digest("\x00".join((norm_text(entry.get("content")), "\x01".join(keys), "\x01".join(secondary))))


def entry_title(entry: dict[str, Any], strip_prefix: str = "") -> str:
    """The entry's human label. `strip_prefix` undoes the `[Book title] ` that
    `LorebookMapper` prepends to comments when it concatenates several books,
    so the same entry reads the same whether its card attached one book or
    three."""
    title = entry.get("comment") or entry.get("name") or ""
    title = title.strip() if isinstance(title, str) else ""
    if strip_prefix and title.startswith(strip_prefix):
        title = title[len(strip_prefix) :].strip()
    return title


def fingerprint(hashes: list[str] | tuple[str, ...]) -> str:
    """A book's content identity: its set of entry versions, order-free."""
    return digest("\x00".join(sorted(set(hashes))))


@dataclass(frozen=True, slots=True)
class BookPart:
    """One source lorebook, as recovered from one card's embedded book."""

    title: str
    # "janitor", "chub" or "embedded" -- how the part was recovered, not which
    # importer wrote the card.
    kind: str
    # Provider identities, e.g. `jai:<script uuid>` or `chub:<project path>`.
    # Empty when the importer stamped none.
    refs: tuple[str, ...]
    entries: tuple[dict[str, Any], ...]
    # The `[Title] ` prefix this part's entry comments carry on the card.
    comment_prefix: str = ""


def _entries(book: dict[str, Any]) -> list[Any]:
    entries = book.get("entries")
    # SillyTavern's own world-info files key entries by index; a card that
    # passed through one can carry that shape instead of the spec's list.
    if isinstance(entries, dict):
        return list(entries.values())
    return entries if isinstance(entries, list) else []


def _usable(entries: list[Any]) -> tuple[dict[str, Any], ...]:
    return tuple(
        e
        for e in entries
        if isinstance(e, dict) and (norm_text(e.get("content")) or _key_list(e.get("keys")))
    )


def _jai_parts(book: dict[str, Any], entries: list[Any]) -> list[BookPart] | None:
    extensions = book.get("extensions")
    sources = extensions.get("jai_sources") if isinstance(extensions, dict) else None
    if not isinstance(sources, list) or not sources:
        return None
    counts = [s.get("entry_count") if isinstance(s, dict) else None for s in sources]
    # The split is only trusted when the stamped counts tile the entries
    # exactly. A book edited since (an entry deleted in a console and the card
    # re-adopted) no longer does, and guessing the seams would mis-attribute
    # entries -- it falls back to one unidentified part instead.
    if not all(isinstance(c, int) and not isinstance(c, bool) and c >= 0 for c in counts):
        return None
    if sum(counts) != len(entries):
        return None

    multi = len(sources) > 1
    parts: list[BookPart] = []
    start = 0
    for source, count in zip(sources, counts):
        chunk = _usable(entries[start : start + count])
        start += count
        if not chunk:
            continue
        title = source.get("title") if isinstance(source.get("title"), str) else ""
        script_id = source.get("id") if isinstance(source.get("id"), str) else ""
        parts.append(
            BookPart(
                title=title.strip(),
                kind="janitor",
                refs=(f"jai:{script_id}",) if script_id else (),
                entries=chunk,
                comment_prefix=f"[{title}] " if multi and title else "",
            )
        )
    return parts


def _chub_path(value: Any) -> str:
    """A Chub lorebook project path, normalized. Some `related_lorebooks`
    entries carry a doubled `lorebooks/lorebooks/` prefix for the same project
    the book itself names with one."""
    if not isinstance(value, str):
        return ""
    path = value.strip().strip("/")
    while path.startswith("lorebooks/lorebooks/"):
        path = path[len("lorebooks/") :]
    return path if path.startswith("lorebooks/") else ""


def _chub_refs(book: dict[str, Any], card_extensions: dict[str, Any], entries: tuple[dict[str, Any], ...]) -> tuple[str, ...]:
    paths: list[str] = []
    # The path the resolved lorebook names itself by...
    book_ext = book.get("extensions")
    book_chub = book_ext.get("chub") if isinstance(book_ext, dict) else None
    if isinstance(book_chub, dict):
        paths.append(_chub_path(book_chub.get("full_path")))
    # ...and the one the character pointed at. Both, because they can differ
    # for the same book (a renamed or re-published project), and sharing either
    # is what lets the index see two cards' copies as one lorebook. Only with a
    # single related lorebook and entries Chub itself flags as linked: a card
    # naming a related book while embedding its own does not carry that book.
    card_chub = card_extensions.get("chub")
    related = card_chub.get("related_lorebooks") if isinstance(card_chub, dict) else None
    if isinstance(related, list) and len(related) == 1 and isinstance(related[0], dict):
        linked = any(
            isinstance(e.get("extensions"), dict) and e["extensions"].get("linked") is True for e in entries
        )
        if linked:
            paths.append(_chub_path(related[0].get("path")))
    return tuple(dict.fromkeys(f"chub:{p}" for p in paths if p))


def split_book(book: Any, card_extensions: dict[str, Any] | None = None) -> list[BookPart]:
    """The lorebooks a card's `character_book` was assembled from, in entry
    order. Empty when the card has no usable lore."""
    if not isinstance(book, dict):
        return []
    raw = _entries(book)
    if not raw:
        return []

    jai = _jai_parts(book, raw)
    if jai is not None:
        return jai

    entries = _usable(raw)
    if not entries:
        return []
    name = book.get("name") if isinstance(book.get("name"), str) else ""
    refs = _chub_refs(book, card_extensions or {}, entries)
    return [BookPart(title=name.strip(), kind="chub" if refs else "embedded", refs=refs, entries=entries)]
