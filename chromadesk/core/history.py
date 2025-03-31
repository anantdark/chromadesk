# chromadesk/chromadesk/core/history.py
import logging
import re  # Import regular expressions
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from . import config as core_config
from .config import load_config

logger = logging.getLogger(__name__)  # Use __name__ for logger


# --- Wallpaper Storage Location ---
def get_wallpaper_dir() -> Path:
    """Gets the wallpaper storage directory from config, with fallback."""
    config = load_config()
    dir_str = config.get(
        "Settings",
        "wallpaper_dir",
        fallback=str(Path.home() / "Pictures" / "wallpapers"),
    )
    return Path(dir_str)


def ensure_wallpaper_dir() -> bool:
    """Creates the wallpaper storage directory if it doesn't exist."""
    wallpaper_dir = get_wallpaper_dir()
    try:
        wallpaper_dir.mkdir(parents=True, exist_ok=True)
        # Don't log success every time, reduce noise
        # logger.info(f"Ensured wallpaper directory exists: {wallpaper_dir}")
        return True
    except OSError as e:
        logger.error(f"Error creating wallpaper directory {wallpaper_dir}: {e}")
        return False


# --- Filename Generation ---
def get_bing_filename(date_str: str, image_url: str) -> str:
    """Generates a filename for a Bing wallpaper (e.g., bing_20231027.jpg)."""
    try:
        parsed_url = urlparse(image_url)
        extension = (
            Path(parsed_url.path).suffix.lower() or ".jpg"
        )  # Use lower extension
        date_part = date_str.split("T")[0].replace("-", "")
        filename = f"bing_{date_part}{extension}"
        logger.debug(f"Generated Bing filename '{filename}' for date '{date_str}'")
        return filename
    except Exception as e:
        logger.error(
            f"Error generating Bing filename for url='{image_url}', date='{date_str}': {e}",
            exc_info=True,
        )
        return f"bing_{date_str.replace('-','')}_error{extension or '.jpg'}"


def get_custom_filename(extension: str = ".jpg") -> str:
    """Generates a unique filename for a custom wallpaper (e.g., custom_20231027_153000.jpg)."""
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    # Ensure extension starts with a dot and is lowercase
    if extension:
        extension = extension.lower()
        if not extension.startswith("."):
            extension = "." + extension
    filename = f"custom_{timestamp}{extension or '.jpg'}"
    logger.debug(f"Generated custom filename '{filename}'")
    return filename


# --- Combined History Management ---

# Regular expressions to parse filenames
BING_FILENAME_RE = re.compile(r"^bing_(\d{8})\..+$")
CUSTOM_FILENAME_RE = re.compile(r"^custom_(\d{8}_\d{6})\..+$")


def _parse_datetime_from_path(file_path: Path) -> datetime | None:
    """Extracts datetime object from Bing or Custom filename."""
    match = BING_FILENAME_RE.match(file_path.name)
    if match:
        try:
            # Bing images represent a whole day, use start of day for sorting
            return datetime.strptime(match.group(1), "%Y%m%d")
        except ValueError:
            return None  # Invalid date format
    match = CUSTOM_FILENAME_RE.match(file_path.name)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y%m%d_%H%M%S")
        except ValueError:
            return None  # Invalid datetime format
    return None  # Filename doesn't match known patterns


def get_sorted_wallpaper_history(max_items: int = 7) -> list[Path]:
    """
    Scans the wallpaper directory for Bing AND Custom images, sorts them by
    date/time (newest first), and returns a list of Path objects.

    Args:
        max_items (int): The maximum number of history items to return.

    Returns:
        list[Path]: A list of Path objects for wallpapers, sorted newest first.
    """
    wallpaper_dir = get_wallpaper_dir()
    logger.info(f"Getting combined wallpaper history from: {wallpaper_dir}")
    if not wallpaper_dir.is_dir():
        logger.warning(f"Wallpaper directory not found: {wallpaper_dir}")
        return []

    wallpaper_files_with_dates = []
    try:
        # Iterate through all files, check pattern, parse date
        for item in wallpaper_dir.iterdir():
            if item.is_file():
                dt = _parse_datetime_from_path(item)
                if dt:
                    wallpaper_files_with_dates.append((dt, item))
                else:
                    logger.debug(f"Ignoring file with non-history name: {item.name}")

        # Sort by datetime object (newest first)
        wallpaper_files_with_dates.sort(key=lambda x: x[0], reverse=True)

        # Extract only the Path objects from the sorted list
        sorted_paths = [item[1] for item in wallpaper_files_with_dates]
        logger.info(
            f"Found {len(sorted_paths)} history files. Returning newest {max_items}."
        )

        return sorted_paths[:max_items]

    except OSError as e:
        logger.error(f"Error scanning wallpaper directory {wallpaper_dir}: {e}")
        return []


def cleanup_wallpaper_history(keep: int = 7) -> int:
    """
    Deletes the oldest wallpapers (Bing and Custom) from the storage directory,
    keeping only the specified number of newest items overall.

    Args:
        keep (int): The number of most recent wallpapers to keep.

    Returns:
        int: The number of files deleted.
    """
    wallpaper_dir = get_wallpaper_dir()
    logger.info(
        f"Running combined wallpaper cleanup in {wallpaper_dir}, keeping {keep} newest."
    )
    if not wallpaper_dir.is_dir():
        return 0

    try:
        # Get *all* history files sorted newest first
        all_history_files = get_sorted_wallpaper_history(max_items=99999)

        if len(all_history_files) <= keep:
            logger.info(
                f"Cleanup: {len(all_history_files)} files found <= {keep}. No cleanup needed."
            )
            return 0

        # Files to delete are the ones after the 'keep' index
        files_to_delete = all_history_files[keep:]
        deleted_count = 0
        logger.info(
            f"Cleanup: Found {len(all_history_files)} files, keeping {keep}. Will delete {len(files_to_delete)}."
        )

        for file_path in files_to_delete:
            try:
                file_path.unlink()  # Delete the file
                logger.info(f"Cleanup: Deleted old wallpaper: {file_path.name}")
                deleted_count += 1
            except OSError as e:
                logger.error(f"Cleanup: Error deleting file {file_path}: {e}")

        return deleted_count

    except OSError as e:
        logger.error(f"Cleanup: Error during cleanup in {wallpaper_dir}: {e}")
        return 0


# --- Custom Wallpaper Saving ---
def save_custom_wallpaper(source_path: Path) -> Path | None:
    """
    Copies a validated custom wallpaper to the storage directory with a unique name.
    (Ensure source_path is validated image before calling this)

    Args:
        source_path (Path): Path to the temporary downloaded custom image file.

    Returns:
        Path | None: The Path to the newly saved custom wallpaper in the storage directory,
                     or None if saving failed.
    """
    if not ensure_wallpaper_dir():
        return None
    if not source_path.is_file():
        logger.error(f"Source file for custom wallpaper not found: {source_path}")
        return None

    wallpaper_dir = get_wallpaper_dir()
    # Generate filename using lowercase extension from source
    dest_filename = get_custom_filename(source_path.suffix)
    dest_path = wallpaper_dir / dest_filename

    try:
        shutil.copy2(source_path, dest_path)  # copy2 preserves metadata
        logger.info(f"Saved custom wallpaper from {source_path.name} to {dest_path}")
        # Clean up old history after adding a new custom one
        keep_count = int(
            core_config.get_setting("Settings", "keep_history", fallback="7")
        )
        cleanup_wallpaper_history(keep=keep_count)  # Run cleanup after adding
        return dest_path
    except OSError as e:
        logger.error(f"Error copying custom wallpaper to {dest_path}: {e}")
        return None
    except Exception as e:
        logger.error(
            f"Unexpected error saving custom wallpaper or cleaning history: {e}",
            exc_info=True,
        )
        return None


# --- Update Headless Script Reference ---
# Make sure headless.py calls cleanup_wallpaper_history instead of cleanup_bing_history

# --- (Test block needs updating if run standalone) ---
# The __main__ block here would need significant changes to test combined history.
# Recommend testing via the main UI or dedicated unit tests later.
