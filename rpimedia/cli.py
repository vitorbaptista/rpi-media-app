# Write a CLI using Click to configure the media controller

import asyncio
import click

from . import controller
from . import event_bus as eb
from . import input_listener


@click.command()
def main():
    """Run the media controller."""

    async def run_all():
        # Create EventBus inside the async context to ensure it uses the right event loop
        event_bus = eb.EventBus()
        ctrl = controller.Controller(event_bus=event_bus)
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
