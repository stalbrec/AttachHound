import logging
import re
import os
from pathlib import Path

def increment_filename(filepath:str) -> str:
    base,extension = os.path.splitext(filepath)
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
