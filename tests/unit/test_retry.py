# tests/unit/test_retry.py

import asyncio
import pytest
import requests
from spotify_to_tidal import sync as sync_mod


class _Resp:
    def __init__(self, headers):
        self.headers = headers
        self.text = "rate limited"


def _failing_then_ok(exc):
    """Return an async function that raises `exc` on its first call, then succeeds."""
    state = {"calls": 0}

    async def fn():
        state["calls"] += 1
        if state["calls"] == 1:
            raise exc
        return "ok"

    return fn, state


def test_repeat_on_request_error_honors_retry_after(monkeypatch):
    slept = []
    monkeypatch.setattr(sync_mod.time, "sleep", lambda s: slept.append(s))

    exc = requests.exceptions.RequestException(response=_Resp({"Retry-After": "7"}))
    fn, state = _failing_then_ok(exc)

    result = asyncio.run(sync_mod.repeat_on_request_error(fn))

    assert result == "ok"
    assert state["calls"] == 2
    assert slept == [7]  # waited exactly as the header instructed


def test_repeat_on_request_error_falls_back_to_schedule(monkeypatch):
    slept = []
    monkeypatch.setattr(sync_mod.time, "sleep", lambda s: slept.append(s))

    exc = requests.exceptions.RequestException(response=_Resp({}))  # no Retry-After header
    fn, state = _failing_then_ok(exc)

    result = asyncio.run(sync_mod.repeat_on_request_error(fn))

    assert result == "ok"
    assert slept == [1]  # first retry in the fixed backoff schedule


def test_repeat_on_request_error_does_not_retry_non_transient_4xx(monkeypatch):
    slept = []
    monkeypatch.setattr(sync_mod.time, "sleep", lambda s: slept.append(s))

    class _Resp412:
        status_code = 412
        headers = {}
        text = "precondition failed"

    exc = requests.exceptions.HTTPError(response=_Resp412())
    calls = {"n": 0}

    async def fn():
        calls["n"] += 1
        raise exc

    # a 412 precondition failure won't recover by retrying -> re-raise immediately, no backoff
    with pytest.raises(requests.exceptions.HTTPError):
        asyncio.run(sync_mod.repeat_on_request_error(fn))

    assert calls["n"] == 1
    assert slept == []
