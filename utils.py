import logging
import re


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
    sanitized = re.sub(r"[^\w\-_\. ]", "_", filename)
    logging.debug(f"Sanitized filename: {filename} -> {sanitized}")
    return sanitized

