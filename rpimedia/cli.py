# Write a CLI using Click to configure the media controller

import asyncio
import os
import pathlib
import sys
import tomllib
from datetime import datetime, time as dtime
import click
import logging

from . import controller
from . import devices
from . import event_bus as eb
from . import input_listener
from . import ipc_listener


# Configure logging to suppress asyncio debug messages
logging.getLogger("asyncio").setLevel(logging.INFO)

CONFIG_PATH = pathlib.Path(__file__).parent.parent / "config.toml"


def _load_config():
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


@click.group()
def cli():
    pass


@cli.command()
def start():
    """Start the media controller."""

    async def run_all():
        # Create EventBus inside the async context to ensure it uses the right event loop
        event_bus = eb.EventBus()
        config = _load_config()
        device = devices.build_device(config)
        devices.validate_config(config, device)
        ctrl = controller.Controller(
            config=config, event_bus=event_bus, device=device
        )
        listener = input_listener.InputListener(event_bus=event_bus)
        ipc_event_listener = ipc_listener.IPCListener(event_bus=event_bus)

        # Create tasks for the controller and input handlers
        controller_task = asyncio.create_task(ctrl.run())
        keyboard_task = asyncio.create_task(listener.run())
        ipc_task = asyncio.create_task(ipc_event_listener.run())

        try:
            logging.info("Starting media controller...")
            # Wait for all tasks to complete
            await asyncio.gather(controller_task, keyboard_task, ipc_task)
        except asyncio.CancelledError:
            logging.info("Shutting down...")

    try:
        asyncio.run(run_all())
    except KeyboardInterrupt:
        logging.info("\nKeyboard interrupt received, shutting down...")
    finally:
        # Ensure terminal is back to normal state
        logging.info("Application terminated.")


@cli.command(name="send_event")
@click.argument("event_kind")
@click.argument("event_data", nargs=-1)
@click.option(
    "--max-enqueued-videos",
    type=click.IntRange(min=0),
    help="Maximum number of videos to enqueue (only applies to youtube events)",
)
def send_event(
    event_kind: str, event_data: tuple[str, ...], max_enqueued_videos: int | None
):
    """Send an event to the running media controller instance.

    This command allows sending events to a running media controller instance through IPC.
    The event_kind determines what type of event to send, and event_data provides the
    necessary parameters for that event type.

    Examples:
        $ rpimedia send_event keyboard_input a
        $ rpimedia send_event keyboard_input b --max-enqueued-videos 5
        $ rpimedia send_event youtube 4CAmwaFJo6k
        $ rpimedia send_event volume_up 15
    """

    async def send(event_kind, event_data, max_enqueued_videos):
        # For keyboard events, we need to wrap the key in the expected format
        if event_kind == "keyboard_input":
            assert (
                len(event_data) == 1
            ), "Keyboard input must have exactly one parameter"
            event_data = {
                "key": event_data[0],
                "max_enqueued_videos": max_enqueued_videos,
            }
        else:
            params = [event_data] if isinstance(event_data, str) else event_data
            event_data = {"params": params}

        success = await ipc_listener.IPCListener.send_event(event_kind, event_data)
        if not success:
            click.echo("Failed to send event", err=True)
            exit(1)

    try:
        asyncio.run(send(event_kind, event_data, max_enqueued_videos))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        exit(1)


@cli.command(name="is_playing")
def is_playing():
    """Exit 0 if the configured device is playing, 1 otherwise.

    Designed for shell composition in cron, e.g.:

        rpimedia is_playing || rpimedia send_event keyboard_input c

    Retry and timing semantics are device-specific and handled inside the
    device implementation (Chromecast needs multiple attempts because
    catt discovery is flaky; Fire TV does a single adb dumpsys call).
    """

    async def check():
        config = _load_config()
        device = devices.build_device(config)
        try:
            return await device.is_playing()
        except Exception:
            logging.exception("is_playing check failed; treating as idle")
            return False

    playing = asyncio.run(check())
    if playing:
        logging.info("device is playing")
        exit(0)
    logging.info("device is idle")
    exit(1)


@cli.command(name="resume")
def resume():
    """Resume a paused media session in place; no-op otherwise.

    Designed to run before is_playing in cron, e.g.:

        rpimedia resume
        rpimedia is_playing || rpimedia send_event keyboard_input c

    If the foreground media app is paused, sends MEDIA_PLAY. Otherwise
    (playing, idle, launcher in front, no device, etc.) does nothing and
    exits 0 — the next is_playing check then drives the existing fallback.
    """

    async def run():
        config = _load_config()
        device = devices.build_device(config)
        try:
            await device.resume()
        except Exception:
            logging.exception("resume failed")

    asyncio.run(run())


@cli.command(name="hearing_aids_schedule")
@click.argument("window_start")
@click.argument("window_end")
def hearing_aids_schedule(window_start: str, window_end: str):
    """Connect/disconnect hearing aids on a daily window.

    Designed for cron: runs frequently and acts only on a transition into
    or out of the [WINDOW_START, WINDOW_END) interval (HH:MM, 24h).
    Exception: the very first run on a new install bootstraps its state
    file from the live hearing-aid status, then immediately enforces the
    schedule against it — so installing during the off-window with the
    aid still connected will trigger one disconnect.

    The last applied state is persisted in
    ``$XDG_STATE_HOME/rpimedia/hearing_aids.state`` (default
    ``~/.local/state/rpimedia/...``); transient adb/UI failures don't
    update it, so the next cron tick retries automatically.

    Example::

        rpimedia hearing_aids_schedule 05:00 11:00
    """
    try:
        start = _parse_hhmm(window_start)
        end = _parse_hhmm(window_end)
    except ValueError as e:
        raise click.BadParameter(str(e))

    state_path = _hearing_aids_state_path()
    now = datetime.now().time()
    desired = "on" if _in_window(now, start, end) else "off"

    async def run():
        config = _load_config()
        device = devices.build_device(config)

        last = _read_state(state_path)
        if last is None:
            # Bootstrap: trust the live state on first run so we don't
            # interrupt the user with a UI flash to set state to what's
            # already true.
            actual_on = await device.is_hearing_aid_connected()
            last = "on" if actual_on else "off"
            _write_state(state_path, last)
            logging.info(f"hearing_aids_schedule: bootstrapped state={last}")

        if desired == last:
            logging.info(
                f"hearing_aids_schedule: state unchanged ({desired}); skipping"
            )
            return True

        logging.info(
            f"hearing_aids_schedule: transition {last} -> {desired}"
        )
        success = await device.set_hearing_aids(desired == "on")
        if not success:
            logging.error(
                f"hearing_aids_schedule: failed to apply {desired}; "
                "leaving state file unchanged so cron retries"
            )
            return False
        _write_state(state_path, desired)
        logging.info(f"hearing_aids_schedule: applied {desired}")
        return True

    ok = asyncio.run(run())
    if not ok:
        sys.exit(1)


def _parse_hhmm(s: str) -> dtime:
    try:
        return datetime.strptime(s, "%H:%M").time()
    except ValueError:
        raise ValueError(
            f"invalid time {s!r}: expected HH:MM in 24-hour format"
        )


def _in_window(now: dtime, start: dtime, end: dtime) -> bool:
    if start <= end:
        return start <= now < end
    # Window crosses midnight (e.g. 22:00 → 06:00).
    return now >= start or now < end


def _hearing_aids_state_path() -> pathlib.Path:
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser(
        "~/.local/state"
    )
    return pathlib.Path(base) / "rpimedia" / "hearing_aids.state"


def _read_state(path: pathlib.Path) -> str | None:
    try:
        text = path.read_text().strip()
    except FileNotFoundError:
        return None
    return text or None


def _write_state(path: pathlib.Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(value)
    tmp.replace(path)


if __name__ == "__main__":
    cli()
