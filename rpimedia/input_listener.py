import asyncio
import threading
import signal
import time
import keyboard
from typing import Dict
from . import event_bus as eb

# If a key-down arrives for an already-pressed scan code AND it's been
# longer than this since the last key-down for that code, the OS
# autorepeat stream has stopped — treat it as a fresh press. Linux
# kernel autorepeat is 25-30Hz (~33ms gap), so 5s is over two orders of
# magnitude above the largest plausible inter-repeat interval. This
# cannot be tripped by GC pauses or scheduling jitter on the Pi short
# of a multi-second freeze. Worst case if it ever is tripped: one
# spurious fire, then the key re-enters the pressed set and subsequent
# repeats are blocked again. Bounded — never a runaway.
_AUTOREPEAT_RECOVERY_SECONDS = 5.0


class InputListener:
    def __init__(self, event_bus: eb.EventBus | None = None):
        """Initialize the InputListener with an event bus."""
        self.event_bus = event_bus or eb.EventBus()
        self._shutdown_event = threading.Event()
        self._loop = None
        # scan_code -> monotonic time of last observed key-down.
        # Presence in the dict means "currently considered held". An
        # entry is cleared by an explicit key-up, OR refreshed by every
        # autorepeat down (so a stuck-key autorepeat keeps refreshing
        # the timestamp and stays blocked indefinitely). Keyed on
        # scan_code rather than name because scan_code is stable across
        # modifier state.
        self._pressed_codes: Dict[int, float] = {}
        self._lock = threading.Lock()

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

        # Hook key-down and key-up. We need both so we can distinguish a
        # genuine press from OS autorepeat (see handle_key_event).
        keyboard.on_press(self.handle_key_event)
        keyboard.on_release(self.handle_key_release)

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
        if self._loop is None:
            return

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

    def handle_key_release(self, e):
        """Clear pressed-key state when the OS reports a key-up."""
        with self._lock:
            self._pressed_codes.pop(e.scan_code, None)

    def handle_key_event(self, e):
        """Handle a key-down, suppressing OS autorepeat.

        A real key press → release → press always carries a key-up event
        between presses, so removing the code from _pressed_codes on
        release lets quick re-presses of the same key (e.g. volume up)
        through. OS autorepeat has no intervening release, so repeated
        downs for an already-pressed code are dropped. The recovery
        clause handles the failure case where a key-up is never delivered
        (wireless link drop, dongle desync) — once the autorepeat stream
        actually pauses for _AUTOREPEAT_RECOVERY_SECONDS, the next down
        is treated as fresh, guaranteeing the key never goes permanently
        inert.
        """
        if self._loop is None:
            return

        now = time.monotonic()
        with self._lock:
            last_down = self._pressed_codes.get(e.scan_code)
            self._pressed_codes[e.scan_code] = now
            if (
                last_down is not None
                and (now - last_down) <= _AUTOREPEAT_RECOVERY_SECONDS
            ):
                return

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
