# tests/unit/test_playlist_add.py

import asyncio

import tidalapi

from spotify_to_tidal import sync as sync_mod
from spotify_to_tidal.tidalapi_patch import clear_tidal_playlist


def test_add_tracks_retries_per_chunk_without_duplicates(monkeypatch):
    """A rate-limit error on one chunk retries only that chunk — earlier chunks
    are not re-added (which a whole-operation retry would have duplicated)."""
    monkeypatch.setattr(sync_mod.time, "sleep", lambda s: None)  # no real backoff

    added = []
    calls = {"n": 0}

    class FakePlaylist:
        def __init__(self):
            self.reparsed_before_first_add = None
        def _reparse(self):
            # records whether the ETag was refreshed before any add happened
            self.reparsed_before_first_add = (len(added) == 0)
        def add(self, chunk):
            calls["n"] += 1
            # fail the first attempt at the second chunk, succeed on retry
            if list(chunk) == [3, 4] and calls["n"] == 2:
                raise tidalapi.exceptions.TooManyRequests("rate limited")
            added.append(list(chunk))

    pl = FakePlaylist()
    asyncio.run(sync_mod._add_tracks_to_tidal_playlist(pl, [1, 2, 3, 4, 5], chunk_size=2))

    # ETag refreshed before the first add (avoids the 412 on the add path)
    assert pl.reparsed_before_first_add is True
    # every track added exactly once, in order — no duplicate of the [1, 2] chunk
    assert added == [[1, 2], [3, 4], [5]]


def test_clear_tidal_playlist_refreshes_etag_before_first_delete():
    """The custom chunk fetcher doesn't set _etag, so clear must _reparse() to get a fresh ETag
    before the first DELETE — otherwise Tidal returns 412 Precondition Failed."""
    events = []

    class FakeRequest:
        def __init__(self, pl):
            self.pl = pl

        def request(self, method, url, headers=None):
            events.append((method, dict(headers) if headers else None))
            self.pl._pending = 0  # the DELETE cleared the chunk

    class FakePlaylist:
        _base_url = "playlists/%s"

        def __init__(self):
            self.id = "p1"
            self._etag = None      # bug condition: chunk fetcher never populated the ETag
            self.num_tracks = 13
            self._pending = 13
            self.request = FakeRequest(self)

        def _reparse(self):
            events.append(("reparse", self._etag))
            self._etag = "fresh-etag"
            self.num_tracks = self._pending

    clear_tidal_playlist(FakePlaylist(), chunk_size=20)

    assert events[0] == ("reparse", None)  # refreshed the ETag before anything else
    deletes = [e for e in events if e[0] == "DELETE"]
    assert deletes and deletes[0][1] == {"If-None-Match": "fresh-etag"}  # delete used the fresh ETag
