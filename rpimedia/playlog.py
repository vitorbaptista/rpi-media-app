"""Best-effort external play log backed by Supabase (PostgREST).

The RPi runs on a read-only filesystem, so there is no durable place to
append a local log. Every event is POSTed to a Supabase table instead.

Two sources feed the same table:

* ``command`` rows — emitted by the controller whenever *this* codebase
  launches something. They carry ``media_id`` (the ``method:param`` form
  used in config, so rows join back to curation) and the ``source``
  button/cron that triggered it.
* ``observed`` rows — emitted by the ``is_playing`` cron tick from what
  ``dumpsys`` actually reports, and only when the app/state *changed*
  since the last observed row. This is what captures playback started
  directly on the Fire TV (e.g. someone navigating it by hand).

Everything here is strictly best-effort: a network failure, missing
credentials, or a malformed response must never raise into — or slow
down — playback. Failures are downgraded to a log line. A read-only FS
means we cannot durably buffer a dropped POST, so a rare miss is
accepted (change-only volume makes this tolerable).

Credentials come from the environment (``SUPABASE_URL`` /
``SUPABASE_KEY``), optionally seeded from a gitignored ``.env`` in the
project root. The table name lives under ``[supabase]`` in
``config.toml``; absent credentials silently disable logging.
"""

import logging
import os
from typing import Any, Dict, Optional

import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Seed os.environ from a project-root .env if present. Real environment
# variables take precedence; absent file is a no-op. Done at import so it
# works uniformly under systemd and cron (both run with cwd = project root).
load_dotenv()

# Generous: command logging is fire-and-forget (never blocks playback) and
# the observed path runs in the latency-tolerant cron tick, so we'd rather
# wait out a Supabase cold start than drop a row that would have succeeded.
_TIMEOUT = 10.0

# Methods worth recording as command events; volume/pause/hearing-aid
# control are not "what's playing" and are skipped.
COMMAND_METHODS = frozenset(
    {"youtube", "video", "url", "glob", "prime_video", "netflix", "globoplay"}
)


def _settings(config: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Return resolved Supabase settings, or None if logging is off.

    Missing credentials are the single off-switch and stay silent
    (debug-level), so a device without a ``.env`` simply doesn't log
    rather than warning every cron tick.
    """
    url = os.environ.get("SUPABASE_URL")
    # Accept the modern publishable-key name as well as the generic one.
    key = os.environ.get("SUPABASE_KEY") or os.environ.get(
        "SUPABASE_PUBLISHABLE_KEY"
    )
    if not url or not key:
        logger.debug("playlog off: SUPABASE_URL/SUPABASE_KEY not set")
        return None
    table = config.get("supabase", {}).get("table", "play_log")
    return {"url": url.rstrip("/"), "key": key, "table": table}


def _headers(settings: Dict[str, str]) -> Dict[str, str]:
    return {
        "apikey": settings["key"],
        "Authorization": f"Bearer {settings['key']}",
        "Content-Type": "application/json",
    }


def _endpoint(settings: Dict[str, str]) -> str:
    return f"{settings['url']}/rest/v1/{settings['table']}"


async def _insert(settings: Dict[str, str], row: Dict[str, Any]) -> None:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            _endpoint(settings),
            headers={**_headers(settings), "Prefer": "return=minimal"},
            json=row,
        )
        resp.raise_for_status()


async def _last_observed(settings: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Return the most recent observed row (app+state), or None.

    The observed path reads this back to log change-only — there is no
    local state file to compare against on a read-only FS.
    """
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            _endpoint(settings),
            headers=_headers(settings),
            params={
                "kind": "eq.observed",
                "order": "ts.desc",
                "limit": "1",
                "select": "app,state",
            },
        )
        resp.raise_for_status()
        rows = resp.json()
    return rows[0] if rows else None


async def log_command(
    config: Dict[str, Any],
    *,
    method: str,
    param: str,
    source: Optional[str] = None,
) -> None:
    """Record an intent event for media this codebase just launched."""
    settings = _settings(config)
    if settings is None:
        return
    try:
        await _insert(
            settings,
            {
                "kind": "command",
                "app": method,
                "media_id": f"{method}:{param}",
                "source": source,
            },
        )
    except Exception:
        logger.warning("playlog: failed to record command event", exc_info=True)


async def log_observed(
    config: Dict[str, Any], *, app: Optional[str], state: str
) -> None:
    """Record a device-observed event, but only when it changed.

    Compares against the last observed row (a Supabase read-back, since the
    read-only FS rules out a local state file). Equal app+state means no
    new row.
    """
    settings = _settings(config)
    if settings is None:
        return
    try:
        prev = await _last_observed(settings)
        if prev and prev.get("app") == app and prev.get("state") == state:
            return
        await _insert(settings, {"kind": "observed", "app": app, "state": state})
    except Exception:
        logger.warning("playlog: failed to record observed event", exc_info=True)
