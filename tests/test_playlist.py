"""Tests for the controller-level ``playlist`` dispatcher and its
startup validation in ``devices.validate_config``.
"""

import datetime
from typing import Any, Dict, List, Optional, Tuple

import pytest

from rpimedia import controller as controller_mod
from rpimedia import devices


class FakeDevice(devices.Device):
    """Records every dispatch so tests can assert what was played.

    ``supported_methods`` is configurable per test so we can verify the
    supported_methods gate is re-applied to the chosen submethod.
    """

    def __init__(self, supported_methods: frozenset[str]) -> None:
        self.supported_methods = supported_methods
        self.calls: List[Tuple[str, str]] = []

    async def play_youtube(self, video_id: str) -> None:
        self.calls.append(("youtube", video_id))
        return None

    async def play_netflix(self, netflix_id: str) -> None:
        self.calls.append(("netflix", netflix_id))
        return None

    async def play_prime_video(self, gti: str) -> None:
        self.calls.append(("prime_video", gti))
        return None

    async def play_globoplay(self, slug: str) -> None:
        self.calls.append(("globoplay", slug))
        return None


def _make_controller(device: FakeDevice) -> controller_mod.Controller:
    return controller_mod.Controller(config={}, device=device)


def _freeze_now(
    monkeypatch: pytest.MonkeyPatch, dt: datetime.datetime
) -> None:
    class _FrozenDatetime(datetime.datetime):
        @classmethod
        def now(cls, tz: Optional[datetime.tzinfo] = None) -> datetime.datetime:
            return dt

    monkeypatch.setattr(controller_mod.datetime, "datetime", _FrozenDatetime)


ALL_SUBMETHODS = frozenset(
    {"youtube", "netflix", "prime_video", "globoplay"}
)


# --- _daily_index --------------------------------------------------------


def test_daily_index_matches_day_of_year_before_noon() -> None:
    # Jan 1, 09:00 -> tm_yday 1, hour <= 12, no bump
    dt = datetime.datetime(2026, 1, 1, 9, 0)
    assert controller_mod._daily_index(dt) == 1


def test_daily_index_bumps_after_noon() -> None:
    # Jan 1, 18:00 -> tm_yday 1 + 1 (afternoon bump) = 2
    dt = datetime.datetime(2026, 1, 1, 18, 0)
    assert controller_mod._daily_index(dt) == 2


# --- daily pick + dispatch ----------------------------------------------


@pytest.mark.parametrize(
    "dt, expected",
    [
        # sorted params (see below) -> index % 4 selects deterministically.
        # tm_yday for these dates makes the math easy to follow.
        (datetime.datetime(2026, 1, 1, 9, 0), 1),   # idx 1 % 4 -> 1
        (datetime.datetime(2026, 1, 1, 18, 0), 2),  # idx 2 % 4 -> 2
        (datetime.datetime(2026, 1, 2, 9, 0), 2),   # idx 2 % 4 -> 2
        (datetime.datetime(2026, 1, 3, 9, 0), 3),   # idx 3 % 4 -> 3
        (datetime.datetime(2026, 1, 4, 9, 0), 0),   # idx 4 % 4 -> 0
    ],
)
async def test_playlist_picks_expected_item_for_day(
    monkeypatch: pytest.MonkeyPatch,
    dt: datetime.datetime,
    expected: int,
) -> None:
    _freeze_now(monkeypatch, dt)
    device = FakeDevice(ALL_SUBMETHODS)
    ctl = _make_controller(device)

    # Provided unsorted; the handler sorts canonically. sorted() order:
    #   globoplay:globo
    #   netflix:70086050
    #   prime_video:amzn1...
    #   youtube:qVw_SkV797M
    params = [
        "youtube:qVw_SkV797M",
        "netflix:70086050",
        "globoplay:globo",
        "prime_video:amzn1.dv.gti.00000000-0000-0000-0000-000000000000",
    ]
    sorted_expected = sorted(params)
    sub, subparam = sorted_expected[expected].split(":", 1)

    await ctl._handle_method_call("playlist", {"params": params})

    assert device.calls == [(sub, subparam)]


async def test_playlist_pick_independent_of_input_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _freeze_now(monkeypatch, datetime.datetime(2026, 3, 15, 9, 0))
    params = [
        "youtube:qVw_SkV797M",
        "netflix:70086050",
        "globoplay:globo",
        "prime_video:amzn1.dv.gti.00000000-0000-0000-0000-000000000000",
    ]

    device_a = FakeDevice(ALL_SUBMETHODS)
    await _make_controller(device_a)._handle_method_call(
        "playlist", {"params": list(params)}
    )

    device_b = FakeDevice(ALL_SUBMETHODS)
    await _make_controller(device_b)._handle_method_call(
        "playlist", {"params": list(reversed(params))}
    )

    assert device_a.calls == device_b.calls
    assert len(device_a.calls) == 1


async def test_playlist_dispatches_single_param_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Jan 4 09:00 -> idx 4 % 1 == 0; only one item, always chosen.
    _freeze_now(monkeypatch, datetime.datetime(2026, 1, 4, 9, 0))
    device = FakeDevice(ALL_SUBMETHODS)
    await _make_controller(device)._handle_method_call(
        "playlist", {"params": ["netflix:70086050"]}
    )
    assert device.calls == [("netflix", "70086050")]


async def test_playlist_unsupported_submethod_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # idx 4 % 1 == 0 -> picks the only item, whose submethod the device
    # does not support; the recursive call hits the gate and returns None.
    _freeze_now(monkeypatch, datetime.datetime(2026, 1, 4, 9, 0))
    device = FakeDevice(frozenset({"youtube"}))  # no netflix support
    result = await _make_controller(device)._handle_method_call(
        "playlist", {"params": ["netflix:70086050"]}
    )
    assert result is None
    assert device.calls == []  # gracefully skipped, no crash


async def test_playlist_nested_playlist_skipped_at_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # idx 4 % 1 == 0 -> picks the only (nested) item; must not recurse.
    _freeze_now(monkeypatch, datetime.datetime(2026, 1, 4, 9, 0))
    device = FakeDevice(ALL_SUBMETHODS)
    result = await _make_controller(device)._handle_method_call(
        "playlist", {"params": ["playlist:netflix:70086050"]}
    )
    assert result is None
    assert device.calls == []


async def test_playlist_empty_params_returns_none() -> None:
    device = FakeDevice(ALL_SUBMETHODS)
    result = await _make_controller(device)._handle_method_call(
        "playlist", {"params": []}
    )
    assert result is None
    assert device.calls == []


async def test_playlist_malformed_item_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # idx 4 % 1 == 0 -> picks the only (colon-less) item.
    _freeze_now(monkeypatch, datetime.datetime(2026, 1, 4, 9, 0))
    device = FakeDevice(ALL_SUBMETHODS)
    result = await _make_controller(device)._handle_method_call(
        "playlist", {"params": ["no_colon_here"]}
    )
    assert result is None
    assert device.calls == []


# --- validate_config -----------------------------------------------------


class _ValidationDevice(devices.Device):
    supported_methods = frozenset(
        {"youtube", "netflix", "prime_video", "globoplay"}
    )


def _config_with_playlist(params: List[str]) -> Dict[str, Any]:
    return {
        "remote": {
            "keys": {"b6": {"method": "playlist", "params": params}},
            "bindings": {},
        }
    }


def test_validate_config_accepts_well_formed_playlist() -> None:
    config = _config_with_playlist(
        [
            "youtube:qVw_SkV797M",
            "netflix:70086050",
            "prime_video:amzn1.dv.gti.00000000-0000-0000-0000-000000000000",
            "globoplay:globo",
        ]
    )
    # Should not raise.
    devices.validate_config(config, _ValidationDevice())


def test_validate_config_rejects_bad_submethod() -> None:
    config = _config_with_playlist(["bogus:whatever"])
    with pytest.raises(ValueError, match="unknown submethod"):
        devices.validate_config(config, _ValidationDevice())


def test_validate_config_rejects_bad_subparam() -> None:
    # netflix expects digits only; "abc" must fail the regex.
    config = _config_with_playlist(["netflix:abc"])
    with pytest.raises(ValueError, match="does not match expected format"):
        devices.validate_config(config, _ValidationDevice())


def test_validate_config_rejects_colonless_playlist_item() -> None:
    config = _config_with_playlist(["youtube_no_colon"])
    with pytest.raises(ValueError, match="expected '<submethod>:<subparam>'"):
        devices.validate_config(config, _ValidationDevice())


def test_validate_config_rejects_nested_playlist() -> None:
    config = _config_with_playlist(["playlist:netflix:70086050"])
    with pytest.raises(ValueError, match="may not nest 'playlist'"):
        devices.validate_config(config, _ValidationDevice())


def test_validate_config_rejects_empty_playlist() -> None:
    # An empty playlist would be a silent dead button at runtime; fail fast.
    config = _config_with_playlist([])
    with pytest.raises(ValueError, match="playlist has no items"):
        devices.validate_config(config, _ValidationDevice())


def test_playlist_not_in_param_validators() -> None:
    # Validation is structural, not a single regex.
    assert "playlist" not in devices._PARAM_VALIDATORS


def test_playlist_in_known_methods() -> None:
    assert "playlist" in devices.KNOWN_METHODS
