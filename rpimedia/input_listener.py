import asyncio
import signal
from typing import List, Optional

import evdev
from evdev import InputDevice, ecodes

from . import event_bus as eb


def _key_name(code: int) -> Optional[str]:
    """Map evdev key code to lowercase short name (KEY_A→'a', KEY_1→'1', KEY_ESC→'esc')."""
    raw = ecodes.KEY.get(code)
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)):
        raw = raw[0]
    if not raw.startswith("KEY_"):
        # ecodes.KEY also indexes BTN_* (mouse buttons, power button, gamepad);
        # those aren't typing keys and the controller's config can't bind them.
        return None
    return raw.removeprefix("KEY_").lower()


def _find_keyboards() -> List[InputDevice]:
    """Open every input device that exposes alphabetic keys.

    Filters out mice, gamepads, power buttons, and other EV_KEY-but-not-keyboard
    devices. Presence of KEY_A is the proxy for "typing-style keyboard".
    """
    devices = []
    for path in evdev.list_devices():
        try:
            dev = InputDevice(path)
        except OSError:
            continue
        try:
            keys = dev.capabilities().get(ecodes.EV_KEY, [])
        except OSError:
            dev.close()
            continue
        if ecodes.KEY_A in keys:
            devices.append(dev)
        else:
            dev.close()
    return devices


class InputListener:
    def __init__(self, event_bus: Optional[eb.EventBus] = None):
        """Initialize the InputListener with an event bus."""
        self.event_bus = event_bus or eb.EventBus()
        self._shutdown_event = asyncio.Event()

    async def run(self):
        """Run the input listener until shutdown is requested."""
        print("Keyboard input handler started. Press keys to generate events.")
        loop = asyncio.get_running_loop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(
                sig,
                lambda s=sig: self._request_shutdown(f"Received signal {s.name}"),
            )

        devices = _find_keyboards()
        if not devices:
            print("No keyboard input devices found.")
            return

        listeners = [asyncio.create_task(self._listen(d)) for d in devices]
        shutdown_wait = asyncio.create_task(self._shutdown_event.wait())
        try:
            while not self._shutdown_event.is_set():
                pending = [t for t in listeners if not t.done()]
                if not pending:
                    self._request_shutdown("All input devices disconnected")
                    break
                await asyncio.wait(
                    [shutdown_wait, *pending],
                    return_when=asyncio.FIRST_COMPLETED,
                )
        finally:
            shutdown_wait.cancel()
            for task in listeners:
                task.cancel()
            await asyncio.gather(shutdown_wait, *listeners, return_exceptions=True)
            for dev in devices:
                try:
                    dev.close()
                except OSError:
                    pass

        print("Keyboard input handler stopped.")

    async def _listen(self, device: InputDevice):
        """Stream KEY_DOWN events from `device`. Drops kernel autorepeat (value=2) and releases (value=0)."""
        try:
            async for event in device.async_read_loop():
                if self._shutdown_event.is_set():
                    return
                # value 1 = real DOWN; value 2 = kernel autorepeat (ignore); value 0 = UP (ignore)
                if event.type != ecodes.EV_KEY or event.value != 1:
                    continue
                key_char = _key_name(event.code)
                if key_char is None:
                    continue
                await self.process_key(key_char)
        except (OSError, ValueError):
            # Device disappeared (e.g. dongle unplugged). Other listeners and run() continue.
            return

    async def process_key(self, key: str):
        """Process the key and create an event in the event bus."""
        event_data = {"key": key, "timestamp": asyncio.get_running_loop().time()}
        await self.event_bus.add_event("keyboard_input", event_data)

    def _request_shutdown(self, message: str):
        """Initiate graceful shutdown. Idempotent; safe from sync handlers and async tasks."""
        if self._shutdown_event.is_set():
            return
        print(f"\n{message}. Exiting...")
        self._shutdown_event.set()
        for task in asyncio.all_tasks():
            if task != asyncio.current_task():
                task.cancel()
