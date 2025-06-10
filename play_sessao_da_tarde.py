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
VIDEO_DIR = os.path.join(os.path.dirname(__file__), "data", "sessao_da_tarde", "chosen")


def _get_video_path():
    video_paths = sorted(glob.glob(os.path.join(VIDEO_DIR, "**/*.mp4"), recursive=True))
    if not video_paths:
        return

    video_index = datetime.datetime.now().timetuple().tm_yday  # Day of the year
    if datetime.datetime.now().hour > 12:
        video_index += 1

    video_path = video_paths[video_index % len(video_paths)]

    return video_path


def _play_video(video_path):
    logger.info(f"Playing video: {video_path}")
    return subprocess.run(["rpimedia", "send_event", "video", video_path], check=True)


# TODO: Only play if we're playing TV Aparecida
def main():
    try:
        video_path = _get_video_path()
        if not video_path:
            logger.error("No video path found")
            return 1

        _play_video(video_path)

        return 0
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
