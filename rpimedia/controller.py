import logging
import random
import glob
import os
import asyncio
from typing import Any, Dict, List, Optional
from . import devices
from . import event_bus as eb

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")


class Controller:
    MAX_ENQUEUED_VIDEOS: int = 3

    def __init__(
        self,
        config: Dict[str, Any],
        event_bus: Optional[eb.EventBus] = None,
        device: Optional[devices.Device] = None,
    ) -> None:
        self.event_bus: eb.EventBus = event_bus or eb.EventBus()
        self._config: Dict[str, Any] = config
        self.device: devices.Device = device or devices.ChromecastDevice()

        # For some reason, the random.shuffle() is always picking the same
        # video. I'm trying to explicitly set a random seed now.
        random.seed()

    async def run(self) -> None:
        while True:
            event = await self.event_bus.get_event()
            if event is not None:
                event_kind, event_data = event
                await self.handle_event(event_kind, event_data)

            # Add a small delay to prevent CPU spinning
            await asyncio.sleep(0.01)

    async def handle_event(
        self, event_kind: str, event_data: Dict[str, Any]
    ) -> Optional[asyncio.subprocess.Process]:
        logger.debug(f"Handling event: {event_kind} {event_data}")

        match event_kind:
            case "keyboard_input":
                return await self._handle_key_press(event_data)
            case _:
                method = event_kind
                return await self._handle_method_call(method, event_data)

    async def _handle_key_press(
        self, event_data: Dict[str, Any]
    ) -> Optional[asyncio.subprocess.Process]:
        key = event_data["key"]

        binding = self._config["remote"]["bindings"].get(key)
        key_config = self._config["remote"]["keys"].get(binding)
        if not binding or not key_config:
            logger.debug(f"No configuration for key: {key}")
            return None

        method = key_config["method"]
        key_params = key_config["params"]
        if not isinstance(key_params, list):
            key_params = [key_params]

        params = {
            "params": key_params,
            "max_enqueued_videos": event_data.get("max_enqueued_videos"),
        }

        # We shuffle the params to avoid always playing the same video
        random.shuffle(params["params"])

        return await self._handle_method_call(method, params)

    async def _handle_method_call(
        self, method: str, data: Dict[str, Any]
    ) -> Optional[asyncio.subprocess.Process]:
        params = data["params"]

        if method not in self.device.supported_methods:
            logger.warning(
                f"method {method!r} is not supported by "
                f"{self.device.__class__.__name__}; ignoring"
            )
            return None

        match method:
            case "youtube":
                first_video = params[0]
                max_enqueued_videos = data.get("max_enqueued_videos")
                if max_enqueued_videos is None:
                    max_enqueued_videos = self.MAX_ENQUEUED_VIDEOS
                else:
                    assert (
                        max_enqueued_videos >= 0
                    ), f"Max enqueued videos must be greater or equal to 0 (was {max_enqueued_videos})"

                result = await self.device.play_youtube(first_video)

                if self.device.supports_enqueue:
                    for video_id in params[1:max_enqueued_videos]:
                        await self.device.enqueue_youtube(video_id)
                        await asyncio.sleep(2)

                return result
            case "video":
                video = random.choice(params)
                return await self.device.play_video(video)
            case "volume_up":
                assert len(params) == 1, "Volume up must have exactly one parameter"
                return await self.device.volume_up(int(params[0]))
            case "volume_down":
                assert len(params) == 1, "Volume down must have exactly one parameter"
                return await self.device.volume_down(int(params[0]))
            case "url":
                return await self.device.play_url(params[0])
            case "glob":
                return await self.play_globs(params)
            case "prime_video":
                return await self.device.play_prime_video(params[0])
            case "netflix":
                return await self.device.play_netflix(params[0])
            case "globoplay":
                return await self.device.play_globoplay(params[0])
            case "pause":
                return await self.device.pause()
            case "set_hearing_aids":
                assert len(params) == 1, (
                    "set_hearing_aids must have exactly one parameter "
                    "(on|off|toggle)"
                )
                # Shape is enforced lowercase by _PARAM_VALIDATORS.
                arg = params[0]
                if arg == "toggle":
                    currently_on = await self.device.is_hearing_aid_connected()
                    enabled = not currently_on
                else:
                    enabled = arg == "on"
                await self.device.set_hearing_aids(enabled)
                return None
            case _:
                logger.debug(f"Unknown method: {method}")
                return None

    async def play_globs(self, glob_paths: List[str]) -> Optional[asyncio.subprocess.Process]:
        logger.debug(f"Playing globs in {glob_paths}")
        glob_paths = [os.path.join(BASE_DIR, glob_path) for glob_path in glob_paths]
        video_paths: List[str] = sorted(list(set([
            path
            for glob_path in glob_paths
            for path in glob.glob(glob_path, recursive=True)
        ])))
        if not video_paths:
            logger.error(f"No video found for globs {glob_paths}")
            return None

        video_path = random.choice(video_paths)
        return await self.device.play_video(video_path)
