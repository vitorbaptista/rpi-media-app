#!/usr/bin/env python3
"""
Volume control script that sets volume based on time of day.
Sets volume to 0 if current time is before day_start_time, otherwise sets to specified volume.
"""

import click
import logging
import subprocess
import time
from datetime import datetime

# Setup logging globally
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def parse_time(time_str):
    """
    Parse time string in HH24:MM format to datetime.time object.

    Args:
        time_str: Time string in format "HH:MM" (24-hour format)

    Returns:
        datetime.time object

    Raises:
        ValueError: If time format is invalid
    """
    try:
        # Parse the time string and extract just the time component
        parsed = datetime.strptime(time_str, '%H:%M')
        return parsed.time()
    except ValueError:
        raise ValueError(f"Invalid time format: {time_str}. Expected HH:MM in 24-hour format.")


def set_volume(volume_level):
    """
    Set volume using catt command.

    Args:
        volume_level: Integer volume level (0-100)

    Returns:
        bool: True if volume was set successfully, False otherwise
    """
    cmd = ['catt', 'volume', str(volume_level)]
    logger.debug(f"Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            logger.info(f"Volume set to {volume_level}")
            return True
        else:
            logger.warning(f"Command failed with code {result.returncode}")
            if result.stderr:
                logger.debug(f"Error: {result.stderr.strip()}")
            return False

    except subprocess.TimeoutExpired:
        logger.error(f"Timeout (attempt {attempt}/{max_attempts})")
        return False

    except FileNotFoundError:
        logger.error("catt command not found")
        return False

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return False


@click.command()
@click.argument(
    'day-start-time',
)
@click.argument(
    'volume',
    type=click.IntRange(0, 100),
)
def main(day_start_time, volume):
    """
    Volume control based on time of day.

    Sets volume to 0 if current time is before day_start_time,
    otherwise sets volume to the specified level.
    """
    logger.info("Starting volume control")

    # Parse and validate day start time
    try:
        day_start = parse_time(day_start_time)
    except ValueError as e:
        logger.error(str(e))
        raise click.BadParameter(str(e))

    # Get current time and determine volume
    now = datetime.now().time()
    is_before_day_start = now < day_start

    if is_before_day_start:
        logger.info(f"Current time {now.strftime('%H:%M')} is before {day_start.strftime('%H:%M')} - setting volume to 0")
        volume_to_set = 0
    else:
        logger.info(f"Current time {now.strftime('%H:%M')} is after {day_start.strftime('%H:%M')} - setting volume to {volume}")
        volume_to_set = volume

    # Set the volume
    success = set_volume(volume_to_set)

    if not success:
        logger.error("Failed to set volume")
        exit(1)


if __name__ == '__main__':
    main()
