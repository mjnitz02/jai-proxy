"""`/api/v1/lorebooks` -- lorebooks as entities.

The reads are derived from the cards by `proxy.archive.lorebooks`: which
distinct lorebooks the archive holds, which cards carry each, where copies have
drifted apart.

The writes record *decisions* -- these two lorebooks are one, these two entries
are one, this is the version to keep -- in `proxy.state.lorebook_decisions`.
None of them touches a card: a decision changes what these routes report, and
is undone by its matching DELETE. Writing chosen versions back onto cards is the
sync, which is separate.
"""

from __future__ import annotations

import difflib
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query

from proxy.api.schemas import (
    CardLorebookOut,
    LorebookChooseIn,
    LorebookChooseNewestOut,
    LorebookEntryCandidateOut,
    LorebookMergeIn,
    LorebookMergeOut,
    LorebookRefOut,
    LorebookCardOut,
    LorebookDetailOut,
    LorebookEntriesOut,
    LorebookEntryDetailOut,
    LorebookEntryOut,
    LorebookEntryVersionOut,
    LorebookOut,
    LorebookRevisionOut,
    LorebookSimilarOut,
    LorebooksOut,
    LorebookStatsOut,
)
from proxy.api.v1 import _shared
from proxy.archive import catalog, lorebooks
from proxy.cards import lorebook_split
from proxy.config import settings
from proxy.state import lorebook_decisions

router = APIRouter()

_PREVIEW_CHARS = 220
# How alike two entries' text must be to be offered as the same entry, and how
# much of each is compared. A bounded heuristic: the user confirms every merge.
_CANDIDATE_RATIO = 0.6
_COMPARE_CHARS = 2000


# The last decisions read, with the file key they were read at, so a browse
# page's worth of requests parses the file once rather than once each.
_decisions_cache: tuple[Any, lorebook_decisions.Decisions] | None = None


def _store() -> lorebook_decisions.DecisionsStore:
    """Built per call so a test that repoints the setting takes effect."""
    return lorebook_decisions.DecisionsStore(settings.lorebook_decisions_file)


def _indexes() -> tuple[catalog.ArchiveIndex, lorebooks.LorebookIndex]:
    global _decisions_cache
    idx = _shared.index()
    store = _store()
    key = (str(store.path), store.key())
    if _decisions_cache is None or _decisions_cache[0] != key:
        try:
            _decisions_cache = (key, store.read())
        except lorebook_decisions.DecisionsError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    return idx, lorebooks.index(idx, _decisions_cache[1], key)


def _write(action: Any) -> Any:
    """Run one store mutation, turning a failed write into a 500 that says why."""
    try:
        return action()
    except lorebook_decisions.DecisionsError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _merge_out(merge: lorebook_decisions.Merge) -> LorebookMergeOut:
    return LorebookMergeOut(id=merge.id, a_name=merge.a_name, b_name=merge.b_name, at=merge.at)


def _card_out(idx: catalog.ArchiveIndex, filename: str) -> LorebookCardOut:
    record = idx.get(filename)
    quoted = quote(filename, safe="")
    return LorebookCardOut(
        id=filename,
        name=record.name if record else filename,
        creator=record.creator if record else "",
        create_date=record.create_date if record else "",
        thumb_url=f"{_shared.PREFIX}/characters/{quoted}/thumb",
    )


def _book_fields(book: lorebooks.Lorebook) -> dict:
    return {
        "id": book.id,
        "name": book.name,
        "kinds": list(book.kinds),
        "refs": list(book.refs),
        "creators": list(book.creators),
        "card_count": len(book.cards),
        "entry_count": len(book.lines),
        "revision_count": len(book.revisions),
        "changed_entries": book.changed_lines,
        "similar_count": len(book.similar),
        "unresolved_entries": book.unresolved_lines,
        "pending_cards": len(book.pending_cards),
        "chars": book.chars,
    }


def _preview(content: str) -> str:
    return " ".join(content[: _PREVIEW_CHARS * 2].split())[:_PREVIEW_CHARS]


def _entry_out(lore: lorebooks.LorebookIndex, line: lorebooks.EntryLine, book_name: str) -> LorebookEntryOut:
    # The chosen version when there is one -- it is what the entry *is* now.
    newest = lore.version(line.chosen or line.versions[0].hash)
    content = newest.content if newest else ""
    return LorebookEntryOut(
        id=line.id,
        lorebook_id=line.lorebook_id,
        lorebook_name=book_name,
        title=line.title,
        keys=list(newest.keys) if newest else [],
        constant=newest.constant if newest else False,
        preview=_preview(content),
        chars=len(content),
        version_count=len(line.versions),
        card_count=line.card_count,
        resolved=line.resolved,
        pending_cards=len(line.pending_cards),
    )


def _candidates(
    lore: lorebooks.LorebookIndex, book: lorebooks.Lorebook, line: lorebooks.EntryLine
) -> list[LorebookEntryCandidateOut]:
    """Entries of the same lorebook that may be `line` under another title.

    Two entries on the same card are two entries by definition, so only lines
    that never share a card are compared -- which is also what keeps this cheap:
    in a lorebook with one revision every pair shares its cards and nothing is
    compared at all."""
    mine = lore.version(line.versions[0].hash)
    if mine is None or not mine.content:
        return []
    cards = {c for v in line.versions for c in v.cards}
    text = lorebook_split.norm_text(mine.content)[:_COMPARE_CHARS]
    matcher = difflib.SequenceMatcher(None, "", text, autojunk=False)
    scored: list[tuple[float, lorebooks.EntryLine, str]] = []
    for other in book.lines:
        if other.id == line.id or any(c in cards for v in other.versions for c in v.cards):
            continue
        theirs = lore.version(other.versions[0].hash)
        if theirs is None or not theirs.content:
            continue
        matcher.set_seq1(lorebook_split.norm_text(theirs.content)[:_COMPARE_CHARS])
        if matcher.real_quick_ratio() < _CANDIDATE_RATIO or matcher.quick_ratio() < _CANDIDATE_RATIO:
            continue
        ratio = matcher.ratio()
        if ratio >= _CANDIDATE_RATIO:
            scored.append((ratio, other, theirs.content))
    scored.sort(key=lambda item: -item[0])
    return [
        LorebookEntryCandidateOut(
            id=other.id,
            title=other.title,
            preview=_preview(content),
            similarity=round(ratio, 3),
            version_count=len(other.versions),
            card_count=other.card_count,
        )
        for ratio, other, content in scored[:5]
    ]


@router.get("/lorebooks", response_model=LorebooksOut, summary="Every distinct lorebook in the archive")
def list_lorebooks() -> LorebooksOut:
    _idx, lore = _indexes()
    stats = lore.stats
    return LorebooksOut(
        lorebooks=[LorebookOut(**_book_fields(book)) for book in lore.lorebooks()],
        stats=LorebookStatsOut(
            cards=stats.cards,
            lorebooks=stats.lorebooks,
            shared_lorebooks=stats.shared_lorebooks,
            entries_embedded=stats.entries_embedded,
            entries_unique=stats.entries_unique,
            changed_entries=stats.changed_lines,
            unresolved_entries=stats.unresolved_lines,
            pending_cards=stats.pending_cards,
        ),
    )


# Registered before `/lorebooks/{lorebook_id}` so "entries" is not taken for an id.
@router.get(
    "/lorebooks/entries",
    response_model=LorebookEntriesOut,
    summary="Entries across every lorebook, one row per entry however many versions it has",
)
def list_entries(
    q: str = Query("", description="Matches title, keys and text, case-insensitively."),
    lorebook: str = Query("", description="Only this lorebook's entries."),
    changed: bool = Query(False, description="Only entries with more than one version."),
    unresolved: bool = Query(False, description="Only changed entries with no version chosen yet."),
    sort: Literal["versions", "cards", "title"] = "versions",
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> LorebookEntriesOut:
    _idx, lore = _indexes()
    needle = q.strip().casefold()
    names = {book.id: book.name for book in lore.lorebooks()}

    matched: list[lorebooks.EntryLine] = []
    for line in lore.lines():
        if lorebook and line.lorebook_id != lorebook:
            continue
        if changed and len(line.versions) < 2:
            continue
        if unresolved and line.resolved:
            continue
        if needle:
            version = lore.version(line.versions[0].hash)
            haystack = " ".join((line.title, *(version.keys if version else ()), version.content if version else ""))
            if needle not in haystack.casefold():
                continue
        matched.append(line)

    if sort == "title":
        matched.sort(key=lambda line: line.title.casefold())
    elif sort == "cards":
        matched.sort(key=lambda line: (-line.card_count, line.title.casefold()))
    else:
        matched.sort(key=lambda line: (-len(line.versions), -line.card_count, line.title.casefold()))

    return LorebookEntriesOut(
        entries=[_entry_out(lore, line, names.get(line.lorebook_id, "")) for line in matched[offset : offset + limit]],
        total=len(matched),
    )


@router.get(
    "/lorebooks/entries/{entry_id}",
    response_model=LorebookEntryDetailOut,
    summary="One entry: every version of its text, and which cards hold each",
)
def get_entry(entry_id: str) -> LorebookEntryDetailOut:
    idx, lore = _indexes()
    line = lore.line(entry_id)
    if line is None:
        raise HTTPException(status_code=404, detail=f"no lorebook entry {entry_id!r}")
    book = lore.get(line.lorebook_id)
    versions: list[LorebookEntryVersionOut] = []
    for held in line.versions:
        version = lore.version(held.hash)
        if version is None:
            continue
        versions.append(
            LorebookEntryVersionOut(
                hash=version.hash,
                title=version.title,
                keys=list(version.keys),
                secondary_keys=list(version.secondary_keys),
                constant=version.constant,
                content=version.content,
                newest=held.newest,
                cards=[_card_out(idx, filename) for filename in held.cards],
            )
        )
    return LorebookEntryDetailOut(
        id=line.id,
        lorebook_id=line.lorebook_id,
        lorebook_name=book.name if book else "",
        title=line.title,
        versions=versions,
        chosen=line.chosen,
        merges=[_merge_out(m) for m in line.merges],
        candidates=_candidates(lore, book, line) if book else [],
    )


def _require_line(lore: lorebooks.LorebookIndex, entry_id: str) -> lorebooks.EntryLine:
    line = lore.line(entry_id)
    if line is None:
        raise HTTPException(status_code=404, detail=f"no lorebook entry {entry_id!r}")
    return line


def _require_book(lore: lorebooks.LorebookIndex, lorebook_id: str) -> lorebooks.Lorebook:
    book = lore.get(lorebook_id)
    if book is None:
        raise HTTPException(status_code=404, detail=f"no lorebook {lorebook_id!r}")
    return book


@router.put(
    "/lorebooks/entries/{entry_id}/chosen",
    response_model=LorebookRefOut,
    summary="Choose the version of an entry every card should carry",
)
def choose_version(entry_id: str, body: LorebookChooseIn) -> LorebookRefOut:
    _idx, lore = _indexes()
    line = _require_line(lore, entry_id)
    hashes = [v.hash for v in line.versions]
    if body.hash not in hashes:
        raise HTTPException(status_code=422, detail="that version does not belong to this entry")
    _write(lambda: _store().choose([body.hash], clear=hashes))
    return LorebookRefOut(id=line.id)


@router.delete(
    "/lorebooks/entries/{entry_id}/chosen",
    response_model=LorebookRefOut,
    summary="Clear an entry's chosen version",
)
def clear_version(entry_id: str) -> LorebookRefOut:
    _idx, lore = _indexes()
    line = _require_line(lore, entry_id)
    _write(lambda: _store().choose([], clear=[v.hash for v in line.versions]))
    return LorebookRefOut(id=line.id)


@router.post(
    "/lorebooks/entries/{entry_id}/merge",
    response_model=LorebookRefOut,
    summary="Declare two entries of one lorebook to be versions of the same entry",
)
def merge_entries(entry_id: str, body: LorebookMergeIn) -> LorebookRefOut:
    _idx, lore = _indexes()
    line, other = _require_line(lore, entry_id), _require_line(lore, body.into)
    if line.id == other.id:
        raise HTTPException(status_code=422, detail="an entry cannot be merged with itself")
    if line.lorebook_id != other.lorebook_id:
        raise HTTPException(status_code=422, detail="entries of different lorebooks cannot be merged; merge the lorebooks first")
    anchor = line.versions[0].hash
    _write(lambda: _store().merge_entries(anchor, other.versions[0].hash))
    _idx, lore = _indexes()
    merged = next((l for l in lore.lines() if any(v.hash == anchor for v in l.versions) and l.lorebook_id == line.lorebook_id), None)
    return LorebookRefOut(id=merged.id if merged else line.id)


@router.delete(
    "/lorebooks/entries/merges/{merge_id}",
    status_code=204,
    summary="Undo an entry merge",
)
def unmerge_entries(merge_id: str) -> None:
    if not _write(lambda: _store().unmerge("entry", merge_id)):
        raise HTTPException(status_code=404, detail=f"no entry merge {merge_id!r}")


@router.post(
    "/lorebooks/{lorebook_id}/merge",
    response_model=LorebookRefOut,
    summary="Declare two lorebooks to be the same book",
)
def merge_lorebooks(lorebook_id: str, body: LorebookMergeIn) -> LorebookRefOut:
    _idx, lore = _indexes()
    book, other = _require_book(lore, lorebook_id), _require_book(lore, body.into)
    if book.id == other.id:
        raise HTTPException(status_code=422, detail="a lorebook cannot be merged with itself")
    merge = _write(lambda: _store().merge_lorebooks(other.anchor, book.anchor, other.name, book.name))
    _idx, lore = _indexes()
    merged = next((b for b in lore.lorebooks() if any(m.id == merge.id for m in b.merges)), None)
    return LorebookRefOut(id=merged.id if merged else other.id)


@router.delete(
    "/lorebooks/merges/{merge_id}",
    status_code=204,
    summary="Undo a lorebook merge",
)
def unmerge_lorebooks(merge_id: str) -> None:
    if not _write(lambda: _store().unmerge("lorebook", merge_id)):
        raise HTTPException(status_code=404, detail=f"no lorebook merge {merge_id!r}")


@router.post(
    "/lorebooks/{lorebook_id}/choose-newest",
    response_model=LorebookChooseNewestOut,
    summary="Choose the newest version of every entry that has none chosen",
)
def choose_newest(lorebook_id: str) -> LorebookChooseNewestOut:
    """"Newest" is the version on the most recently created card -- the same
    guess the pages label as one. Entries already decided are left alone."""
    _idx, lore = _indexes()
    book = _require_book(lore, lorebook_id)
    hashes = [line.versions[0].hash for line in book.lines if not line.resolved]
    if hashes:
        _write(lambda: _store().choose(hashes))
    return LorebookChooseNewestOut(chosen=len(hashes))


@router.get(
    "/lorebooks/{lorebook_id}",
    response_model=LorebookDetailOut,
    summary="One lorebook: its revisions, entries, and the lorebooks it overlaps",
)
def get_lorebook(lorebook_id: str) -> LorebookDetailOut:
    idx, lore = _indexes()
    book = lore.get(lorebook_id)
    if book is None:
        raise HTTPException(status_code=404, detail=f"no lorebook {lorebook_id!r}")

    similar: list[LorebookSimilarOut] = []
    for other in book.similar:
        target = lore.get(other.lorebook_id)
        if target is None:
            continue
        similar.append(
            LorebookSimilarOut(
                id=target.id,
                name=target.name,
                card_count=len(target.cards),
                entry_count=len(target.lines),
                shared=other.shared,
                relation=other.relation,  # type: ignore[arg-type]
            )
        )

    return LorebookDetailOut(
        **_book_fields(book),
        revisions=[
            LorebookRevisionOut(
                fingerprint=revision.fingerprint,
                entry_count=len(revision.hashes),
                newest=revision.newest,
                cards=[_card_out(idx, filename) for filename in revision.cards],
            )
            for revision in book.revisions
        ],
        # Undecided entries first, then the other changed ones -- they are
        # what a reader opens a multi-revision book to find.
        entries=[
            _entry_out(lore, line, book.name)
            for line in sorted(book.lines, key=lambda line: (line.resolved, -len(line.versions)))
        ],
        similar=similar,
        merges=[_merge_out(m) for m in book.merges],
    )


@router.get(
    "/characters/{card_id}/lorebooks",
    response_model=list[CardLorebookOut],
    summary="The lorebooks a card's embedded book was assembled from, in entry order",
)
def card_lorebooks(card_id: str) -> list[CardLorebookOut]:
    idx, lore = _indexes()
    record = _shared.require(idx, card_id)
    out: list[CardLorebookOut] = []
    for part, lorebook_id in lore.for_card(record.filename):
        book = lore.get(lorebook_id)
        if book is None:
            continue
        out.append(
            CardLorebookOut(
                lorebook_id=lorebook_id,
                name=book.name,
                kind=part.kind,
                entry_count=len(part.hashes),
                card_count=len(book.cards),
                revision=part.fingerprint,
                is_newest=book.revisions[0].fingerprint == part.fingerprint,
                revision_count=len(book.revisions),
            )
        )
    return out
