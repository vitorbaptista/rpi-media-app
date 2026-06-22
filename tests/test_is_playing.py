"""Tests for `_active_session_state`, the `dumpsys media_session` parser that
decides whether the Fire TV is playing.

A false "idle" reading is destructive: the cron line
`rpimedia is_playing || rpimedia send_event keyboard_input c` starts a second
video on top of one already playing. These tests pin the parse against the
`dumpsys` shapes that have (or could) trip it.
"""

from rpimedia.devices import _active_session_state


def _dump(*blocks: str) -> str:
    """Assemble a media_session dump: announcement + Sessions Stack of blocks.

    The stack is sorted "top of stack at the end", so the LAST block is the
    most current session.
    """
    yt = "com.amazon.firetv.youtube/MediaSessionService"
    body = "\n".join(blocks)
    return (
        f"  Media button session is {yt} (userId=0)\n"
        "  Sessions Stack - have N sessions, top of stack at the end:\n"
        f"{body}\n"
    )


def _block(component: str, state: int, extra: str = "") -> str:
    lines = [f"    tag {component} (userId=0)"]
    if extra:
        lines.append(f"      {extra}")
    lines.append(f"      state=PlaybackState {{state={state}, position=0}}")
    return "\n".join(lines)


YT = "com.amazon.firetv.youtube/MediaSessionService"
BT = "com.amazon.bluetooth.audio/btSession"


def test_single_playing_session():
    assert _active_session_state(_dump(_block(YT, 3))) == 3


def test_buffering_counts_as_playing():
    assert _active_session_state(_dump(_block(YT, 6))) == 6


def test_stale_duplicate_then_live_reads_live():
    # The bug: same app owns a lingering stale session (stopped) listed before
    # the live one. Reading the first match alone would report idle.
    dump = _dump(_block(YT, 1), _block(YT, 3))
    assert _active_session_state(dump) == 3


def test_callback_userid_before_state_does_not_truncate_block():
    # A controller/callback line carrying "(userId=" before the PlaybackState
    # must not be mistaken for the next session header.
    dump = _dump(_block(YT, 3, extra="cb ISessionCallback$Stub$Proxy@a (userId=0)"))
    assert _active_session_state(dump) == 3


def test_unrelated_session_playing_does_not_win():
    # An unrelated Bluetooth session stuck at state=3 must NOT read as playing
    # when the active (media-button) session is paused.
    dump = _dump(_block(BT, 3), _block(YT, 2))
    assert _active_session_state(dump) == 2


def test_paused_active_session():
    assert _active_session_state(_dump(_block(YT, 2))) == 2


def test_no_media_button_session():
    assert _active_session_state("Media button session is null\n") is None


def test_announced_but_no_block():
    assert _active_session_state(f"  Media button session is {YT} (userId=0)\n") is None
