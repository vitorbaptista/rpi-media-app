# Write a CLI using Click to configure the media controller

import asyncio
import pathlib
import tomllib
import click
import logging

from . import controller
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
        ctrl = controller.Controller(config=config, event_bus=event_bus)
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


if __name__ == "__main__":
    cli()
