# Write a CLI using Click to configure the media controller

import asyncio
import pathlib
import tomllib
import click

from . import controller
from . import event_bus as eb
from . import input_listener


CONFIG_PATH = pathlib.Path(__file__).parent.parent / "config.toml"


def _load_config():
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


@click.command()
def main():
    """Run the media controller."""

    async def run_all():
        # Create EventBus inside the async context to ensure it uses the right event loop
        event_bus = eb.EventBus()
        config = _load_config()
        ctrl = controller.Controller(config=config, event_bus=event_bus)
        listener = input_listener.InputListener(event_bus=event_bus)

        # Create tasks for the controller and keyboard input handler
        controller_task = asyncio.create_task(ctrl.run())
        keyboard_task = asyncio.create_task(listener.run())

        try:
            # Wait for all tasks to complete
            await asyncio.gather(controller_task, keyboard_task)
        except asyncio.CancelledError:
            print("Tasks cancelled, shutting down...")

    try:
        asyncio.run(run_all())
    except KeyboardInterrupt:
        print("\nKeyboard interrupt received, shutting down...")
    finally:
        # Ensure terminal is back to normal state
        print("Application terminated.")


if __name__ == "__main__":
    main()
