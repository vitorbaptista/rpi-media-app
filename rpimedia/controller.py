import random
import asyncio
import subprocess
from . import event_bus as eb


class Controller:
    def __init__(self, config, event_bus: eb.EventBus | None = None):
        self.event_bus = event_bus or eb.EventBus()
        self._current_process = None
        self._current_process_command = None
        self._config = config

    async def run(self):
        while True:
            event = await self.event_bus.get_event()
            if event is not None:
                event_kind, event_data = event
                await self.handle_event(event_kind, event_data)

            # Add a small delay to prevent CPU spinning
            await asyncio.sleep(0.01)

    async def handle_event(self, event_kind, event_data):
        print(f"Handling event: {event_kind} {event_data}")

        match event_kind:
            case "keyboard_input":
                await self._handle_key_press(event_data["key"])
            case _:
                print(f"Unknown event: {event_kind} {event_data}")

    async def _handle_key_press(self, key):
        """Handle a key press using the configuration"""
        binding = self._config["remote"]["bindings"].get(key)
        key_config = self._config["remote"]["keys"].get(binding)
        if not binding or not key_config:
            print(f"No configuration for key: {key}")
            return

        method = key_config["method"]
        params = key_config["params"]
        match method:
            case "youtube":
                video_id = random.choice(params)
                return await self.play_youtube(video_id)
            case "video":
                video = random.choice(params)
                return await self.play_video(video)
            case "volume_up":
                return await self.volume_up(params)
            case "volume_down":
                return await self.volume_down(params)
            case _:
                print(f"Unknown method: {method}")

    async def play_youtube(self, video_id):
        # TODO: Adicionar uma imagem enquanto ele não carrega, pois demora alguns segundos
        print(f"Playing youtube video {video_id}")
        return await self._run_command(
            [
                "mpv",
                "--ytdl-format=94,18,397",  # TODO: Use best format using https://github.com/ytdl-org/youtube-dl/blob/master/README.md#format-selection
                f"https://www.youtube.com/watch?v={video_id}",
            ]
        )

    async def play_video(self, video_path):
        print(f"Playing video {video_path}")
        return await self._run_command(
            ["cvlc", "--no-keyboard-events", "--loop", "--avcodec-hw=none", video_path]
        )

    async def volume_up(self, volume_step):
        print(f"Volume up by {volume_step}")
        return await self._run_command_async(
            ["amixer", "-M", "set", "Master", f"{volume_step}+"]
        )

    async def volume_down(self, volume_step):
        print(f"Volume down by {volume_step}")
        return await self._run_command_async(
            ["amixer", "--quiet", "-M", "set", "Master", f"{volume_step}-"]
        )

    async def _run_command(self, command):
        if self._current_process_command == command:
            # Ignore if the command is the same as the current one
            print("Ignoring repeated command")
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
            print(f"Failed to run command: {e}")
