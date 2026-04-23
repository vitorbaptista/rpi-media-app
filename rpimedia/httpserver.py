import logging
import os
import socket
import threading
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class _RangedFile:
    """File wrapper that exposes only `limit` bytes to downstream readers."""

    def __init__(self, f, limit: int) -> None:
        self._f = f
        self._remaining = limit

    def read(self, n: int = -1) -> bytes:
        if self._remaining <= 0:
            return b""
        if n < 0 or n > self._remaining:
            n = self._remaining
        data = self._f.read(n)
        self._remaining -= len(data)
        return data

    def close(self) -> None:
        self._f.close()


class RangeRequestHandler(SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler with `Range` header support.

    Video players (VLC, ExoPlayer, etc.) issue Range requests for seeking
    and progressive download. Stdlib's SimpleHTTPRequestHandler silently
    returns the full file with 200 instead of honoring the range — enough
    clients to time out or show black before playback starts.
    """

    def send_head(self):  # type: ignore[override]
        range_header = self.headers.get("Range")
        if not range_header:
            return super().send_head()
        path = self.translate_path(self.path)
        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return None
        try:
            size = os.fstat(f.fileno()).st_size
            parsed = _parse_byte_range(range_header, size)
            if parsed is None:
                # Malformed header — RFC 7233 allows falling through to 200.
                f.close()
                return super().send_head()
            start, end = parsed
            if start is None or end is None:
                f.close()
                self.send_response(
                    HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE
                )
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return None
            f.seek(start)
            self.send_response(HTTPStatus.PARTIAL_CONTENT)
            self.send_header("Content-Type", self.guess_type(path))
            self.send_header(
                "Content-Range", f"bytes {start}-{end}/{size}"
            )
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
        except Exception:
            f.close()
            raise
        return _RangedFile(f, end - start + 1)

    def copyfile(self, source, outputfile):  # type: ignore[override]
        # Clients (notably VLC) frequently abort mid-stream when seeking;
        # swallow the resulting BrokenPipe to keep the journal clean.
        try:
            super().copyfile(source, outputfile)
        except (BrokenPipeError, ConnectionResetError):
            pass


def _parse_byte_range(
    header: str, size: int
) -> Optional[Tuple[Optional[int], Optional[int]]]:
    """Parse an HTTP `Range: bytes=…` header.

    Returns `None` when the header isn't parseable at all (caller should
    fall through to 200). Returns `(None, None)` when the range is
    syntactically valid but unsatisfiable (caller should respond 416).
    Otherwise returns `(start, end)` inclusive, clamped to file size.
    """
    units, _, spec = header.partition("=")
    if units.strip().lower() != "bytes":
        return None
    start_s, _, end_s = spec.partition("-")
    try:
        if start_s:
            start = int(start_s)
            end = int(end_s) if end_s else size - 1
        else:
            if not end_s:
                return None
            start = max(size - int(end_s), 0)
            end = size - 1
    except ValueError:
        return None
    end = min(end, size - 1)
    if start > end or start >= size or start < 0:
        return None, None
    return start, end


class VideoServer:
    """Serves a directory tree over HTTP, used to stream local video files
    to Fire TV (via VLC). Chromecast has its own HTTP serving inside catt,
    so only FireTVDevice uses this.

    Started lazily on first use; thread runs for the lifetime of the process.
    """

    def __init__(self, root: str) -> None:
        self._root = root
        self._server: Optional[ThreadingHTTPServer] = None

    def ensure_running(self, bind_host: str) -> int:
        """Start the server bound to `bind_host` if not already running.

        Binds to a specific interface rather than 0.0.0.0 so the directory
        isn't reachable on unrelated networks (e.g. Tailscale) — videos are
        only useful on the same LAN as the Fire TV.
        """
        if self._server is not None:
            return self._server.server_address[1]
        handler = partial(RangeRequestHandler, directory=self._root)
        self._server = ThreadingHTTPServer((bind_host, 0), handler)
        port = self._server.server_address[1]
        thread = threading.Thread(
            target=self._server.serve_forever,
            name="rpimedia-video-http",
            daemon=True,
        )
        thread.start()
        logger.info(
            f"video HTTP server listening on {bind_host}:{port}, "
            f"root={self._root}"
        )
        return port


def detect_local_ip(target_ip: str) -> Optional[str]:
    """Return the local IP of the interface that routes to `target_ip`.

    Uses the "connect a UDP socket, read its source IP" trick — no packets
    are sent because UDP connect() only sets the default route; the kernel
    picks the outbound interface and fills in the source address. Passing
    the specific target (e.g. the Fire TV) avoids returning a Tailscale or
    other VPN address that the target can't reach.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect((target_ip, 9))
            return s.getsockname()[0]
    except OSError as e:
        logger.warning(f"could not detect local IP toward {target_ip}: {e}")
        return None
