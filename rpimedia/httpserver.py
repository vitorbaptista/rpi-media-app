import logging
import socket
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

logger = logging.getLogger(__name__)


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
        handler = partial(SimpleHTTPRequestHandler, directory=self._root)
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
