import functools
import logging
import time

logger = logging.getLogger(__name__)


def retry_if_finished_too_quickly(min_execution_duration=180, max_attempts=5):
    """Decorator that retries a function if it finishes too quickly.

    Args:
        min_execution_duration (int): Minimum duration in seconds for the function to be considered successful
        max_attempts (int): Maximum number of retry attempts

    Returns:
        The decorator function
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            attempts = 0
            result = None
            while attempts < max_attempts:
                attempts += 1
                start_time = time.time()
                result = func(*args, **kwargs)
                execution_duration = time.time() - start_time

                if execution_duration >= min_execution_duration:
                    return result
                elif attempts >= max_attempts:
                    logger.info(f"Reached maximum of {max_attempts} attempts.")
                    return result
                else:
                    logger.info(
                        f"Execution time was {execution_duration:.2f} seconds, below {min_execution_duration} seconds threshold. Running again (attempt {attempts}/{max_attempts})."
                    )
            return result

        return wrapper

    return decorator
