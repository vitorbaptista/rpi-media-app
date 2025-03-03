import asyncio
from typing import Tuple, Dict, Optional


class EventBus:
    def __init__(self):
        self._queue = asyncio.Queue()

    async def add_event(self, event_kind: str, event_data: Dict) -> None:
        """Add an event to the bus."""
        await self._queue.put((event_kind, event_data))

    async def get_event(
        self, timeout: Optional[float] = None
    ) -> Optional[Tuple[str, Dict]]:
        """Get the next event from the bus."""
        try:
            if timeout is not None:
                return await asyncio.wait_for(self._queue.get(), timeout=timeout)
            else:
                return await self._queue.get()
        except asyncio.TimeoutError:
            return None
