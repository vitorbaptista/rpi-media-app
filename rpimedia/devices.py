import asyncio
import logging
import mimetypes
import os
import pathlib
import re
import shlex
import subprocess
import time
import xml.etree.ElementTree as ET
from abc import ABC
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import catt.api

from . import httpserver

logger = logging.getLogger(__name__)

KNOWN_METHODS = frozenset({
    "youtube", "video", "url", "glob",
    "prime_video", "netflix", "globoplay",
    "volume_up", "volume_down", "pause",
    "set_hearing_aids",
})

_PARAM_VALIDATORS: Dict[str, re.Pattern[str]] = {
    "prime_video": re.compile(
        r"^amzn1\.dv\.gti\.[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
        r"[0-9a-f]{4}-[0-9a-f]{12}$"
    ),
    "netflix": re.compile(r"^\d+$"),
    "youtube": re.compile(r"^[A-Za-z0-9_-]{11}$"),
    "globoplay": re.compile(r"^[a-z0-9-]{1,64}$"),
    "set_hearing_aids": re.compile(r"^(on|off|toggle)$"),
}


class Device(ABC):
    supports_enqueue: bool = False
    supported_methods: frozenset[str] = frozenset()

    async def _unsupported(self, method: str) -> None:
        logger.warning(
            f"{self.__class__.__name__} does not support {method}"
        )
        return None

    async def play_youtube(self, video_id: str) -> Optional[asyncio.subprocess.Process]:
        return await self._unsupported("play_youtube")

    async def enqueue_youtube(self, video_id: str) -> Optional[asyncio.subprocess.Process]:
        return await self._unsupported("enqueue_youtube")

    async def play_prime_video(self, gti: str) -> Optional[asyncio.subprocess.Process]:
        return await self._unsupported("play_prime_video")

    async def play_netflix(self, netflix_id: str) -> Optional[asyncio.subprocess.Process]:
        return await self._unsupported("play_netflix")

    async def play_globoplay(self, slug: str) -> Optional[asyncio.subprocess.Process]:
        return await self._unsupported("play_globoplay")

    async def play_url(self, url: str) -> Optional[asyncio.subprocess.Process]:
        return await self._unsupported("play_url")

    async def play_video(self, path: str) -> Optional[asyncio.subprocess.Process]:
        return await self._unsupported("play_video")

    async def skip_video(self) -> Optional[asyncio.subprocess.Process]:
        return await self._unsupported("skip_video")

    async def volume_up(self, n: int) -> Optional[asyncio.subprocess.Process]:
        return await self._unsupported("volume_up")

    async def volume_down(self, n: int) -> Optional[asyncio.subprocess.Process]:
        return await self._unsupported("volume_down")

    async def pause(self) -> Optional[asyncio.subprocess.Process]:
        return await self._unsupported("pause")

    async def is_playing(self) -> bool:
        logger.warning(
            f"{self.__class__.__name__} does not support is_playing"
        )
        return False

    async def resume(self) -> bool:
        """Resume a paused media session in place. Return True iff resumed."""
        await self._unsupported("resume")
        return False

    async def set_hearing_aids(self, enabled: bool) -> bool:
        """Connect (enabled=True) or disconnect (False) paired hearing aids.

        Returns True iff the requested state was reached.
        """
        await self._unsupported("set_hearing_aids")
        return False

    async def is_hearing_aid_connected(self) -> bool:
        """Return True iff a hearing aid is currently connected."""
        return False


class ChromecastDevice(Device):
    VIDEO_MIN_EXECUTION_TIME: float = 120
    MAX_RETRY_ATTEMPTS: int = 3
    IS_PLAYING_CHECKS: int = 2
    IS_PLAYING_CHECK_INTERVAL: float = 60
    IS_PLAYING_TIMEOUT: float = 15

    supports_enqueue = True
    supported_methods = frozenset({
        "youtube", "video", "url", "glob",
        "volume_up", "volume_down", "pause",
    })

    async def play_youtube(self, video_id: str) -> Optional[asyncio.subprocess.Process]:
        logger.debug(f"Playing youtube video {video_id}")
        return await self._run(
            ["catt", "cast", f"https://www.youtube.com/watch?v={video_id}"]
        )

    async def enqueue_youtube(self, video_id: str) -> Optional[asyncio.subprocess.Process]:
        logger.debug(f"Enqueuing youtube video {video_id}")
        return await self._run(
            ["catt", "add", f"https://www.youtube.com/watch?v={video_id}"]
        )

    async def play_url(self, url: str) -> Optional[asyncio.subprocess.Process]:
        logger.debug(f"Playing url {url}")
        return await self._run(["catt", "cast", url])

    async def play_video(self, path: str) -> Optional[asyncio.subprocess.Process]:
        logger.debug(f"Playing video {path}")
        return await self._run(
            ["catt", "cast", "--block", path],
            min_execution_time=self.VIDEO_MIN_EXECUTION_TIME,
        )

    async def skip_video(self) -> Optional[asyncio.subprocess.Process]:
        logger.debug("Skipping video")
        return await self._run(["catt", "skip"])

    async def volume_up(self, n: int) -> Optional[asyncio.subprocess.Process]:
        logger.debug(f"Volume up by {n}")
        return await self._run(["catt", "volumeup", str(n)])

    async def volume_down(self, n: int) -> Optional[asyncio.subprocess.Process]:
        logger.debug(f"Volume down by {n}")
        return await self._run(["catt", "volumedown", str(n)])

    async def pause(self) -> Optional[asyncio.subprocess.Process]:
        logger.debug("Toggling play/pause")
        return await self._run(["catt", "play_toggle"])

    async def is_playing(self) -> bool:
        """Return True only if every attempt reports playback.

        Conservative: one idle check is enough to conclude the device is idle,
        which matches the behavior of the former chromecast_checker.
        """
        for attempt in range(self.IS_PLAYING_CHECKS):
            if attempt > 0:
                await asyncio.sleep(self.IS_PLAYING_CHECK_INTERVAL)
            try:
                playing = await asyncio.wait_for(
                    asyncio.to_thread(self._is_playing_sync),
                    timeout=self.IS_PLAYING_TIMEOUT,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "catt discovery/prep_info timed out; treating as idle"
                )
                return False
            if not playing:
                return False
        return True

    def _is_playing_sync(self) -> bool:
        discovered = catt.api.discover()
        if not discovered:
            logger.warning("no Chromecast discovered; treating as idle")
            return False
        device = discovered[0]
        if not device.controller:
            return False
        device.controller.prep_info()
        media_info = device.controller.media_info
        if media_info is None:
            return False
        current_time = media_info.get("current_time")
        title = media_info.get("title") or ""
        if current_time is None:
            # Live streams (e.g. TV Aparecida) have no current_time
            return "ao vivo" in title.lower()
        return current_time > 0

    async def _run(
        self,
        command: List[str],
        min_execution_time: Optional[float] = None,
        _attempts: int = 0,
    ) -> Optional[asyncio.subprocess.Process]:
        process: Optional[asyncio.subprocess.Process] = None
        try:
            _attempts += 1
            if _attempts > self.MAX_RETRY_ATTEMPTS:
                logger.error(
                    f"Process finished too quickly after {self.MAX_RETRY_ATTEMPTS} "
                    f"attempts. Giving up."
                )
                return None

            process = await asyncio.create_subprocess_exec(*command)

            if not min_execution_time:
                return process

            await asyncio.wait_for(process.wait(), timeout=min_execution_time)

            logger.info(
                f"Process finished too quickly running again "
                f"(attempt {_attempts}/{self.MAX_RETRY_ATTEMPTS})"
            )
            return await self._run(command, min_execution_time, _attempts)

        except asyncio.TimeoutError:
            return process
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            logger.debug(f"Failed to run command: {e}")
            return None


class FireTVDevice(Device):
    ADB_PORT: int = 5555
    MDNS_TIMEOUT: float = 15

    PRIME_VIDEO_PACKAGE: str = "com.amazon.firebat"
    PRIME_VIDEO_ACTIVITY: str = "com.amazon.pyrocore.IgnitionActivity"
    PRIME_VIDEO_WAIT_SECONDS: float = 6

    YOUTUBE_PACKAGE: str = "com.amazon.firetv.youtube"
    YOUTUBE_ACTIVITY: str = "dev.cobalt.app.MainActivity"

    NETFLIX_PACKAGE: str = "com.netflix.ninja"
    NETFLIX_ACTIVITY: str = ".MainActivity"
    NETFLIX_WAIT_SECONDS: float = 2
    NETFLIX_FLAGS: str = "0x10000020"

    GLOBOPLAY_PACKAGE: str = "com.globo.globotv"
    GLOBOPLAY_CHOOSER_ACTIVITY: str = ".accountchoosertv.AccountChooserActivity"
    GLOBOPLAY_HUB_ACTIVITY: str = ".categoriesdetailspagetv.CategoryDetailsPageActivity"
    ACTIVITY_WAIT_TIMEOUT: float = 20
    # Free-tier accounts always show the profile chooser on cold launch with
    # the (single) real profile pre-focused. DPAD_CENTER on the chooser drops
    # us at MainActivity (losing the deep link target) — only a screen tap
    # routes through to the channel hub. `input tap` uses display coordinates,
    # not content coordinates: these are correct for a 1080p panel; verify
    # with `adb shell wm size` if the device renegotiates to 4K.
    GLOBOPLAY_PROFILE_TAP_X: int = 810
    GLOBOPLAY_PROFILE_TAP_Y: int = 508
    # The chooser activity is "resumed" before its content is rendered and
    # tap-receptive. ~2s isn't always enough; 4s is reliable in practice.
    GLOBOPLAY_CHOOSER_SETTLE_SECONDS: float = 4
    # The hub's "Agora na TV" hero starts playback. DPAD_CENTER on this view
    # is not wired reliably (gets dropped or routes to a no-op listener), but
    # an `input tap` at the hero's geometric center triggers playback every
    # time. Coords are the center of the hero card (bounds [140,184][1780,886]
    # on a 1080p panel).
    GLOBOPLAY_HUB_HERO_TAP_X: int = 960
    GLOBOPLAY_HUB_HERO_TAP_Y: int = 535
    GLOBOPLAY_HUB_SETTLE_SECONDS: float = 3

    VLC_PACKAGE: str = "org.videolan.vlc"
    VLC_ACTIVITY: str = ".StartActivity"

    _MEDIA_PACKAGES: Tuple[str, ...] = (
        PRIME_VIDEO_PACKAGE, YOUTUBE_PACKAGE, NETFLIX_PACKAGE, VLC_PACKAGE,
        GLOBOPLAY_PACKAGE,
    )

    HEARING_AID_PACKAGE: str = "com.amazon.hearingaid"
    HEARING_AID_ACTIVITY: str = ".ui.HearingAidMainActivity"
    HEARING_AID_DEVICE_LIST_ID: str = (
        "com.amazon.hearingaid:id/hearing_aid_gridview"
    )
    HEARING_AID_DETAIL_LIST_ID: str = (
        "com.amazon.hearingaid:id/hearing_aid_settings_gridview"
    )
    HEARING_AID_GRID_ITEM_ID: str = (
        "com.amazon.hearingaid:id/gridview_item_title"
    )
    # 0=Volume, 1=Mute, 2=Connect/Disconnect, 3=Unpair. Position is stable
    # across pt_BR and en; the toggle's *text* changes (Conectar /
    # Desconectar), so we match by resource-id + position, not by text.
    HEARING_AID_TOGGLE_INDEX: int = 2
    HEARING_AID_UI_TIMEOUT: float = 6.0
    HEARING_AID_UI_POLL_INTERVAL: float = 0.5
    HEARING_AID_DISCONNECT_TIMEOUT: float = 8.0
    # The activity paints its content_pane before its FocusManager has
    # latched onto the device row; a DPAD_CENTER fired in that window
    # gets dropped. Empirically ~1s is sufficient.
    HEARING_AID_FOCUS_SETTLE_SECONDS: float = 1.0
    HEARING_AID_DRILL_ATTEMPTS: int = 3

    supports_enqueue = False
    supported_methods = frozenset({
        "youtube", "prime_video", "netflix", "globoplay", "video", "glob",
        "volume_up", "volume_down", "pause",
        "set_hearing_aids",
    })

    def __init__(
        self,
        address: Optional[str] = None,
        video_root: Optional[str] = None,
    ) -> None:
        self._configured_address = address
        self._cached_ip: Optional[str] = None
        self._video_root = (
            pathlib.Path(video_root).resolve() if video_root else None
        )
        self._video_http: Optional[httpserver.VideoServer] = None

    async def play_youtube(self, video_id: str) -> Optional[asyncio.subprocess.Process]:
        logger.debug(f"Playing youtube video {video_id}")
        await self._force_stop(self.YOUTUBE_PACKAGE)
        return await self._start(
            f"{self.YOUTUBE_PACKAGE}/{self.YOUTUBE_ACTIVITY}",
            f"https://www.youtube.com/watch?v={video_id}",
        )

    async def play_prime_video(self, gti: str) -> Optional[asyncio.subprocess.Process]:
        logger.debug(f"Playing prime video {gti}")
        await self._force_stop(self.PRIME_VIDEO_PACKAGE)
        proc = await self._start(
            f"{self.PRIME_VIDEO_PACKAGE}/{self.PRIME_VIDEO_ACTIVITY}",
            f"https://watch.amazon.com/detail?gti={gti}",
        )
        if proc is None:
            return None
        await asyncio.sleep(self.PRIME_VIDEO_WAIT_SECONDS)
        await self._keyevent("KEYCODE_DPAD_CENTER")
        return proc

    async def play_netflix(self, netflix_id: str) -> Optional[asyncio.subprocess.Process]:
        logger.debug(f"Playing netflix {netflix_id}")
        await self._force_stop(self.NETFLIX_PACKAGE)
        await asyncio.sleep(self.NETFLIX_WAIT_SECONDS)
        return await self._start(
            f"{self.NETFLIX_PACKAGE}/{self.NETFLIX_ACTIVITY}",
            f"netflix://title/{netflix_id}",
            flags=self.NETFLIX_FLAGS,
            extras=f"-e amzn_deeplink_data {shlex.quote(netflix_id)}",
        )

    async def play_globoplay(self, slug: str) -> Optional[asyncio.subprocess.Process]:
        """Open the Globoplay live broadcast for `slug` (e.g. ``"futura"``,
        ``"globo"``). The free-tier flow has no single-button path to live, so
        we chain: deep link → tap profile chooser → DPAD_CENTER on the hub's
        "Agora na TV" hero, which hands off to MainActivity's broadcast
        fragment with the live stream playing.
        """
        logger.debug(f"Playing globoplay channel {slug}")
        await self._force_stop(self.GLOBOPLAY_PACKAGE)
        # Use `-p <package>` rather than `-n <component>`: pinning the splash
        # activity explicitly causes the chooser to drop the deep-link target
        # on dismiss, landing at MainActivity instead of the channel hub.
        url = f"https://globoplay.globo.com/canais/{slug}/"
        proc = await self._shell(
            "am start -a android.intent.action.VIEW "
            f"-d {shlex.quote(url)} -p {self.GLOBOPLAY_PACKAGE}"
        )
        if proc is None:
            return None
        # Splash → MainActivity → chooser takes ~8s on cold launch and varies
        # with network. Poll instead of sleeping a fixed interval.
        if not await self._wait_for_activity(self.GLOBOPLAY_CHOOSER_ACTIVITY):
            return proc
        await asyncio.sleep(self.GLOBOPLAY_CHOOSER_SETTLE_SECONDS)
        await self._tap(
            self.GLOBOPLAY_PROFILE_TAP_X, self.GLOBOPLAY_PROFILE_TAP_Y
        )
        if not await self._wait_for_activity(self.GLOBOPLAY_HUB_ACTIVITY):
            return proc
        await asyncio.sleep(self.GLOBOPLAY_HUB_SETTLE_SECONDS)
        await self._tap(
            self.GLOBOPLAY_HUB_HERO_TAP_X, self.GLOBOPLAY_HUB_HERO_TAP_Y
        )
        return proc

    async def _wait_for_activity(
        self, activity: str, timeout: float = ACTIVITY_WAIT_TIMEOUT,
    ) -> bool:
        """Block until the resumed activity's component name ends with
        `activity` (e.g. ``".accountchoosertv.AccountChooserActivity"`` or
        a fully-qualified ``"pkg/.path.Cls"``). Returns False on timeout.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            out = await self._shell_capture("dumpsys activity activities")
            component = _resumed_activity_component(out) if out else None
            if component and component.endswith(activity):
                return True
            await asyncio.sleep(0.5)
        logger.warning(f"timed out waiting for activity {activity!r}")
        return False

    async def volume_up(self, n: int) -> Optional[asyncio.subprocess.Process]:
        logger.debug(f"Volume up by {n}")
        proc: Optional[asyncio.subprocess.Process] = None
        for _ in range(n):
            proc = await self._keyevent("KEYCODE_VOLUME_UP")
        return proc

    async def volume_down(self, n: int) -> Optional[asyncio.subprocess.Process]:
        logger.debug(f"Volume down by {n}")
        proc: Optional[asyncio.subprocess.Process] = None
        for _ in range(n):
            proc = await self._keyevent("KEYCODE_VOLUME_DOWN")
        return proc

    async def pause(self) -> Optional[asyncio.subprocess.Process]:
        logger.debug("Toggling play/pause")
        return await self._keyevent("KEYCODE_MEDIA_PLAY_PAUSE")

    async def is_hearing_aid_connected(self) -> bool:
        """Return True iff a hearing aid is currently connected.

        Reads the AOSP-defined Settings.Secure flag set by the
        BluetoothHearingAid profile service when the ASHA ACL link
        completes.
        """
        out = await self._shell_capture(
            "settings get secure hearing_aid_connected"
        )
        return out is not None and out.strip() == "1"

    async def set_hearing_aids(self, enabled: bool) -> bool:
        """Connect or disconnect paired hearing aids.

        Stock Fire OS blocks every shell-side path to a profile
        disconnect: BLUETOOTH_PRIVILEGED is signature|privileged and not
        granted to the shell uid; ``svc bluetooth disable`` is killed by
        the sandbox; ``service call bluetooth_manager`` enable/disable
        return SecurityException; ``am force-stop com.android.bluetooth``
        is a no-op against the protected BT process. The Amazon
        ``HearingAidUI`` Settings activity, however, runs as a privileged
        process and *can* invoke the privileged
        ``BluetoothHearingAid.{connect,disconnect}`` API on our behalf,
        so we drive it via uiautomator + key/tap events.

        For the disable transition we verify the post-tap state via
        ``hearing_aid_connected`` and return False if the disconnect
        didn't land. For enable we trust the tap: it sets the device's
        connection priority to AUTO_CONNECT and initiates the ACL, but
        whether the link actually completes depends on the hearing aid
        being powered on and in range, which we don't control.
        """
        target = await self._ensure_connected()
        if target is None:
            return False

        logger.info(f"set_hearing_aids({enabled})")

        # The UI's connect/disconnect grid item is a *toggle* whose
        # direction depends on the live connection state ("Conectar" when
        # disconnected, "Desconectar" when connected). If the live state
        # already matches the request, tapping would toggle the wrong
        # way — so check first and short-circuit.
        if (await self.is_hearing_aid_connected()) == enabled:
            logger.info(
                f"hearing aid already in desired state ({enabled}); skipping"
            )
            return True

        # ``-S`` force-stops then starts, so we always land on the
        # device-list pane regardless of any cached navigation state.
        proc = await self._shell(
            f"am start -S -n "
            f"{self.HEARING_AID_PACKAGE}/{self.HEARING_AID_ACTIVITY}"
        )
        if proc is None or proc.returncode != 0:
            logger.warning("failed to launch HearingAidMainActivity")
            return False

        if not await self._wait_for_ui_node(self.HEARING_AID_DEVICE_LIST_ID):
            logger.warning("hearing-aid device list did not render")
            await self._keyevent("KEYCODE_HOME")
            return False

        # The single paired hearing-aid row is auto-focused; drill in.
        # Retry on failure: a DPAD_CENTER fired before the FocusManager
        # has latched onto the row gets dropped, leaving us on the
        # device list with no detail page in sight.
        detail_xml: Optional[str] = None
        for attempt in range(self.HEARING_AID_DRILL_ATTEMPTS):
            await asyncio.sleep(self.HEARING_AID_FOCUS_SETTLE_SECONDS)
            await self._keyevent("KEYCODE_DPAD_CENTER")
            detail_xml = await self._wait_for_ui_xml(
                self.HEARING_AID_DETAIL_LIST_ID
            )
            if detail_xml is not None:
                break
            logger.info(
                f"hearing-aid drill-in attempt {attempt + 1} did not "
                "land on detail; retrying"
            )
        if detail_xml is None:
            logger.warning("hearing-aid device detail did not render")
            await self._keyevent("KEYCODE_HOME")
            return False

        bounds = _nth_node_bounds(
            detail_xml,
            self.HEARING_AID_GRID_ITEM_ID,
            self.HEARING_AID_TOGGLE_INDEX,
        )
        if bounds is None:
            logger.warning(
                "hearing-aid connect/disconnect button not found in UI dump"
            )
            await self._keyevent("KEYCODE_HOME")
            return False

        cx = (bounds[0] + bounds[2]) // 2
        cy = (bounds[1] + bounds[3]) // 2
        await self._tap(cx, cy)

        success = True
        if not enabled:
            success = await self._wait_for_hearing_aid_state(
                expected=False,
                timeout=self.HEARING_AID_DISCONNECT_TIMEOUT,
            )
            if not success:
                logger.warning(
                    "hearing aid did not disconnect within "
                    f"{self.HEARING_AID_DISCONNECT_TIMEOUT}s"
                )

        await self._keyevent("KEYCODE_HOME")
        return success

    async def _dump_ui(self) -> Optional[str]:
        """Capture the current uiautomator hierarchy as XML, or None.

        Uses ``$$`` so concurrent shell invocations don't clobber each
        other's dump file — `flock` already prevents this from cron, but
        the cost of per-shell uniqueness is one shell expansion.
        """
        return await self._shell_capture(
            "f=/sdcard/ui_$$.xml; "
            "uiautomator dump \"$f\" >/dev/null 2>&1 "
            "&& cat \"$f\"; rm -f \"$f\"",
            timeout=8,
        )

    async def _wait_for_ui_node(self, resource_id: str) -> bool:
        return await self._wait_for_ui_xml(resource_id) is not None

    async def _wait_for_ui_xml(self, resource_id: str) -> Optional[str]:
        deadline = (
            asyncio.get_event_loop().time() + self.HEARING_AID_UI_TIMEOUT
        )
        needle = f'resource-id="{resource_id}"'
        while asyncio.get_event_loop().time() < deadline:
            xml = await self._dump_ui()
            if xml and needle in xml:
                return xml
            await asyncio.sleep(self.HEARING_AID_UI_POLL_INTERVAL)
        return None

    async def _wait_for_hearing_aid_state(
        self, expected: bool, timeout: float
    ) -> bool:
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            if (await self.is_hearing_aid_connected()) == expected:
                return True
            await asyncio.sleep(self.HEARING_AID_UI_POLL_INTERVAL)
        return False

    async def play_video(self, path: str) -> Optional[asyncio.subprocess.Process]:
        logger.debug(f"Playing local video {path}")
        if self._video_root is None:
            logger.warning(
                "FireTVDevice has no video_root configured; cannot play "
                "local files"
            )
            return None
        try:
            rel = pathlib.Path(path).resolve().relative_to(self._video_root)
        except ValueError:
            logger.warning(
                f"video path {path!r} is outside video_root "
                f"{str(self._video_root)!r}; skipping"
            )
            return None
        # Resolve Fire TV IP first so we bind the HTTP server to the interface
        # that actually routes to it (not, e.g., Tailscale).
        fire_tv_ip = await self._resolve_ip()
        if fire_tv_ip is None:
            return None
        host = httpserver.detect_local_ip(fire_tv_ip)
        if host is None:
            return None
        if self._video_http is None:
            self._video_http = httpserver.VideoServer(str(self._video_root))
        port = self._video_http.ensure_running(bind_host=host)
        url = f"http://{host}:{port}/" + "/".join(quote(p) for p in rel.parts)
        # Derive a concrete MIME type so VLC's VIEW intent filter matches
        # reliably (a wildcard `video/*` can miss on some Fire OS versions).
        mime, _ = mimetypes.guess_type(rel.name)
        await self._force_stop(self.VLC_PACKAGE)
        return await self._start(
            f"{self.VLC_PACKAGE}/{self.VLC_ACTIVITY}",
            url,
            mime_type=mime or "",
        )

    async def is_playing(self) -> bool:
        """Return True iff a media session reports state=3 AND a media app
        is currently foregrounded.

        The foreground cross-check guards against stale PlaybackState entries
        that a backgrounded app may leave behind — without it, navigating to
        the launcher after watching could read as "playing" indefinitely.
        """
        return await self._session_state_with_foreground() == 3

    async def resume(self) -> bool:
        """Send MEDIA_PLAY iff the foreground media app is paused.

        No-op when nothing is paused (idle, playing, or backgrounded session
        with stale state), so safe to run unconditionally from cron alongside
        is_playing.
        """
        if await self._session_state_with_foreground() != 2:
            return False
        logger.info("foreground media app is paused; resuming")
        await self._keyevent("KEYCODE_MEDIA_PLAY")
        return True

    async def _session_state_with_foreground(self) -> Optional[int]:
        """Return the active session's playback state, or None if no media
        app is foregrounded.

        The foreground cross-check guards against stale PlaybackState entries
        that a backgrounded app may leave behind — without it, navigating to
        the launcher after watching could read as "playing" indefinitely.
        """
        sessions = await self._shell_capture("dumpsys media_session")
        if sessions is None:
            return None
        state = _active_session_state(sessions)
        if state is None:
            return None
        activities = await self._shell_capture("dumpsys activity activities")
        if activities is None:
            return None
        if not _foreground_is_media_app(activities, self._MEDIA_PACKAGES):
            return None
        return state

    async def _start(
        self,
        component: str,
        url: str,
        flags: str = "",
        extras: str = "",
        mime_type: str = "",
    ) -> Optional[asyncio.subprocess.Process]:
        cmd_parts = [
            "am start",
            f"-n {shlex.quote(component)}",
            "-a android.intent.action.VIEW",
            f"-d {shlex.quote(url)}",
        ]
        if mime_type:
            cmd_parts.append(f"-t {shlex.quote(mime_type)}")
        if flags:
            cmd_parts.append(f"-f {flags}")
        if extras:
            cmd_parts.append(extras)
        return await self._shell(" ".join(cmd_parts))

    async def _force_stop(self, package: str) -> Optional[asyncio.subprocess.Process]:
        return await self._shell(f"am force-stop {shlex.quote(package)}")

    async def _keyevent(self, keycode: str) -> Optional[asyncio.subprocess.Process]:
        return await self._shell(f"input keyevent {shlex.quote(keycode)}")

    async def _tap(self, x: int, y: int) -> Optional[asyncio.subprocess.Process]:
        return await self._shell(f"input tap {int(x)} {int(y)}")

    async def _shell_capture(
        self, remote_cmd: str, timeout: float = 5
    ) -> Optional[str]:
        """Run `adb shell <cmd>` and return stdout, or None on any failure."""
        target = await self._ensure_connected()
        if target is None:
            return None
        try:
            proc = await asyncio.create_subprocess_exec(
                "adb", "-s", target, "shell", remote_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError as e:
            logger.warning(f"adb shell failed: {e}")
            return None
        try:
            out_bytes, _ = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"adb shell timed out after {timeout}s")
            proc.kill()
            await proc.wait()
            return None
        if proc.returncode != 0:
            logger.warning(
                f"adb shell exited {proc.returncode}; treating as no data"
            )
            return None
        return out_bytes.decode(errors="replace")

    async def _shell(self, remote_cmd: str) -> Optional[asyncio.subprocess.Process]:
        """Run `adb shell <cmd>` and wait for completion.

        Awaiting completion is required: back-to-back commands (e.g. force-stop
        then `am start`) race otherwise, and a not-yet-stopped app causes
        `am start` to print "brought to the front" and silently drop the URL.
        """
        target = await self._ensure_connected()
        if target is None:
            return None
        try:
            proc = await asyncio.create_subprocess_exec(
                "adb", "-s", target, "shell", remote_cmd
            )
            await proc.wait()
            return proc
        except OSError as e:
            logger.warning(f"adb shell failed: {e}")
            return None

    async def _ensure_connected(self) -> Optional[str]:
        ip = await self._resolve_ip()
        if ip is None:
            return None
        target = f"{ip}:{self.ADB_PORT}"
        try:
            proc = await asyncio.create_subprocess_exec(
                "adb", "connect", target,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            out_bytes, _ = await proc.communicate()
        except OSError as e:
            logger.warning(f"adb connect failed: {e}")
            self._cached_ip = None
            return None

        out = out_bytes.decode(errors="replace")
        if "connected to" in out or "already connected" in out:
            return target

        logger.warning(f"adb connect failed for {target}: {out.strip()}")
        self._cached_ip = None
        return None

    async def _resolve_ip(self) -> Optional[str]:
        if self._configured_address:
            return self._configured_address
        if self._cached_ip:
            return self._cached_ip
        discovered = await _discover_firetv(self.MDNS_TIMEOUT)
        if discovered is None:
            logger.warning("no Fire TV discovered via mDNS")
            return None
        name, ip = discovered
        logger.info(f"discovered Fire TV: {name} at {ip}")
        self._cached_ip = ip
        return ip


async def _discover_firetv(timeout: float) -> Optional[Tuple[str, str]]:
    """Run avahi-browse and return (name, ip) of the first Fire TV found."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "avahi-browse", "-artp",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except OSError as e:
        logger.warning(f"mDNS discovery failed to spawn avahi-browse: {e}")
        return None

    try:
        out_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning("mDNS discovery timed out")
        proc.kill()
        await proc.wait()
        return None

    for line in out_bytes.decode(errors="replace").splitlines():
        if not line.startswith("="):
            continue
        fields = line.split(";")
        if len(fields) < 9 or fields[4] != "Amazon Fire TV":
            continue
        ip = fields[7]
        txt_blob = fields[9] if len(fields) > 9 else ""
        name = _extract_friendly_name(txt_blob) or fields[4]
        return name, ip
    return None


_UI_BOUNDS_PATTERN = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def _nth_node_bounds(
    ui_xml: str, resource_id: str, n: int
) -> Optional[Tuple[int, int, int, int]]:
    """Return the (x1, y1, x2, y2) bounds of the nth node (0-indexed)
    matching ``resource_id`` in a uiautomator dump, or None.
    """
    try:
        root = ET.fromstring(ui_xml)
    except ET.ParseError:
        return None
    matches = []
    for node in root.iter("node"):
        if node.attrib.get("resource-id") != resource_id:
            continue
        m = _UI_BOUNDS_PATTERN.match(node.attrib.get("bounds", ""))
        if m:
            matches.append(tuple(int(g) for g in m.groups()))
    if n >= len(matches):
        return None
    return matches[n]


_PLAYBACK_STATE_PATTERN = re.compile(r"PlaybackState\s*\{\s*state=(\d+)")


_RESUMED_COMPONENT_PATTERN = re.compile(r"\b([\w.]+/[\w.]+)\b")


def _resumed_activity_component(dumpsys_activities_output: str) -> Optional[str]:
    """Extract the resumed activity's ``pkg/.path.Cls`` component, or None.

    Anchors on `ResumedActivity` rather than `mLastResumedActivity`, which
    can point at a stale prior activity.
    """
    for line in dumpsys_activities_output.splitlines():
        if line.lstrip().startswith("ResumedActivity"):
            match = _RESUMED_COMPONENT_PATTERN.search(line)
            return match.group(1) if match else None
    return None


def _foreground_is_media_app(
    dumpsys_activities_output: str, media_packages: Tuple[str, ...]
) -> bool:
    """Return True if the currently-resumed activity belongs to a media app.

    Looks only at the `ResumedActivity` line rather than the full dump,
    which otherwise lists every activity the system knows about (including
    backgrounded ones).
    """
    for line in dumpsys_activities_output.splitlines():
        # Anchor on the field name: substring containment would also match
        # `mLastResumedActivity`, which can point at a stale prior activity.
        if line.lstrip().startswith("ResumedActivity"):
            return any(pkg in line for pkg in media_packages)
    return False


_MEDIA_BUTTON_SESSION_PATTERN = re.compile(
    r"Media button session is (.+?) \(userId="
)


def _active_session_state(dumpsys_output: str) -> Optional[int]:
    """Return the playback state of the media-button session.

    Android's MediaSession states: 0=none, 1=stopped, 2=paused, 3=playing,
    4=fast-forwarding, 5=rewinding, 6=buffering, 7=error, 8=connecting.

    `dumpsys media_session` lists every session known to the framework —
    Bluetooth, Alexa, the TTS player, and stale entries from previously-run
    media apps. Some of those report state=3 indefinitely even though they're
    not actually playing. The "Media button session is X" line names the one
    session that owns the media-button receiver, which is always the
    foreground app's session; reading its state is what we want.
    """
    active_match = _MEDIA_BUTTON_SESSION_PATTERN.search(dumpsys_output)
    if active_match is None:
        return None
    active_id = active_match.group(1)
    # The Sessions Stack header for this session is "<tag> <pkg>/<tag>
    # (userId=N)", so we look for `<active_id> (userId=` *after* the line
    # that named the session. The first state=PlaybackState following that
    # header is the active session's state — every session block emits its
    # state line before any nested sub-sections.
    block_marker = f"{active_id} (userId="
    after_announcement = dumpsys_output[active_match.end():]
    block_idx = after_announcement.find(block_marker)
    if block_idx < 0:
        logger.debug(
            f"media_session announced active={active_id!r} but no matching "
            "session block found; dumpsys format may have drifted"
        )
        return None
    block_text = after_announcement[block_idx:]
    state_match = _PLAYBACK_STATE_PATTERN.search(block_text)
    if state_match is None:
        return None
    return int(state_match.group(1))


def _extract_friendly_name(txt_blob: str) -> Optional[str]:
    """Pull the instance name from the TXT record `n=...` if present.

    avahi-browse emits all TXT records in a single semicolon field as
    space-separated quoted strings: `"a=0" "ad=..." "n=Fire TV Cube de VITOR"`.
    """
    try:
        tokens = shlex.split(txt_blob)
    except ValueError:
        return None
    for token in tokens:
        if token.startswith("n="):
            return token[2:]
    return None


def build_device(config: Dict[str, Any]) -> Device:
    dev_config = config.get("device", {}) or {}
    dev_type = dev_config.get("type", "chromecast")
    if dev_type == "chromecast":
        return ChromecastDevice()
    if dev_type == "firetv":
        repo_root = os.path.join(os.path.dirname(__file__), "..")
        video_root = os.path.join(repo_root, "data")
        return FireTVDevice(
            address=dev_config.get("address"),
            video_root=video_root,
        )
    raise ValueError(f"unknown device type: {dev_type!r}")


def validate_config(config: Dict[str, Any], device: Device) -> None:
    """Check every configured remote key's method + params. Raise on any issue."""
    keys = config.get("remote", {}).get("keys", {})
    for key_name, key_config in keys.items():
        method = key_config.get("method")
        if method not in KNOWN_METHODS:
            raise ValueError(
                f"key '{key_name}' uses unknown method: {method!r}"
            )
        if method not in device.supported_methods:
            logger.warning(
                f"key '{key_name}' uses method '{method}' which is not "
                f"supported by {device.__class__.__name__}; pressing this "
                f"button will be a no-op"
            )
        validator = _PARAM_VALIDATORS.get(method)
        if validator is None:
            continue
        params = key_config.get("params", [])
        if isinstance(params, str):
            params = [params]
        for param in params:
            if not isinstance(param, str) or not validator.match(param):
                raise ValueError(
                    f"key '{key_name}': param {param!r} for method "
                    f"'{method}' does not match expected format"
                )

    bindings = config.get("remote", {}).get("bindings", {})
    for binding_key, binding_value in bindings.items():
        if binding_value not in keys:
            raise ValueError(
                f"binding {binding_key!r} -> {binding_value!r} references "
                f"a key config that does not exist"
            )
