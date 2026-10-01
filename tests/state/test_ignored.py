"""Discover's ignore list: the store, and the API over it.

The list is append-only and has no removal route (see
`proxy/state/ignored.py`), which makes a lost or clobbered entry unrecoverable
through the UI. So the cases that matter here are the ones where a naive
implementation drops decisions quietly: a bucket overwritten instead of merged,
a damaged file read as "nothing ignored", a hand-edit lost to a cache.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from proxy.state import ignored
from proxy.state.ignored import IgnoredError, IgnoredStore


@pytest.fixture
def store(tmp_path: Path) -> IgnoredStore:
    return IgnoredStore(tmp_path / "ignored.json")


# --------------------------------------------------------------------------
# the store
# --------------------------------------------------------------------------


def test_missing_file_reads_as_empty(store: IgnoredStore) -> None:
    """Nothing ignored yet is the normal first state, not a fault."""
    assert store.read() == {}
    assert store.ids("chub") == set()


def test_add_then_read_round_trips(store: IgnoredStore) -> None:
    added, ids = store.add("chub", ["412233", "891020"])
    assert added == 2
    assert ids == ["412233", "891020"]
    assert store.read() == {"chub": ["412233", "891020"]}


def test_add_is_idempotent(store: IgnoredStore) -> None:
    """Ignoring a card twice is a no-op, not an error -- a card can be selected
    in two different batches, and the second must not look like a failure."""
    store.add("chub", ["412233"])
    added, ids = store.add("chub", ["412233"])
    assert added == 0
    assert ids == ["412233"]


def test_add_counts_only_what_was_new(store: IgnoredStore) -> None:
    store.add("chub", ["a", "b"])
    added, ids = store.add("chub", ["b", "c"])
    assert added == 1
    assert ids == ["a", "b", "c"]


def test_add_leaves_the_other_providers_alone(store: IgnoredStore) -> None:
    """The write is a whole-file replace, so the bucket not being written has to
    be read and carried across -- the bug this guards is Chub's list vanishing
    the first time anything is ignored on DataCat."""
    store.add("chub", ["412233"])
    store.add("datacat", ["3f1a9c22-0000-4000-8000-000000000001"])
    assert store.read() == {
        "chub": ["412233"],
        "datacat": ["3f1a9c22-0000-4000-8000-000000000001"],
    }


def test_blanks_and_duplicates_are_dropped(store: IgnoredStore) -> None:
    added, ids = store.add("chub", [" 412233 ", "", "   ", "412233"])
    assert added == 1
    assert ids == ["412233"]


def test_an_overlong_id_is_refused(store: IgnoredStore) -> None:
    with pytest.raises(IgnoredError, match="over the"):
        store.add("chub", ["x" * (ignored.MAX_ID_CHARS + 1)])


def test_a_refused_batch_writes_nothing(store: IgnoredStore) -> None:
    """Validation runs over the whole batch before the file is touched, so one
    junk id in a selection does not half-apply it."""
    store.add("chub", ["good"])
    with pytest.raises(IgnoredError):
        store.add("chub", ["also-good", "x" * 500])
    assert store.read() == {"chub": ["good"]}


def test_the_per_provider_ceiling_is_enforced(
    store: IgnoredStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ignored, "MAX_IDS_PER_PROVIDER", 3)
    store.add("chub", ["a", "b", "c"])
    with pytest.raises(IgnoredError, match="over the 3-id ceiling"):
        store.add("chub", ["d"])
    assert store.read() == {"chub": ["a", "b", "c"]}


def test_damaged_json_raises_rather_than_reading_as_empty(
    store: IgnoredStore,
) -> None:
    """The difference between "nothing ignored" and "your list is damaged" is
    the difference between a first run and losing every decision in the file --
    and the caller's next add would write straight over it."""
    store.path.write_text("{not json", encoding="utf-8")
    with pytest.raises(IgnoredError, match="not valid JSON"):
        store.read()


def test_a_json_array_is_refused(store: IgnoredStore) -> None:
    store.path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(IgnoredError, match="expected a JSON object"):
        store.read()


def test_junk_rows_are_dropped_rather_than_raising(store: IgnoredStore) -> None:
    """One bad entry must not make the whole list unreadable -- a bucket with a
    null in it is still a usable list of ids, and the alternative is a file only
    fixable by hand."""
    store.path.write_text(
        json.dumps({"chub": ["412233", None, 7, "", "891020"], "junk": "nope"}),
        encoding="utf-8",
    )
    assert store.read() == {"chub": ["412233", "891020"]}


def test_a_hand_edit_is_picked_up_without_a_restart(store: IgnoredStore) -> None:
    """Reads are uncached on purpose: pasting in a list of ids, or clearing a
    bucket, is the only way to un-ignore anything."""
    store.add("chub", ["a", "b"])
    store.path.write_text(json.dumps({"chub": ["a"]}), encoding="utf-8")
    assert store.read() == {"chub": ["a"]}


def test_write_creates_the_parent_directory(tmp_path: Path) -> None:
    store = IgnoredStore(tmp_path / "nested" / "deeper" / "ignored.json")
    store.add("chub", ["412233"])
    assert store.read() == {"chub": ["412233"]}


def test_a_failed_write_leaves_the_previous_list_intact(
    store: IgnoredStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The temp-file-then-replace dance exists for this: a crash mid-write must
    not truncate a list nothing can rebuild."""
    store.add("chub", ["412233"])

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(ignored.os, "replace", boom)
    with pytest.raises(IgnoredError, match="could not write"):
        store.add("chub", ["891020"])
    assert store.read() == {"chub": ["412233"]}


def test_a_failed_write_leaves_no_temp_file_behind(
    store: IgnoredStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(ignored.os, "replace", boom)
    with pytest.raises(IgnoredError):
        store.add("chub", ["412233"])
    assert list(store.path.parent.glob(".ignored-*")) == []


def test_normalize_keeps_first_seen_order() -> None:
    assert ignored.normalize([" b ", "a", "b", ""]) == ["b", "a"]


# --------------------------------------------------------------------------
# the API
# --------------------------------------------------------------------------


def test_get_is_empty_on_a_fresh_archive(client, archive_dirs) -> None:
    resp = client.get("/api/v1/discover/ignored")
    assert resp.status_code == 200
    assert resp.json() == {"ignored": {}}


def test_post_then_get_round_trips_through_the_api(client, archive_dirs) -> None:
    post = client.post(
        "/api/v1/discover/ignored", json={"provider": "chub", "ids": ["412233", "891020"]}
    )
    assert post.status_code == 200
    assert post.json() == {
        "provider": "chub",
        "added": 2,
        "ids": ["412233", "891020"],
    }
    assert client.get("/api/v1/discover/ignored").json() == {
        "ignored": {"chub": ["412233", "891020"]}
    }


def test_post_accumulates_across_requests(client, archive_dirs) -> None:
    """Each batch adds to the list rather than replacing it -- the opposite of
    `PUT /settings`, and the reason this is POST."""
    client.post("/api/v1/discover/ignored", json={"provider": "chub", "ids": ["a"]})
    resp = client.post(
        "/api/v1/discover/ignored", json={"provider": "chub", "ids": ["b"]}
    )
    assert resp.json()["ids"] == ["a", "b"]


def test_post_keeps_the_providers_separate(client, archive_dirs) -> None:
    client.post("/api/v1/discover/ignored", json={"provider": "chub", "ids": ["a"]})
    client.post("/api/v1/discover/ignored", json={"provider": "datacat", "ids": ["a"]})
    assert client.get("/api/v1/discover/ignored").json() == {
        "ignored": {"chub": ["a"], "datacat": ["a"]}
    }


def test_an_unknown_provider_is_refused(client, archive_dirs) -> None:
    """The store takes any bucket name; the route is where the providers
    Discover actually browses are enumerated, so a typo cannot create a bucket
    nothing ever reads."""
    resp = client.post(
        "/api/v1/discover/ignored", json={"provider": "janitor", "ids": ["a"]}
    )
    assert resp.status_code == 422
    assert client.get("/api/v1/discover/ignored").json() == {"ignored": {}}


def test_too_many_ids_in_one_request_is_refused(client, archive_dirs) -> None:
    from proxy.api.v1 import discover

    ids = [str(n) for n in range(discover.MAX_IDS_PER_REQUEST + 1)]
    resp = client.post(
        "/api/v1/discover/ignored", json={"provider": "chub", "ids": ids}
    )
    assert resp.status_code == 422
    assert client.get("/api/v1/discover/ignored").json() == {"ignored": {}}


def test_an_empty_batch_is_accepted_and_writes_nothing(client, archive_dirs) -> None:
    resp = client.post("/api/v1/discover/ignored", json={"provider": "chub", "ids": []})
    assert resp.status_code == 200
    assert resp.json()["added"] == 0
    assert not archive_dirs["ignored"].exists()


def test_get_reports_a_damaged_file_rather_than_hiding_it(
    client, archive_dirs
) -> None:
    archive_dirs["ignored"].write_text("{broken", encoding="utf-8")
    resp = client.get("/api/v1/discover/ignored")
    assert resp.status_code == 500
    assert "not valid JSON" in resp.json()["detail"]


def test_an_overlong_id_is_a_400_not_a_500(client, archive_dirs) -> None:
    resp = client.post(
        "/api/v1/discover/ignored", json={"provider": "chub", "ids": ["x" * 500]}
    )
    assert resp.status_code == 400
