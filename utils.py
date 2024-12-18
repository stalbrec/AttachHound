import logging
import re
import os
from pathlib import Path
from typing import Union
from datetime import datetime, timedelta, timezone


class CutOffDate:
    def __init__(self, x: Union[str, int]):
        if isinstance(x, int):
            self.datetime = datetime.now(timezone.utc) - timedelta(days=x)
        elif isinstance(x, str):

            def parse_date(date_str):
                for date_format in [
                    "%Y-%m-%d",
                    "%d.%m.%Y",
                ]:
                    try:
                        date = datetime.strptime(date_str, date_format)
                        return date
                    except ValueError:
                        logging.debug(
                            f"Failed to parse date with format: {date_format}"
                        )
                logging.error("Failed to parse date for CutOff Query!")
                raise NotImplementedError

            self.datetime = parse_date(x)
            self.datetime = self.datetime.replace(tzinfo=timezone.utc)

    def __str__(self):
        return self.datetime.strftime("%d-%b-%Y")


def increment_filename(filepath: str) -> str:
    base, extension = os.path.splitext(filepath)
    counter = 1
    new_filepath = filepath
    while os.path.exists(new_filepath):
        new_filepath = f"{base}_{counter}{extension}"
        counter += 1
    return new_filepath


def sanitize_filename(filename: str) -> str:
    """
    Sanitize the filename to make it safe for filesystem use.

    This function replaces special characters in the filename with underscores
    to ensure the filename is safe for use in the filesystem.

    Args:
        filename (str): The original filename to sanitize.

    Returns:
        str: The sanitized filename with special characters replaced by underscores.
    """
    sanitized = re.sub(r"[^\w\-_\.:\\ ]", "_", filename)
    sanitized_path = Path(sanitized)

    if sanitized_path.is_absolute():
        sanitized_path = Path(
            *(
                p if i == 0 else p.replace(":", "_")
                for i, p in enumerate(sanitized_path.parts)
            )
        )
        sanitized = str(sanitized_path)
    else:
        sanitized = sanitized.replace(":", "_")
    logging.debug(f"Sanitized filename: {filename} -> {sanitized}")
    return sanitized
