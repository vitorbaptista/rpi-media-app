#!/usr/bin/env python3

import os
import sys
import logging
import glob
import subprocess
import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
VIDEO_DIR = os.path.join(os.path.dirname(__file__), "data", "sessao_da_tarde")


def _get_video_path():
    video_paths = sorted(glob.glob(os.path.join(VIDEO_DIR, "**/*.mp4"), recursive=True))
    if not video_paths:
        return

    video_index = datetime.datetime.now().day
    if datetime.datetime.now().hour > 12:
        video_index += 1

    video_path = video_paths[video_index % len(video_paths)]

    return video_path


def main():
    try:
        video_path = _get_video_path()
        if not video_path:
            logger.error("No video path found")
            return 1

        logger.info(f"Playing video: {video_path}")
        subprocess.run(["catt", "cast", video_path], check=True)
        logger.info("Playback completed successfully")

        return 0

    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
