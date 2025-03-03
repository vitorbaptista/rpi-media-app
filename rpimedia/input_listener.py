import asyncio
import threading
import signal
import keyboard
from . import event_bus as eb


class InputListener:
    def __init__(self, event_bus: eb.EventBus = None):
        """Initialize the InputListener with an event bus."""
        self.event_bus = event_bus or eb.EventBus()
        self._shutdown_event = threading.Event()
        self._loop = None

    async def run(self):
        """Run the input listener in a loop until shutdown is requested."""
        print(
            "Keyboard input handler started. Press keys to generate events (press 'q' to quit, ESC to exit)."
        )
        self._loop = asyncio.get_running_loop()

        # Set up signal handlers for graceful shutdown
        for sig in (signal.SIGINT, signal.SIGTERM):
            self._loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(
                    self.handle_shutdown(f"Received signal {s.name}")
                ),
            )

        # Hook the keyboard event
        keyboard.on_press(self.handle_key_event)

        try:
            # Keep this coroutine alive until shutdown is requested
            while not self._shutdown_event.is_set():
                await asyncio.sleep(0.1)
        finally:
            # Unhook the keyboard when this coroutine exits
            keyboard.unhook_all()

        print("Keyboard input handler stopped.")

    async def process_key(self, key):
        """Process the key and create an event in the event bus."""
        # Create an event with the key pressed
        event_data = {"key": key, "timestamp": self._loop.time()}

        await self.event_bus.add_event("keyboard_input", event_data)

    async def handle_shutdown(self, message):
        """Handle graceful shutdown."""
        print(f"\n{message}. Exiting...")
        self._shutdown_event.set()
        # Cancel all tasks except the current one to allow the application to exit
        for task in asyncio.all_tasks():
            if task != asyncio.current_task():
                task.cancel()

    def handle_key_event(self, e):
        """Handle keyboard events and convert them to system events."""
        key_char = e.name

        # Handle special cases
        if key_char == "esc":
            # Schedule shutdown on ESC
            self._loop.call_soon_threadsafe(
                lambda: asyncio.create_task(
                    self.handle_shutdown("ESC key pressed, shutting down")
                )
            )
            return

        if key_char == "q":
            # Schedule shutdown on 'q'
            self._loop.call_soon_threadsafe(
                lambda: asyncio.create_task(
                    self.handle_shutdown("Q key pressed, shutting down")
                )
            )
            return

        # For all other keys, create an event
        self._loop.call_soon_threadsafe(
            lambda k=key_char: asyncio.create_task(self.process_key(k))
        )
