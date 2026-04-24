import asyncio
import logging
import mimetypes
import os
import pathlib
import re
import shlex
import subprocess
from abc import ABC
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import catt.api

from . import httpserver

logger = logging.getLogger(__name__)

KNOWN_METHODS = frozenset({
    "youtube", "video", "url", "glob",
    "prime_video", "netflix",
    "volume_up", "volume_down", "pause",
})

_PARAM_VALIDATORS: Dict[str, re.Pattern[str]] = {
    "prime_video": re.compile(
        r"^amzn1\.dv\.gti\.[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
        r"[0-9a-f]{4}-[0-9a-f]{12}$"
    ),
    "netflix": re.compile(r"^\d+$"),
    "youtube": re.compile(r"^[A-Za-z0-9_-]{11}$"),
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

    VLC_PACKAGE: str = "org.videolan.vlc"
    VLC_ACTIVITY: str = ".StartActivity"

    _MEDIA_PACKAGES: Tuple[str, ...] = (
        PRIME_VIDEO_PACKAGE, YOUTUBE_PACKAGE, NETFLIX_PACKAGE, VLC_PACKAGE,
    )

    supports_enqueue = False
    supported_methods = frozenset({
        "youtube", "prime_video", "netflix", "video", "glob",
        "volume_up", "volume_down", "pause",
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
        sessions = await self._shell_capture("dumpsys media_session")
        if sessions is None or not _active_session_is_playing(sessions):
            return False
        activities = await self._shell_capture("dumpsys activity activities")
        if activities is None:
            return False
        return _foreground_is_media_app(activities, self._MEDIA_PACKAGES)

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


_PLAYBACK_STATE_PATTERN = re.compile(r"PlaybackState\s*\{\s*state=(\d+)")


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


def _active_session_is_playing(dumpsys_output: str) -> bool:
    """Return True if any session in `dumpsys media_session` is state=3.

    Android's MediaSession states: 0=none, 1=stopped, 2=paused, 3=playing,
    4=fast-forwarding, 5=rewinding, 6=buffering, 7=error, 8=connecting.
    Only 3 indicates actual playback.

    Pattern is deliberately loose: different Fire OS versions format the
    containing field with or without a leading `state=` prefix.
    """
    for match in _PLAYBACK_STATE_PATTERN.finditer(dumpsys_output):
        if match.group(1) == "3":
            return True
    return False


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
