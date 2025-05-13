import logging
import random
import glob
import os
import asyncio
import subprocess
import functools
from . import event_bus as eb

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")


def _debounce(wait_time):
    """
    Decorator that prevents a function from being called more than once every wait_time seconds.
    For async functions.
    """

    def decorator(func):
        last_called = {}

        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            current_time = asyncio.get_event_loop().time()
            key = args[0] if args else None  # Use first arg as key
            if key is None:
                return await func(self, *args, **kwargs)

            last_time = last_called.get(key, 0)
            if current_time - last_time < wait_time:
                return

            last_called[key] = current_time
            return await func(self, *args, **kwargs)

        return wrapper

    return decorator


class Controller:
    MAX_ENQUEUED_VIDEOS = 3

    def __init__(self, config, event_bus: eb.EventBus | None = None):
        self.event_bus = event_bus or eb.EventBus()
        self._current_process = None
        self._current_process_command = None
        self._config = config
        self._last_key_pressed = None

    async def run(self):
        while True:
            event = await self.event_bus.get_event()
            if event is not None:
                event_kind, event_data = event
                await self.handle_event(event_kind, event_data)

            # Add a small delay to prevent CPU spinning
            await asyncio.sleep(0.01)

    async def handle_event(self, event_kind, event_data):
        logger.debug(f"Handling event: {event_kind} {event_data}")

        match event_kind:
            case "keyboard_input":
                await self._handle_key_press(event_data["key"])
            case _:
                logger.debug(f"Unknown event: {event_kind} {event_data}")

    @_debounce(wait_time=10)
    async def _handle_key_press(self, key):
        """Handle a key press using the configuration"""
        is_repeated_key = self._last_key_pressed == key
        self._last_key_pressed = key

        binding = self._config["remote"]["bindings"].get(key)
        key_config = self._config["remote"]["keys"].get(binding)
        if not binding or not key_config:
            logger.debug(f"No configuration for key: {key}")
            return

        method = key_config["method"]
        params = key_config["params"]
        match method:
            case "youtube":
                # Randomly shuffle the params list
                shuffled_videos = list(params)
                random.shuffle(shuffled_videos)

                if is_repeated_key:
                    return await self.skip_video()
                else:
                    await self.clear_queue_youtube()

                    first_video = shuffled_videos[0]
                    await self.play_youtube(first_video)

                # Enqueue the remaining videos if there are any
                for video_id in shuffled_videos[1 : self.MAX_ENQUEUED_VIDEOS]:
                    await self.enqueue_youtube(video_id)
                    await asyncio.sleep(2)

                return
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

    async def play_youtube(self, video_id):
        # TODO: Adicionar uma imagem enquanto ele não carrega, pois demora alguns segundos
        logger.debug(f"Playing youtube video {video_id}")
        return await self._run_command_async(
            [
                "catt",
                "cast",
                f"https://www.youtube.com/watch?v={video_id}",
            ]
        )

    async def clear_queue_youtube(self):
        logger.debug("Clearing youtube queue")
        return await self._run_command_async(["catt", "clear"])

    async def enqueue_youtube(self, video_id):
        logger.debug(f"Enqueuing youtube video {video_id}")
        return await self._run_command_async(
            ["catt", "add", f"https://www.youtube.com/watch?v={video_id}"]
        )

    async def play_url(self, url):
        logger.debug(f"Playing url {url}")
        return await self._run_command_async(["catt", "cast", url])

    async def skip_video(self):
        logger.debug("Skipping video")
        return await self._run_command_async(["catt", "skip"])

    async def play_video(self, video_path):
        logger.debug(f"Playing video {video_path}")
        return await self._run_command(
            ["cvlc", "--no-keyboard-events", "--loop", "--avcodec-hw=none", video_path]
        )

    async def play_glob(self, glob_path):
        logger.debug(f"Playing glob {glob_path}")
        glob_path = os.path.join(BASE_DIR, glob_path)
        video_paths = sorted(glob.glob(glob_path, recursive=True))
        if not video_paths:
            logger.error(f"No video found for glob {glob_path}")
            return

        video_path = random.choice(video_paths)
        return await self._run_command_async(["catt", "cast", video_path])

    async def volume_up(self, volume_step):
        logger.debug(f"Volume up by {volume_step}")
        return await self._run_command_async(["catt", "volumeup", f"{volume_step}"])

    async def volume_down(self, volume_step):
        logger.debug(f"Volume down by {volume_step}")
        return await self._run_command_async(["catt", "volumedown", f"{volume_step}"])

    async def _run_command(self, command):
        if self._current_process_command == command:
            # Ignore if the command is the same as the current one
            logger.debug("Ignoring repeated command")
            return

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

    async def _run_command_async(self, command):
        try:
            return await asyncio.create_subprocess_exec(*command)
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            logger.debug(f"Failed to run command: {e}")
