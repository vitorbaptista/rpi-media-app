#!/usr/bin/env python3

import sys
import logging
import argparse
import subprocess
import time
from typing import Optional, Tuple, Any, Dict
import catt.api

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


def main() -> int:
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Check Chromecast device and play URL if nothing is playing."
    )
    parser.add_argument("url", help="URL to play when nothing is playing")
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Number of times to check status (default: 2)",
    )
    parser.add_argument(
        "--sleep",
        type=int,
        default=5,
        help="Seconds to wait between checks (default: 5)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    # Set debug level if requested
    if args.debug:
        logger.setLevel(logging.DEBUG)

    try:
        device, is_playing = check_cast_status(
            num_retries=args.retries, sleep_seconds=args.sleep
        )

        if not device:
            logger.error("Failed to get a valid device")
            return 1

        if is_playing:
            logger.info("No action needed - device is playing")
            return 0

        logger.info(f"Starting playback: {args.url}")
        subprocess.run(["catt", "cast", args.url])
        logger.info("Playback started")
        return 0

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
