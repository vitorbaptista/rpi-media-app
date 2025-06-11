#!/usr/bin/env python3

import sys
import logging
import subprocess
import time
from typing import Optional, Tuple, Any, Dict
import catt.api
import click

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_device() -> Optional[catt.api.CattDevice]:
    """
    Discover and return the first available Chromecast device.
    Returns the device or None if no device is found or an error occurs.
    """
    devices = catt.api.discover()
    if not devices:
        return None

    device = devices[0]
    logger.info(f"Found device: {device.name}")
    return device


def check_cast_status(
    num_retries: int = 2, sleep_seconds: int = 3
) -> Tuple[Optional[catt.api.CattDevice], bool]:
    """
    Check Chromecast status with retries.
    Returns (device, is_playing) tuple where is_playing is True only if
    all attempts show something is playing.
    """
    if num_retries < 1:
        raise ValueError("num_retries must be at least 1")

    logger.info(
        f"Checking cast status ({num_retries} attempts, {sleep_seconds}s between)"
    )

    device = get_device()
    if not device or not device.controller:
        return None, False

    all_playing = True
    for attempt in range(num_retries):
        if attempt > 0:
            time.sleep(sleep_seconds)

        device.controller.prep_info()
        media_info: Dict[str, Any] = device.controller.media_info
        is_playing = bool(media_info.get("title"))

        if not is_playing:
            all_playing = False
            logger.debug(f"Attempt {attempt + 1}/{num_retries}: Not playing")
        else:
            logger.debug(
                f"Attempt {attempt + 1}/{num_retries}: Playing - {media_info.get('title', 'Unknown')}"
            )

    status = "playing" if all_playing else "not playing"
    logger.info(f"Final status: {status}")
    return device, all_playing


@click.command()
@click.argument("event_kind", type=str)
@click.argument("event_params", nargs=-1, type=str)
@click.option("--retries", type=int, default=2, help="Number of times to check status")
@click.option("--sleep", type=int, default=5, help="Seconds to wait between checks")
@click.option("--debug", is_flag=True, help="Enable debug logging")
def main(
    event_kind: str,
    event_params: tuple[str, ...],
    retries: int,
    sleep: int,
    debug: bool,
) -> int:
    """Check Chromecast device and send event if nothing is playing.

    EVENT_KIND is the type of event to send (e.g. 'keyboard_input', 'youtube')
    EVENT_PARAMS are the parameters for the event

    The event is the same as the ones required by `rpimedia`.
    """
    # Set debug level if requested
    if debug:
        logger.setLevel(logging.DEBUG)

    try:
        device, is_playing = check_cast_status(num_retries=retries, sleep_seconds=sleep)

        if not device:
            logger.error("Failed to get a valid device")
            return 1

        if is_playing:
            logger.info("No action needed - device is playing")
            return 0

        logger.info(
            f"Device is not playing. Sending event: {event_kind} with params {event_params}"
        )
        subprocess.run(["rpimedia", "send_event", event_kind, *event_params])
        logger.info("Event sent")
        return 0

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
