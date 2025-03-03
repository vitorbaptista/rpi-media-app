import asyncio
import subprocess
from . import event_bus as eb


class Controller:
    def __init__(self, event_bus: eb.EventBus = None):
        self.event_bus = event_bus or eb.EventBus()
        self._current_process = None
        self._current_process_command = None

    async def run(self):
        while True:
            event_kind, event_data = await self.event_bus.get_event()
            if event_kind:
                await self.handle_event(event_kind, event_data)

            # Add a small delay to prevent CPU spinning
            await asyncio.sleep(0.01)

    async def handle_event(self, event_kind, event_data):
        volume_step = "20%"

        match event_kind:
            case "keyboard_input":
                key = event_data["key"]
                match key:
                    case "3":
                        await self.volume_up(volume_step)
                    case "1":
                        await self.volume_down(volume_step)
                    case "2":
                        print("Pause")
                    case "c":
                        await self.play_youtube("ha-Ag0lQmN0")
                    case "f":
                        await self.play_youtube("f_XTeWMoKxk")
                    case "b":
                        await self.play_video("data/ze-freitas.mp4")
                    case "e":
                        await self.play_video("data/toggle.mp4")
                    case "a":
                        print("20")
                    case "d":
                        print("21")
                    case _:
                        print(f"Keyboard input: {event_data['key']}")
            case _:
                print(f"Unknown event: {event_kind} {event_data}")

    async def play_youtube(self, video_id):
        # TODO: Adicionar uma imagem enquanto ele não carrega, pois demora alguns segundos
        print(f"Playing youtube video {video_id}")
        return await self._run_command(
            [
                "mpv",
                "--really-quiet",
                "--ytdl-format=94,18",  # TODO: Use best format using https://github.com/ytdl-org/youtube-dl/blob/master/README.md#format-selection
                f"https://www.youtube.com/watch?v={video_id}",
            ]
        )

    async def play_video(self, video_path):
        print(f"Playing video {video_path}")
        return await self._run_command(
            ["cvlc", "--quiet", "--no-keyboard-events", "--loop", video_path]
        )

    async def volume_up(self, volume_step):
        print(f"Volume up by {volume_step}")
        return await self._run_command_async(
            ["amixer", "--quiet", "-M", "set", "Master", f"{volume_step}+"]
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

        self._current_process = await self._run_command_async(command)
        if self._current_process:
            self._current_process_command = command

    async def _run_command_async(self, command):
        try:
            return await asyncio.create_subprocess_exec(*command)
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            print(f"Failed to run command: {e}")
