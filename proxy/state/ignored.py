"""Provider cards marked "don't want", persisted at `data/ignored.json`.

WHY THIS EXISTS
Discover's "Hide cards I have" filters the grid against the archive's own
`_<id8>` fragment set, which answers one question: do I own this? Browsing a
provider raises a second one it could not answer -- *have I already decided
against this?* Without somewhere to put that decision, the same unwanted cards
come back on every pass through a feed, and the only way to make one stop
appearing is to acquire it.

So: a second list of ids per provider, with exactly the semantics of the first
one. An ignored id is not a claim that anything is on disk -- nothing is -- it
is a claim that the answer is already no. Discover concatenates the two sets at
its single filter site, which is why "ignore" needs no filter of its own: as far
as browsing is concerned these behave like cards you already own.

WHAT THIS MODULE KNOWS
That ids are strings and providers are buckets of them. Nothing about what a
provider id *means* -- Chub's are short integers, DataCat's are uuids, and
neither is parsed here. The bucket names are not validated either, so a third
provider's rows survive a read by a build that has never heard of it; the
route's `Literal` is where the known providers are enumerated, the same division
`providerExcludeTags` already uses on the client.

The full provider id is stored, not the `_<id8>` fragment the archive files
cards under. The fragment exists because a filename has to carry identity;
here there is no file, we hold the provider's own id already, and matching it
whole avoids ever asking whether two ids that share eight characters are the
same card.

APPEND-ONLY, DELIBERATELY
There is no removal path, because the feature does not need one. Turning
"Hide cards I have" off shows every ignored card again, and acquiring one makes
it a card you have -- at which point its entry here is inert, since both sets
feed the same filter. A card is therefore never unreachable, and the one thing
an un-ignore would buy is shrinking this file.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger("jai_proxy.state.ignored")

# A ceiling on what will be read back, guarding against a damaged or runaway
# file rather than against an attacker -- the server is local. Generous next to
# `ui_settings.MAX_BYTES` because this is the one store whose whole job is to
# grow: 50k DataCat uuids is roughly 2 MB of JSON.
MAX_BYTES = 8 * 1024 * 1024

# Per-provider ceiling, so a client bug that ignores in a loop fails loudly at a
# known size instead of quietly growing the file until it stops loading.
MAX_IDS_PER_PROVIDER = 50_000

# A single provider id's length. Chub's are ~6 digits and DataCat's are 36-char
# uuids; this is slack, not a guess at a format.
MAX_ID_CHARS = 128


class IgnoredError(Exception):
    """The stored list could not be read, or the given ids are unusable."""


def normalize(ids: list[str]) -> list[str]:
    """Trim, drop blanks, drop duplicates, keep first-seen order.

    Raises on an id too long to be one. Order is kept rather than sorted so a
    caller's error message can name the id it rejected in the position the
    caller sent it.
    """
    seen: set[str] = set()
    out: list[str] = []
    for raw in ids:
        value = raw.strip()
        if not value:
            continue
        if len(value) > MAX_ID_CHARS:
            raise IgnoredError(
                f"id is {len(value)} characters, over the {MAX_ID_CHARS}-character ceiling"
            )
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


class IgnoredStore:
    """Read/append access to one JSON object of `{provider: [id, ...]}`.

    Reads are not cached, for `ui_settings.SettingsStore`'s reason: the file is
    read on page load rather than per request, and hand-editing it -- pasting in
    a list of ids, or clearing one provider's bucket -- is a reasonable thing to
    do that a cache would hide until a restart.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self) -> dict[str, list[str]]:
        """Every bucket, each a sorted list. `{}` when nothing is ignored yet.

        A missing file is normal and reads as empty. A file that exists but does
        not parse raises instead: unlike settings this holds no credentials, but
        degrading to `{}` would make a damaged file look like "you have ignored
        nothing", and the next ignore would write a fresh list straight over
        however many decisions were in there.

        Rows that are not strings are dropped rather than raising -- a bucket
        with one junk entry is still a usable list of ids, and the alternative
        is a file that can only be fixed by hand.
        """
        if not self.path.is_file():
            return {}
        try:
            raw = self.path.read_bytes()
        except OSError as exc:
            raise IgnoredError(f"could not read {self.path}: {exc}") from exc
        if len(raw) > MAX_BYTES:
            raise IgnoredError(
                f"{self.path} is {len(raw)} bytes, over the {MAX_BYTES}-byte ceiling"
            )
        try:
            blob = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IgnoredError(f"{self.path} is not valid JSON: {exc}") from exc
        if not isinstance(blob, dict):
            raise IgnoredError(
                f"{self.path} holds a {type(blob).__name__}, expected a JSON object"
            )
        return {
            provider: sorted({v for v in values if isinstance(v, str) and v.strip()})
            for provider, values in blob.items()
            if isinstance(provider, str) and isinstance(values, list)
        }

    def ids(self, provider: str) -> set[str]:
        """One provider's bucket, for a membership test."""
        return set(self.read().get(provider, ()))

    def add(self, provider: str, ids: list[str]) -> tuple[int, list[str]]:
        """Add ids to one bucket. Returns `(newly added, the bucket after)`.

        Idempotent: ignoring a card twice is not an error, and the count says
        how many of the given ids were not already there. The other buckets are
        read and written back untouched, so this is safe against a hand-edit to
        a provider the caller is not touching.
        """
        wanted = normalize(ids)
        blob = self.read()
        current = blob.get(provider, [])
        merged = set(current)
        added = [value for value in wanted if value not in merged]
        merged.update(added)
        if len(merged) > MAX_IDS_PER_PROVIDER:
            raise IgnoredError(
                f"{provider} would hold {len(merged)} ids, over the "
                f"{MAX_IDS_PER_PROVIDER}-id ceiling"
            )
        if not added:
            return 0, sorted(merged)
        blob[provider] = sorted(merged)
        self._write(blob)
        logger.info("ignored: +%d on %s (%d total)", len(added), provider, len(merged))
        return len(added), blob[provider]

    def _write(self, blob: dict[str, Any]) -> None:
        """Replace the file atomically.

        The same temp-file-then-`os.replace` dance `ui_settings.SettingsStore`
        does, kept local rather than shared with it: that module's write path is
        the only copy of the Chub and DataCat tokens, and refactoring it for a
        second caller is a risk this feature has no reason to take.
        """
        try:
            text = json.dumps(blob, indent=2, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise IgnoredError(f"ignored ids are not JSON-serialisable: {exc}") from exc
        encoded = text.encode("utf-8")
        if len(encoded) > MAX_BYTES:
            raise IgnoredError(
                f"ignored ids are {len(encoded)} bytes, over the {MAX_BYTES}-byte ceiling"
            )

        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_name = tempfile.mkstemp(
            dir=self.path.parent, prefix=".ignored-", suffix=".tmp"
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(tmp_fd, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, self.path)
        except OSError as exc:
            tmp_path.unlink(missing_ok=True)
            raise IgnoredError(f"could not write {self.path}: {exc}") from exc
        logger.debug("ignored ids written to %s (%d bytes)", self.path, len(encoded))
