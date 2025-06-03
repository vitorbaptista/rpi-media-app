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
        self._current_process: Optional[asyncio.subprocess.Process] = None
        self._current_process_command: Optional[List[str]] = None
        self._config: Dict[str, Any] = config
        self._last_key_pressed: Optional[str] = None

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

    @_debounce(wait_time=20)
    async def handle_event(
        self, event_kind: str, event_data: Dict[str, Any]
    ) -> Optional[asyncio.subprocess.Process]:
        logger.debug(f"Handling event: {event_kind} {event_data}")

        match event_kind:
            case "keyboard_input":
                return await self._handle_key_press(event_data["key"])
            case _:
                logger.debug(f"Unknown event: {event_kind} {event_data}")
                return None

    async def _handle_key_press(self, key: str) -> Optional[asyncio.subprocess.Process]:
        """Handle a key press using the configuration"""
        binding = self._config["remote"]["bindings"].get(key)
        key_config = self._config["remote"]["keys"].get(binding)
        if not binding or not key_config:
            logger.debug(f"No configuration for key: {key}")
            return None

        method = key_config["method"]
        params = key_config["params"]
        match method:
            case "youtube":
                # Randomly shuffle the params list
                shuffled_videos: List[str] = list(params)
                random.shuffle(shuffled_videos)

                first_video = shuffled_videos[0]
                result = await self.play_youtube(first_video)

                # Enqueue the remaining videos if there are any
                for video_id in shuffled_videos[1 : self.MAX_ENQUEUED_VIDEOS]:
                    await self.enqueue_youtube(video_id)
                    await asyncio.sleep(2)

                return result
            case "video":
                video = random.choice(params)
                return await self.play_video(video)
            case "volume_up":
                return await self.volume_up(params)
            case "volume_down":
                return await self.volume_down(params)
            case "url":
                url = random.choice(params)
                return await self.play_url(url)
            case "glob":
                glob_path = random.choice(params)
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
        return await self._run_command(
            ["cvlc", "--no-keyboard-events", "--loop", "--avcodec-hw=none", video_path]
        )

    async def play_glob(self, glob_path: str) -> Optional[asyncio.subprocess.Process]:
        logger.debug(f"Playing glob {glob_path}")
        glob_path = os.path.join(BASE_DIR, glob_path)
        video_paths: List[str] = sorted(glob.glob(glob_path, recursive=True))
        if not video_paths:
            logger.error(f"No video found for glob {glob_path}")
            return None

        video_path = random.choice(video_paths)
        return await self._run_command_async(
            ["catt", "cast", "--block", video_path], min_execution_time=120
        )

    async def volume_up(self, volume_step: int) -> Optional[asyncio.subprocess.Process]:
        logger.debug(f"Volume up by {volume_step}")
        return await self._run_command_async(["catt", "volumeup", f"{volume_step}"])

    async def volume_down(
        self, volume_step: int
    ) -> Optional[asyncio.subprocess.Process]:
        logger.debug(f"Volume down by {volume_step}")
        return await self._run_command_async(["catt", "volumedown", f"{volume_step}"])

    async def _run_command(
        self, command: List[str]
    ) -> Optional[asyncio.subprocess.Process]:
        if self._current_process_command == command:
            # Ignore if the command is the same as the current one
            logger.debug("Ignoring repeated command")
            return None

        if self._current_process:
            try:
                self._current_process.terminate()
            except Exception:
                pass
            finally:
                self._current_process = None
                self._current_process_command = None

        self._current_process = await self._run_command_async(command)
        if self._current_process:
            self._current_process_command = command
        return self._current_process

    async def _run_command_async(
        self,
        command: List[str],
        min_execution_time: Optional[float] = None,
        attempts: int = 0,
    ) -> Optional[asyncio.subprocess.Process]:
        max_attempts = 3
        process: Optional[asyncio.subprocess.Process] = None
        try:
            attempts += 1
            if attempts > max_attempts:
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
                f"Process finished too quickly running again (attempt {attempts}/{max_attempts})"
            )
            return await self._run_command_async(command, min_execution_time, attempts)

        except asyncio.TimeoutError:
            # Process is still running after the timeout. This is fine.
            return process
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            logger.debug(f"Failed to run command: {e}")
            return None
