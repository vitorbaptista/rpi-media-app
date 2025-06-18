#!/usr/bin/env python3

import json
import logging
import sys
import time
from typing import Any, Dict, Optional, Tuple

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
    try:
        devices = catt.api.discover()
        if not devices:
            logger.warning("No Chromecast devices found")
            return None

        device = devices[0]
        logger.info(f"Found device: {device.name}")
        return device
    except Exception as e:
        logger.error(f"Error discovering devices: {e}")
        return None


def get_current_media_info(
    num_retries: int, sleep_seconds: int
) -> Tuple[Optional[catt.api.CattDevice], Optional[Dict[str, Any]]]:
    """
    Get current media info with retries.
    Returns (device, media_info) tuple where media_info is the media info if playing,
    None if not playing or no media info available.
    """
    if num_retries < 1:
        raise ValueError("num_retries must be at least 1")

    logger.debug(
        f"Getting current media info ({num_retries} attempts, {sleep_seconds}s between)"
    )

    device = get_device()
    if not device or not device.controller:
        logger.warning("No valid device or controller available")
        return None, None

    media_info = None
    for attempt in range(num_retries):
        if attempt > 0:
            time.sleep(sleep_seconds)

        try:
            device.controller.prep_info()
            media_info = device.controller.media_info

            if media_info:
                break
            else:
                logger.debug(
                    f"Attempt {attempt + 1}/{num_retries}: No media info available"
                )

        except Exception as e:
            logger.debug(
                f"Attempt {attempt + 1}/{num_retries}: Error getting info - {e}"
            )

    return device, media_info


@click.command()
@click.option("--retries", type=int, default=3, help="Number of times to check status")
@click.option("--sleep", type=int, default=2, help="Seconds to wait between checks")
def main(
    retries: int,
    sleep: int,
) -> int:
    """Get the current media info from Chromecast device.

    Returns the media info if something is playing, nothing otherwise.
    """
    try:
        device, media_info = get_current_media_info(
            num_retries=retries, sleep_seconds=sleep
        )

        if not device:
            logger.error("Failed to get a valid device")
            return 1

        if media_info:
            print(json.dumps(media_info, indent=2, ensure_ascii=False))

        return 0

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
