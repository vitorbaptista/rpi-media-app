import asyncio
import json
import pathlib
import socket
from typing import Optional, Dict, Any
from . import event_bus as eb

# Use a socket file in the user's home directory
SOCKET_PATH = pathlib.Path.home() / ".rpimedia" / "event.sock"


class IPCListener:
    def __init__(self, event_bus: Optional[eb.EventBus] = None):
        """Initialize the IPC Event Listener with an event bus."""
        self.event_bus = event_bus or eb.EventBus()
        self._shutdown_event = asyncio.Event()
        self._server: Optional[asyncio.Server] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def run(self) -> None:
        """Run the IPC server in a loop until shutdown is requested."""
        print("IPC Event Listener started. Listening for events...")
        self._loop = asyncio.get_running_loop()

        SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)

        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()

        self._server = await asyncio.start_unix_server(
            self._handle_client, str(SOCKET_PATH)
        )

        try:
            while not self._shutdown_event.is_set():
                await asyncio.sleep(0.1)
        finally:
            if self._server:
                self._server.close()
                await self._server.wait_closed()
            if SOCKET_PATH.exists():
                SOCKET_PATH.unlink()

        print("IPC Event Listener stopped.")

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            while True:
                # Read the message length (4 bytes)
                length_bytes = await reader.read(4)
                if not length_bytes:
                    break

                # Convert length bytes to integer
                message_length = int.from_bytes(length_bytes, byteorder="big")

                # Read the actual message
                message_bytes = await reader.read(message_length)
                if not message_bytes:
                    break

                # Parse and process the message
                try:
                    message = json.loads(message_bytes.decode())
                    event_kind = message.get("event_kind")
                    event_data = message.get("event_data")

                    if event_kind and event_data:
                        await self.event_bus.add_event(event_kind, event_data)
                        writer.write(b"OK\n")
                    else:
                        writer.write(b"ERROR: Invalid message format\n")
                except json.JSONDecodeError:
                    writer.write(b"ERROR: Invalid JSON\n")

                await writer.drain()

        except Exception as e:
            print(f"Error handling client: {e}")
        finally:
            writer.close()
            await writer.wait_closed()

    async def handle_shutdown(self, message: str) -> None:
        """Handle graceful shutdown."""
        print(f"\n{message}. Exiting...")
        self._shutdown_event.set()
        # Cancel all tasks except the current one to allow the application to exit
        for task in asyncio.all_tasks():
            if task != asyncio.current_task():
                task.cancel()

    @staticmethod
    async def send_event(event_kind: str, event_data: Dict[str, Any]) -> bool:
        """Send an event to the running IPC server.

        Returns:
            bool: True if the event was sent successfully, False otherwise.
        """
        if not SOCKET_PATH.exists():
            print("Error: No running IPC server found")
            return False

        sock = None
        try:
            # Create a Unix domain socket
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(str(SOCKET_PATH))

            # Prepare the message
            message = {"event_kind": event_kind, "event_data": event_data}
            message_bytes = json.dumps(message).encode()
            message_length = len(message_bytes)

            # Send the message length first (4 bytes)
            sock.sendall(message_length.to_bytes(4, byteorder="big"))
            # Send the actual message
            sock.sendall(message_bytes)

            # Read the response
            response = sock.recv(1024).decode().strip()
            success = response == "OK"

            if not success:
                print(f"Error from server: {response}")

            return success

        except Exception as e:
            print(f"Error sending event: {e}")
            return False
        finally:
            if sock is not None:
                sock.close()
