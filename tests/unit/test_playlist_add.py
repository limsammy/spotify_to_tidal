# tests/unit/test_playlist_add.py

import asyncio

import tidalapi

from spotify_to_tidal import sync as sync_mod


def test_add_tracks_retries_per_chunk_without_duplicates(monkeypatch):
    """A rate-limit error on one chunk retries only that chunk — earlier chunks
    are not re-added (which a whole-operation retry would have duplicated)."""
    monkeypatch.setattr(sync_mod.time, "sleep", lambda s: None)  # no real backoff

    added = []
    calls = {"n": 0}

    class FakePlaylist:
        def add(self, chunk):
            calls["n"] += 1
            # fail the first attempt at the second chunk, succeed on retry
            if list(chunk) == [3, 4] and calls["n"] == 2:
                raise tidalapi.exceptions.TooManyRequests("rate limited")
            added.append(list(chunk))

    asyncio.run(sync_mod._add_tracks_to_tidal_playlist(FakePlaylist(), [1, 2, 3, 4, 5], chunk_size=2))

    # every track added exactly once, in order — no duplicate of the [1, 2] chunk
    assert added == [[1, 2], [3, 4], [5]]
