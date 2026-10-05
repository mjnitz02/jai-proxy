"""`/api/v1/lorebooks` -- lorebooks derived from the cards that embed them.

Builds its own archive: the point of every test here is which cards share
which entries, so the fixture has to say exactly that and nothing else.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import card_png, jai_extensions


def _entry(title: str, content: str) -> dict:
    return {"comment": title, "name": title, "content": content, "keys": [title.lower()]}


def _jai_book(character: str, *sources: tuple[str, str, list[dict]]) -> dict:
    """A book as `LorebookMapper` writes it: sources concatenated, comments
    prefixed with the book title when there is more than one."""
    multi = len(sources) > 1
    entries = []
    for _sid, title, source_entries in sources:
        for entry in source_entries:
            entries.append({**entry, "comment": f"[{title}] {entry['comment']}" if multi else entry["comment"]})
    return {
        "name": f"{character} — JanitorAI lorebooks" if multi else sources[0][1],
        "extensions": {
            "jai_sources": [{"id": sid, "title": title, "entry_count": len(es)} for sid, title, es in sources]
        },
        "entries": entries,
    }


WORLD_V1 = [_entry("Town", "A small town."), _entry("River", "A river.")]
WORLD_V2 = [_entry("Town", "A small town, now with a market."), _entry("River", "A river.")]
PEOPLE = [_entry("Mayor", "The mayor.")]


@pytest.fixture
def client(archive_dirs: dict[str, Path]):
    from fastapi.testclient import TestClient

    from proxy.server import app

    def write(filename: str, name: str, card_id: str, book: dict | None, date: str) -> None:
        fields = {"character_book": book} if book else {}
        (archive_dirs["characters"] / filename).write_bytes(
            card_png(
                name,
                extensions=jai_extensions(card_id, gallery_id=card_id[:12], creator_name="worldsmith"),
                envelope_extra={"create_date": date},
                **fields,
            )
        )

    # Two cards on the old World, one on the new; Cleo also attaches People.
    write("Abbie_aaaaaaaa.png", "Abbie", "aaaaaaaa-0000", _jai_book("Abbie", ("w", "World", WORLD_V1)), "2026-01-01T00:00:00Z")
    write("Bea_bbbbbbbb.png", "Bea", "bbbbbbbb-0000", _jai_book("Bea", ("w", "World", WORLD_V1)), "2026-02-01T00:00:00Z")
    write(
        "Cleo_cccccccc.png",
        "Cleo",
        "cccccccc-0000",
        _jai_book("Cleo", ("w", "World", WORLD_V2), ("p", "People", PEOPLE)),
        "2026-03-01T00:00:00Z",
    )
    # No provider id at all, but the same entries as People -- the same book.
    write("Dana_dddddddd.png", "Dana", "dddddddd-0000", {"name": "Dana Lorebook", "entries": PEOPLE}, "2026-04-01T00:00:00Z")
    write("Eve_eeeeeeee.png", "Eve", "eeeeeeee-0000", None, "2026-05-01T00:00:00Z")

    with TestClient(app) as test_client:
        yield test_client


def _by_name(client) -> dict[str, dict]:
    return {book["name"]: book for book in client.get("/api/v1/lorebooks").json()["lorebooks"]}


def test_books_are_deduplicated_across_cards(client):
    body = client.get("/api/v1/lorebooks").json()
    books = {book["name"]: book for book in body["lorebooks"]}
    assert set(books) == {"World", "People"}
    assert books["World"]["card_count"] == 3
    assert books["World"]["refs"] == ["jai:w"]
    # Dana's id-less copy joined People on content alone.
    assert books["People"]["card_count"] == 2
    assert books["People"]["kinds"] == ["embedded", "janitor"]
    assert body["stats"] == {
        "cards": 4,
        "lorebooks": 2,
        "shared_lorebooks": 2,
        "entries_embedded": 8,
        "entries_unique": 4,
        "changed_entries": 1,
        "unresolved_entries": 1,
        "pending_cards": 0,
    }


def test_revisions_newest_first_and_changed_entries_flagged(client):
    world = _by_name(client)["World"]
    assert (world["revision_count"], world["entry_count"], world["changed_entries"]) == (2, 2, 1)

    detail = client.get(f"/api/v1/lorebooks/{world['id']}").json()
    assert [[c["name"] for c in r["cards"]] for r in detail["revisions"]] == [["Cleo"], ["Abbie", "Bea"]]
    # The changed entry leads, and previews its newest text.
    town = detail["entries"][0]
    assert (town["title"], town["version_count"], town["card_count"]) == ("Town", 2, 3)
    assert "market" in town["preview"]


def test_entry_detail_lists_every_version_with_its_cards(client):
    world = _by_name(client)["World"]
    entries = client.get("/api/v1/lorebooks/entries", params={"changed": True}).json()
    assert entries["total"] == 1
    entry = client.get(f"/api/v1/lorebooks/entries/{entries['entries'][0]['id']}").json()
    assert entry["lorebook_id"] == world["id"]
    assert [(v["content"], [c["name"] for c in v["cards"]]) for v in entry["versions"]] == [
        ("A small town, now with a market.", ["Cleo"]),
        ("A small town.", ["Abbie", "Bea"]),
    ]


def test_entries_filter_search_and_page(client):
    everything = client.get("/api/v1/lorebooks/entries").json()
    assert everything["total"] == 3
    people = _by_name(client)["People"]
    scoped = client.get("/api/v1/lorebooks/entries", params={"lorebook": people["id"]}).json()
    assert [e["title"] for e in scoped["entries"]] == ["Mayor"]
    assert client.get("/api/v1/lorebooks/entries", params={"q": "MARKET"}).json()["total"] == 1
    paged = client.get("/api/v1/lorebooks/entries", params={"limit": 1, "offset": 1, "sort": "title"}).json()
    assert [e["title"] for e in paged["entries"]] == ["River"] and paged["total"] == 3


def test_card_lorebooks_in_entry_order_with_staleness(client):
    cleo = client.get("/api/v1/characters/Cleo_cccccccc.png/lorebooks").json()
    assert [(b["name"], b["entry_count"], b["is_newest"]) for b in cleo] == [("World", 2, True), ("People", 1, True)]
    abbie = client.get("/api/v1/characters/Abbie_aaaaaaaa.png/lorebooks").json()
    assert [(b["name"], b["is_newest"], b["revision_count"]) for b in abbie] == [("World", False, 2)]
    assert client.get("/api/v1/characters/Eve_eeeeeeee.png/lorebooks").json() == []


def test_unknown_ids_are_404(client):
    assert client.get("/api/v1/lorebooks/nope").status_code == 404
    assert client.get("/api/v1/lorebooks/entries/nope").status_code == 404
    assert client.get("/api/v1/characters/Nobody.png/lorebooks").status_code == 404


def test_overlapping_books_are_offered_as_similar(client, archive_dirs):
    # A bigger id-less book that contains all of World's newest entries.
    extra = [*WORLD_V2, _entry("Castle", "A castle."), _entry("Forest", "A forest.")]
    (archive_dirs["characters"] / "Fay_ffffffff.png").write_bytes(
        card_png(
            "Fay",
            extensions=jai_extensions("ffffffff-0000", gallery_id="ffffffff0000"),
            character_book={"name": "World (expanded)", "entries": extra},
        )
    )
    from proxy.api.v1 import _shared

    _shared.index().refresh(force=True)
    books = _by_name(client)
    assert books["World (expanded)"]["similar_count"] == 1
    detail = client.get(f"/api/v1/lorebooks/{books['World (expanded)']['id']}").json()
    assert [(s["name"], s["shared"], s["relation"]) for s in detail["similar"]] == [("World", 2, "overlap")]


# --- decisions ---------------------------------------------------------------


def _town(client) -> dict:
    listed = client.get("/api/v1/lorebooks/entries", params={"unresolved": True}).json()["entries"]
    return client.get(f"/api/v1/lorebooks/entries/{listed[0]['id']}").json()


def test_choosing_a_version_resolves_the_entry_and_counts_pending_cards(client, archive_dirs):
    town = _town(client)
    old = town["versions"][1]
    assert town["chosen"] == ""

    assert client.put(f"/api/v1/lorebooks/entries/{town['id']}/chosen", json={"hash": old["hash"]}).status_code == 200
    after = client.get(f"/api/v1/lorebooks/entries/{town['id']}").json()
    assert after["chosen"] == old["hash"]
    world = _by_name(client)["World"]
    # Cleo holds the other version, so she is what a sync would rewrite.
    assert (world["unresolved_entries"], world["pending_cards"]) == (0, 1)
    assert client.get("/api/v1/lorebooks/entries", params={"unresolved": True}).json()["total"] == 0
    # The list now previews the chosen text, not the newest.
    row = client.get("/api/v1/lorebooks/entries", params={"changed": True}).json()["entries"][0]
    assert "market" not in row["preview"] and row["resolved"] and row["pending_cards"] == 1

    # Choosing again replaces the choice rather than adding a second.
    new = town["versions"][0]
    client.put(f"/api/v1/lorebooks/entries/{town['id']}/chosen", json={"hash": new["hash"]})
    assert _by_name(client)["World"]["pending_cards"] == 2

    assert client.delete(f"/api/v1/lorebooks/entries/{town['id']}/chosen").status_code == 200
    assert _by_name(client)["World"]["unresolved_entries"] == 1
    # No card was touched by any of it.
    assert archive_dirs["lorebook_decisions"].is_file()


def test_choosing_a_foreign_version_is_refused(client):
    town = _town(client)
    response = client.put(f"/api/v1/lorebooks/entries/{town['id']}/chosen", json={"hash": "not-a-version"})
    assert response.status_code == 422


def test_choose_newest_decides_only_the_undecided(client):
    world = _by_name(client)["World"]
    assert client.post(f"/api/v1/lorebooks/{world['id']}/choose-newest").json() == {"chosen": 1}
    town = client.get("/api/v1/lorebooks/entries", params={"changed": True}).json()["entries"][0]
    assert "market" in town["preview"] and town["pending_cards"] == 2
    assert client.post(f"/api/v1/lorebooks/{world['id']}/choose-newest").json() == {"chosen": 0}


def _add_retitled_world(archive_dirs) -> None:
    """An id-less copy of World where Town was retitled and reworded -- by title
    a different entry, and by content a different book."""
    entries = [_entry("The Town", "A small town, now with a market and a mill."), _entry("River", "A river.")]
    (archive_dirs["characters"] / "Gia_99999999.png").write_bytes(
        card_png(
            "Gia",
            extensions=jai_extensions("99999999-0000", gallery_id="999999990000"),
            envelope_extra={"create_date": "2026-06-01T00:00:00Z"},
            character_book={"name": "World (old export)", "entries": entries},
        )
    )
    from proxy.api.v1 import _shared

    _shared.index().refresh(force=True)


def test_merging_lorebooks_then_entries_and_undoing_both(client, archive_dirs):
    _add_retitled_world(archive_dirs)
    books = _by_name(client)
    world, stray = books["World"], books["World (old export)"]

    merged_id = client.post(f"/api/v1/lorebooks/{stray['id']}/merge", json={"into": world["id"]}).json()["id"]
    # The provider-identified book keeps its id and absorbs the stray's card.
    assert merged_id == world["id"]
    merged = client.get(f"/api/v1/lorebooks/{merged_id}").json()
    assert (merged["card_count"], merged["revision_count"]) == (4, 3)
    assert [(m["a_name"], m["b_name"]) for m in merged["merges"]] == [("World", "World (old export)")]
    assert "World (old export)" not in _by_name(client)

    # "The Town" arrived as its own entry; it is offered as a candidate for Town.
    entries = {e["title"]: e for e in merged["entries"]}
    assert set(entries) == {"Town", "The Town", "River"}
    town = client.get(f"/api/v1/lorebooks/entries/{entries['Town']['id']}").json()
    assert [c["title"] for c in town["candidates"]] == ["The Town"]
    # River is on every card Town is on, so it is never a candidate.

    line_id = client.post(
        f"/api/v1/lorebooks/entries/{entries['The Town']['id']}/merge", json={"into": entries["Town"]["id"]}
    ).json()["id"]
    line = client.get(f"/api/v1/lorebooks/entries/{line_id}").json()
    assert len(line["versions"]) == 3 and len(line["merges"]) == 1
    assert client.get(f"/api/v1/lorebooks/{merged_id}").json()["entry_count"] == 2

    assert client.delete(f"/api/v1/lorebooks/entries/merges/{line['merges'][0]['id']}").status_code == 204
    assert client.get(f"/api/v1/lorebooks/{merged_id}").json()["entry_count"] == 3
    assert client.delete(f"/api/v1/lorebooks/merges/{merged['merges'][0]['id']}").status_code == 204
    assert _by_name(client)["World"]["card_count"] == 3
    assert client.delete(f"/api/v1/lorebooks/merges/{merged['merges'][0]['id']}").status_code == 404


def test_merges_are_refused_across_lorebooks_and_with_self(client):
    books = _by_name(client)
    world = books["World"]
    assert client.post(f"/api/v1/lorebooks/{world['id']}/merge", json={"into": world["id"]}).status_code == 422
    assert client.post(f"/api/v1/lorebooks/{world['id']}/merge", json={"into": "nope"}).status_code == 404
    town = _town(client)
    mayor = client.get("/api/v1/lorebooks/entries", params={"lorebook": books["People"]["id"]}).json()["entries"][0]
    assert client.post(f"/api/v1/lorebooks/entries/{town['id']}/merge", json={"into": mayor["id"]}).status_code == 422


def test_a_damaged_decisions_file_is_reported_not_overwritten(client, archive_dirs):
    archive_dirs["lorebook_decisions"].write_text("{not json")
    assert client.get("/api/v1/lorebooks").status_code == 500
    assert archive_dirs["lorebook_decisions"].read_text() == "{not json"
