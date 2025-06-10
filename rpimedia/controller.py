import logging
import random
import glob
import os
import asyncio
import subprocess
import functools
from typing import Any, Callable, Dict, List, Optional, TypeVar
from . import event_bus as eb

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")

T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])


def _debounce(wait_time: float) -> Callable[[F], F]:
    """
    Decorator that prevents a function from being called more than once every wait_time seconds.
    For async functions.
    """

    def decorator(func: F) -> F:
        last_called: Dict[Any, float] = {}

        @functools.wraps(func)
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            current_time = asyncio.get_event_loop().time()
            key = args[0] if args else None  # Use first arg as key
            if key is None:
                return await func(self, *args, **kwargs)

            last_time = last_called.get(key, 0)
            if current_time - last_time < wait_time:
                return

            last_called[key] = current_time
            return await func(self, *args, **kwargs)

        return wrapper  # type: ignore

    return decorator


class Controller:
    MAX_ENQUEUED_VIDEOS: int = 3

    def __init__(
        self, config: Dict[str, Any], event_bus: Optional[eb.EventBus] = None
    ) -> None:
        self.event_bus: eb.EventBus = event_bus or eb.EventBus()
        self._config: Dict[str, Any] = config

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
                return await self._handle_key_press(event_data["key"])
            case _:
                method = event_kind
                params = event_data.get("params", [])
                return await self._handle_method_call(method, params)

    @_debounce(wait_time=20)
    async def _handle_key_press(self, key: str) -> Optional[asyncio.subprocess.Process]:
        binding = self._config["remote"]["bindings"].get(key)
        key_config = self._config["remote"]["keys"].get(binding)
        if not binding or not key_config:
            logger.debug(f"No configuration for key: {key}")
            return None

        method = key_config["method"]
        params = key_config["params"]

        # We shuffle the params to avoid always playing the same video
        random.shuffle(params)

        return await self._handle_method_call(method, params)

    async def _handle_method_call(
        self, method: str, params: List[str]
    ) -> Optional[asyncio.subprocess.Process]:
        match method:
            case "youtube":
                first_video = params[0]
                result = await self.play_youtube(first_video)

                # Enqueue the remaining videos if there are any
                for video_id in params[1 : self.MAX_ENQUEUED_VIDEOS]:
                    await self.enqueue_youtube(video_id)
                    await asyncio.sleep(2)

                return result
            case "video":
                video = random.choice(params)
                return await self.play_video(video)
            case "volume_up":
                assert len(params) == 1, "Volume up must have exactly one parameter"
                return await self.volume_up(int(params[0]))
            case "volume_down":
                assert len(params) == 1, "Volume down must have exactly one parameter"
                return await self.volume_down(int(params[0]))
            case "url":
                url = params[0]
                return await self.play_url(url)
            case "glob":
                glob_path = params[0]
                return await self.play_glob(glob_path)
            case _:
                logger.debug(f"Unknown method: {method}")
                return None

    async def play_youtube(self, video_id: str) -> Optional[asyncio.subprocess.Process]:
        # TODO: Adicionar uma imagem enquanto ele não carrega, pois demora alguns segundos
        logger.debug(f"Playing youtube video {video_id}")
        return await self._run_command_async(
            [
                "catt",
                "cast",
                f"https://www.youtube.com/watch?v={video_id}",
            ]
        )

    async def enqueue_youtube(
        self, video_id: str
    ) -> Optional[asyncio.subprocess.Process]:
        logger.debug(f"Enqueuing youtube video {video_id}")
        return await self._run_command_async(
            ["catt", "add", f"https://www.youtube.com/watch?v={video_id}"]
        )

    async def play_url(self, url: str) -> Optional[asyncio.subprocess.Process]:
        logger.debug(f"Playing url {url}")
        return await self._run_command_async(["catt", "cast", url])

    async def skip_video(self) -> Optional[asyncio.subprocess.Process]:
        logger.debug("Skipping video")
        return await self._run_command_async(["catt", "skip"])

    async def play_video(self, video_path: str) -> Optional[asyncio.subprocess.Process]:
        logger.debug(f"Playing video {video_path}")
        return await self._run_command_async(
            ["catt", "cast", "--block", video_path], min_execution_time=120
        )

    async def play_glob(self, glob_path: str) -> Optional[asyncio.subprocess.Process]:
        logger.debug(f"Playing glob {glob_path}")
        glob_path = os.path.join(BASE_DIR, glob_path)
        video_paths: List[str] = sorted(glob.glob(glob_path, recursive=True))
        if not video_paths:
            logger.error(f"No video found for glob {glob_path}")
            return None

        video_path = random.choice(video_paths)
        return await self.play_video(video_path)

    async def volume_up(self, volume_step: int) -> Optional[asyncio.subprocess.Process]:
        logger.debug(f"Volume up by {volume_step}")
        return await self._run_command_async(["catt", "volumeup", f"{volume_step}"])

    async def volume_down(
        self, volume_step: int
    ) -> Optional[asyncio.subprocess.Process]:
        logger.debug(f"Volume down by {volume_step}")
        return await self._run_command_async(["catt", "volumedown", f"{volume_step}"])

    async def _run_command_async(
        self,
        command: List[str],
        min_execution_time: Optional[float] = None,
        _attempts: int = 0,
    ) -> Optional[asyncio.subprocess.Process]:
        max_attempts = 3
        process: Optional[asyncio.subprocess.Process] = None
        try:
            _attempts += 1
            if _attempts > max_attempts:
                logger.error(
                    f"Process finished too quickly after {max_attempts} attempts. Giving up."
                )
                return None

            process = await asyncio.create_subprocess_exec(*command)

            if not min_execution_time:
                return process

            # Wait for process with timeout
            await asyncio.wait_for(process.wait(), timeout=min_execution_time)

            logger.info(
                f"Process finished too quickly running again (attempt {_attempts}/{max_attempts})"
            )
            return await self._run_command_async(command, min_execution_time, _attempts)

        except asyncio.TimeoutError:
            # Process is still running after the timeout. This is fine.
            return process
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            logger.debug(f"Failed to run command: {e}")
            return None
