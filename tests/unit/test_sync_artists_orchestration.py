# tests/unit/test_sync_artists_orchestration.py
#
# Orchestration-level tests for the followed-artist sync flow. The existing
# test_artist_sync.py covers artist_match and the match cache in isolation;
# these exercise the sync_artists / search_new_artists_on_tidal paths end to
# end (fetch pagination, found / not-found, partial failure, add failure,
# search error, wrapper). Test cases adapted from PR #138 (blackpr) to this
# branch's function/module names and architecture.

import asyncio
from unittest import mock

import pytest

from spotify_to_tidal import sync as sync_mod
from spotify_to_tidal.cache import artist_match_cache


class DummyTidalArtist:
    def __init__(self, artist_id, name):
        self.id = artist_id
        self.name = name


@pytest.fixture(autouse=True)
def _reset_global_state():
    """Each test gets a clean match cache and not-found log."""
    artist_match_cache.data = {}
    sync_mod.clear_not_found_log()
    yield
    artist_match_cache.data = {}
    sync_mod.clear_not_found_log()


def _followed_page(items, after=None, has_next=False):
    return {
        "artists": {
            "items": items,
            "next": "https://api.spotify.com/next" if has_next else None,
            "cursors": {"after": after},
        }
    }


def _config():
    return {"max_concurrency": 10, "rate_limit": 10}


# --------------------------------------------------------------------------
# Fetching followed artists from Spotify (cursor pagination)
# --------------------------------------------------------------------------

def _run_sync_capturing_fetched(mocker, spotify_session):
    """Run sync_artists with downstream stubbed out, returning the spotify
    artists that reached search_new_artists_on_tidal."""
    captured = {"artists": None}

    def _capture_search(tidal_session, spotify_artists, config):
        captured["artists"] = list(spotify_artists)

    mocker.patch.object(sync_mod, "get_all_saved_artists", return_value=[])
    mocker.patch.object(sync_mod, "search_new_artists_on_tidal", side_effect=_capture_search)
    mocker.patch.object(sync_mod, "add_artist_to_tidal_collection")
    mocker.patch.object(sync_mod, "tqdm", side_effect=lambda x, **kwargs: x)

    tidal_session = mock.MagicMock()
    asyncio.run(sync_mod.sync_artists(spotify_session, tidal_session, _config()))
    return captured["artists"]


def test_get_followed_artists_single_page(mocker):
    spotify_session = mock.MagicMock()
    spotify_session.current_user_followed_artists.return_value = _followed_page(
        [{"id": "a1", "name": "Artist One"}, {"id": "a2", "name": "Artist Two"}]
    )

    fetched = _run_sync_capturing_fetched(mocker, spotify_session)

    assert [a["name"] for a in fetched] == ["Artist One", "Artist Two"]
    spotify_session.current_user_followed_artists.assert_called_once_with(limit=50)


def test_get_followed_artists_multiple_pages(mocker):
    spotify_session = mock.MagicMock()
    spotify_session.current_user_followed_artists.side_effect = [
        _followed_page(
            [{"id": "a1", "name": "Artist One"}, {"id": "a2", "name": "Artist Two"}],
            after="xyz",
            has_next=True,
        ),
        _followed_page([{"id": "a3", "name": "Artist Three"}]),
    ]

    fetched = _run_sync_capturing_fetched(mocker, spotify_session)

    assert [a["id"] for a in fetched] == ["a1", "a2", "a3"]
    assert spotify_session.current_user_followed_artists.call_count == 2
    # second page is requested with the cursor returned by the first
    assert spotify_session.current_user_followed_artists.call_args_list[1] == mock.call(limit=50, after="xyz")


def test_get_followed_artists_empty(mocker):
    spotify_session = mock.MagicMock()
    spotify_session.current_user_followed_artists.return_value = _followed_page([])

    mocker.patch.object(sync_mod, "get_all_saved_artists", return_value=[])
    mocker.patch.object(sync_mod, "search_new_artists_on_tidal")
    mocker.patch.object(sync_mod, "tqdm", side_effect=lambda x, **kwargs: x)
    add_mock = mocker.patch.object(sync_mod, "add_artist_to_tidal_collection")

    tidal_session = mock.MagicMock()
    asyncio.run(sync_mod.sync_artists(spotify_session, tidal_session, _config()))

    add_mock.assert_not_called()


# --------------------------------------------------------------------------
# Searching for artists on Tidal (found / not found / search error)
# --------------------------------------------------------------------------

def test_search_new_artists_found():
    tidal_session = mock.MagicMock()
    tidal_session.search.return_value = {"artists": [DummyTidalArtist(101, "Artist One")]}

    spotify_artists = [{"id": "sp1", "name": "Artist One"}]
    asyncio.run(sync_mod.search_new_artists_on_tidal(tidal_session, spotify_artists, _config()))

    assert artist_match_cache.get("sp1") == 101


def test_search_new_artists_not_found():
    tidal_session = mock.MagicMock()
    tidal_session.search.return_value = {"artists": []}

    spotify_artists = [{"id": "sp1", "name": "Nonexistent Artist"}]
    asyncio.run(sync_mod.search_new_artists_on_tidal(tidal_session, spotify_artists, _config()))

    assert artist_match_cache.get("sp1") is None
    assert any(item["type"] == "artist" and "Nonexistent Artist" in item["info"]
               for item in sync_mod._not_found_items)


def test_search_new_artists_search_error_is_handled():
    tidal_session = mock.MagicMock()
    tidal_session.search.side_effect = Exception("Search Error")

    spotify_artists = [{"id": "sp1", "name": "Artist One"}]
    # Non-retryable errors inside the search are swallowed -> treated as not found, no crash
    asyncio.run(sync_mod.search_new_artists_on_tidal(tidal_session, spotify_artists, _config()))

    assert artist_match_cache.get("sp1") is None


# --------------------------------------------------------------------------
# Full sync_artists orchestration
# --------------------------------------------------------------------------

def _patch_sync_artists(mocker, found_map, existing_tidal=None):
    """Stub get_all_saved_artists + search so that artists in found_map get a
    cache entry (spotify_id -> tidal_id) as if found on Tidal."""
    mocker.patch.object(sync_mod, "get_all_saved_artists", return_value=existing_tidal or [])

    def _search(tidal_session, spotify_artists, config):
        for artist in spotify_artists:
            if artist["id"] in found_map:
                artist_match_cache.insert((artist["id"], found_map[artist["id"]]))

    mocker.patch.object(sync_mod, "search_new_artists_on_tidal", side_effect=_search)
    mocker.patch.object(sync_mod, "tqdm", side_effect=lambda x, **kwargs: x)


def test_sync_artists_success(mocker):
    spotify_session = mock.MagicMock()
    spotify_session.current_user_followed_artists.return_value = _followed_page(
        [{"id": "sp1", "name": "Artist One"}, {"id": "sp2", "name": "Artist Two"}]
    )
    _patch_sync_artists(mocker, found_map={"sp1": 101, "sp2": 202})

    tidal_session = mock.MagicMock()
    asyncio.run(sync_mod.sync_artists(spotify_session, tidal_session, _config()))

    assert tidal_session.user.favorites.add_artist.call_count == 2
    assert {c.args[0] for c in tidal_session.user.favorites.add_artist.call_args_list} == {101, 202}


def test_sync_artists_partial_failure(mocker):
    spotify_session = mock.MagicMock()
    spotify_session.current_user_followed_artists.return_value = _followed_page(
        [{"id": "sp1", "name": "Artist One"}, {"id": "sp2", "name": "Nonexistent Artist"}]
    )
    # only sp1 is found on Tidal
    _patch_sync_artists(mocker, found_map={"sp1": 101})

    tidal_session = mock.MagicMock()
    asyncio.run(sync_mod.sync_artists(spotify_session, tidal_session, _config()))

    tidal_session.user.favorites.add_artist.assert_called_once_with(101)


def test_sync_artists_skips_already_followed(mocker):
    spotify_session = mock.MagicMock()
    spotify_session.current_user_followed_artists.return_value = _followed_page(
        [{"id": "sp1", "name": "Artist One"}]
    )
    # found on Tidal as id 101, but already in the user's Tidal favorites
    _patch_sync_artists(mocker, found_map={"sp1": 101}, existing_tidal=[DummyTidalArtist(101, "Artist One")])

    tidal_session = mock.MagicMock()
    asyncio.run(sync_mod.sync_artists(spotify_session, tidal_session, _config()))

    tidal_session.user.favorites.add_artist.assert_not_called()


def test_sync_artists_add_failure_propagates(mocker):
    # NOTE: documents current behaviour — sync_artists does NOT wrap
    # add_artist_to_tidal_collection in repeat_on_request_error, so an error
    # while following an artist aborts the run rather than being retried/logged.
    spotify_session = mock.MagicMock()
    spotify_session.current_user_followed_artists.return_value = _followed_page(
        [{"id": "sp1", "name": "Artist One"}]
    )
    _patch_sync_artists(mocker, found_map={"sp1": 101})

    tidal_session = mock.MagicMock()
    tidal_session.user.favorites.add_artist.side_effect = Exception("API Error")

    with pytest.raises(Exception, match="API Error"):
        asyncio.run(sync_mod.sync_artists(spotify_session, tidal_session, _config()))
    tidal_session.user.favorites.add_artist.assert_called_once_with(101)


def test_sync_artists_wrapper(mocker):
    mock_sync = mocker.patch.object(sync_mod, "sync_artists")

    sync_mod.sync_artists_wrapper(mock.MagicMock(), mock.MagicMock(), _config())

    mock_sync.assert_called_once()
