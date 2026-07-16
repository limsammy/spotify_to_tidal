import requests
from unittest.mock import Mock

import spotify_to_tidal.tidalapi_patch as patch_module
from spotify_to_tidal.tidalapi_patch import _retry_on_412


def _http_error(code):
    return requests.HTTPError(response=Mock(status_code=code))


def test_retries_on_412_then_succeeds(monkeypatch):
    monkeypatch.setattr(patch_module.time, "sleep", lambda s: None)
    playlist = Mock()
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise _http_error(412)
        return "ok"

    assert _retry_on_412(playlist, flaky) == "ok"
    assert playlist._reparse.call_count == 2


def test_non_412_propagates():
    playlist = Mock()

    def fail():
        raise _http_error(500)

    try:
        _retry_on_412(playlist, fail)
        assert False, "should have raised"
    except requests.HTTPError:
        pass
    assert playlist._reparse.call_count == 0
