#!/usr/bin/env python3

import sys
import logging
import argparse
import subprocess
import catt.api

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Check Chromecast device and play URL if nothing is playing."
    )
    parser.add_argument("url", help="URL to play when nothing is playing")
    args = parser.parse_args()

    # Get URL from command line argument
    url_to_play = args.url

    try:
        # Discover devices
        logger.info("Discovering Chromecast devices...")
        devices = catt.api.discover()

        # Check if we found any devices
        if not devices:
            logger.error("No Chromecast devices found")
            return 1

        # Get the first device
        dvc = devices[0]
        logger.info(f"Found device: {dvc.name}")

        # Get cast info
        dvc.controller.prep_info()
        media_info = dvc.controller.media_info
        logger.info(f"Current cast info: {media_info}")

        # Check if something is playing (has a title)
        if media_info.get("title"):
            logger.info(f"Device is currently playing: {media_info['title']}")
            logger.info("No action needed")
        else:
            logger.info("Device is not playing anything")
            logger.info(f"Playing URL: {url_to_play}")
            subprocess.run(["catt", "cast", url_to_play])
            # dvc.play_url(url_to_play)
            logger.info("Started playback successfully")

        return 0

    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
