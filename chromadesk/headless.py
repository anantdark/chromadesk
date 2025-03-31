#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ChromaDesk Headless Script

This script is intended to be run automatically (e.g., by a systemd timer)
to fetch the daily Bing wallpaper, download it, set it as the desktop background,
and perform history cleanup. It reads configuration from the standard config file
and logs its actions.
"""

import logging
import os  # Needed for environment variables for notify-send
import subprocess
import sys
from datetime import date
from pathlib import Path

# Configure logging (important for debugging scheduled tasks)
# Log to the same file as the main app, but identify as headless
log_format = "%(asctime)s - %(name)s - HEADLESS - %(levelname)s - %(message)s"
# Ensure the log directory exists (can be tricky if run very early)
# We assume the config loading will handle dir creation needed for config file,
# but log file path might need separate handling if not in ~/.config/chromadesk/
log_file_path = Path.home() / ".config" / "chromadesk" / "chromadesk.log"
try:
    log_file_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,  # Log INFO and above
        format=log_format,
        handlers=[
            logging.FileHandler(log_file_path),
            # Optionally add StreamHandler if debugging manually
            # logging.StreamHandler()
        ],
    )
except Exception as e:
    # Fallback basic logging if file handler fails
    logging.basicConfig(level=logging.WARNING, format=log_format)
    logging.critical(f"Failed to configure file logging for headless script: {e}")

logger = logging.getLogger(__name__)

# --- Import Core Modules ---
# Need to handle potential import errors if run standalone vs as module
try:
    # Use absolute imports (recommended approach)
    from chromadesk.core import bing as core_bing
    from chromadesk.core import config as core_config
    from chromadesk.core import downloader as core_downloader
    from chromadesk.core import history as core_history
    from chromadesk.core import wallpaper as core_wallpaper
except ImportError:
    # Fallback to relative imports if run directly within package
    try:
        from .core import bing as core_bing
        from .core import config as core_config
        from .core import downloader as core_downloader
        from .core import history as core_history
        from .core import wallpaper as core_wallpaper

        logger.info("Using relative imports for core modules.")
    except ImportError as e:
        logger.critical(
            f"Failed to import core modules. Make sure script is run correctly: {e}"
        )
        sys.exit(1)


# --- Helper Function for Notifications ---
def send_notification(title: str, message: str, urgency: str = "normal"):
    """Sends a desktop notification using notify-send."""
    logger.debug(
        f"Attempting to send notification: Title='{title}', Urgency='{urgency}'"
    )
    try:
        # notify-send needs DBUS_SESSION_BUS_ADDRESS, especially when run from systemd user service
        # We hope systemd --user services inherit this, but might need explicit passthrough in service file
        # Check if command exists
        if not subprocess.check_output(["which", "notify-send"]).strip():
            logger.warning(
                "'notify-send' command not found. Cannot send desktop notifications."
            )
            return

        # Check for necessary env var (informational)
        if "DBUS_SESSION_BUS_ADDRESS" not in os.environ:
            logger.warning(
                "DBUS_SESSION_BUS_ADDRESS not found in environment. Notifications might fail from systemd."
            )

        cmd = ["notify-send", "-a", "ChromaDesk", "-u", urgency, title, message]
        subprocess.run(cmd, check=True, timeout=5)
        logger.debug("Notification command executed.")
    except FileNotFoundError:
        logger.warning(
            "'notify-send' command not found (checked again). Cannot send desktop notifications."
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        logger.error(f"Failed to send notification: {e}")
    except Exception as e:
        logger.error(f"Unexpected error sending notification: {e}")


# --- Main Headless Logic ---
def run_daily_update():
    """Performs the complete daily wallpaper update process."""
    logger.info("Starting daily update process...")
    img_title = "ChromaDesk"  # Default title
    img_description = ""  # Default description

    # 1. Load Configuration
    try:
        config = core_config.load_config()
        is_enabled = config.getboolean("Settings", "enabled", fallback=False)
        region = config.get("Settings", "region", fallback="en-US")
        keep_history_count = config.getint("Settings", "keep_history", fallback=7)
        last_update_str = config.get("State", "last_update_date", fallback="")
        logger.info(
            f"Config loaded: enabled={is_enabled}, region={region}, keep={keep_history_count}, last_update={last_update_str}"
        )
    except Exception as e:
        logger.critical(f"Failed to load configuration: {e}. Aborting.", exc_info=True)
        # Send critical notification if possible
        send_notification(
            "ChromaDesk Error",
            "Failed to load configuration. Daily update aborted.",
            "critical",
        )
        return False

    # 2. Check if Enabled
    if not is_enabled:
        logger.info("Daily updates are disabled in configuration. Exiting.")
        return True  # Not an error state

    # 3. Check if Already Updated Today
    today_str = date.today().isoformat()
    if last_update_str == today_str:
        logger.info(f"Wallpaper already updated today ({today_str}). Exiting.")
        return True
    else:
        logger.info(
            f"Last update was {last_update_str}, proceeding with update for {today_str}."
        )

    # 4. Ensure Wallpaper Directory Exists
    if not core_history.ensure_wallpaper_dir():
        logger.error("Failed to ensure wallpaper directory exists. Aborting.")
        send_notification(
            "ChromaDesk Error",
            "Cannot create or access wallpaper directory. Update failed.",
            "critical",
        )
        return False

    # 5. Fetch Bing Info
    logger.info(f"Fetching Bing info for region: {region}")
    bing_info = core_bing.fetch_bing_wallpaper_info(region=region)

    if not bing_info or not bing_info.get("full_url"):
        logger.error("Failed to fetch Bing wallpaper info.")
        send_notification(
            "ChromaDesk Update Failed",
            f"Could not fetch Bing image information for region {region}.",
            "normal",
        )
        # Don't abort yet, maybe network is temporarily down, try again tomorrow
        return False  # Return False to indicate this run failed

    # --- Extract Title and Description ---
    img_title = bing_info.get("title", "Untitled Image")
    raw_copyright = bing_info.get("copyright", "")
    # Clean description - take text before the first parenthesis
    if "(" in raw_copyright:
        img_description = raw_copyright[: raw_copyright.find("(")].strip()
    else:
        img_description = raw_copyright.strip()
    logger.info(f"Fetched Bing info: Title='{img_title}', Desc='{img_description}'")

    # 6. Prepare Filename and Check if Already Downloaded
    wallpaper_dir = core_history.get_wallpaper_dir()
    try:
        target_filename = core_history.get_bing_filename(
            bing_info["date"], bing_info["full_url"]
        )
        local_path = wallpaper_dir / target_filename
    except Exception as e:
        logger.error(f"Failed to generate filename for Bing image: {e}", exc_info=True)
        send_notification(
            "ChromaDesk Error", "Internal error generating filename.", "critical"
        )
        return False

    if local_path.is_file():
        logger.info(f"Today's Bing image already downloaded: {local_path.name}")
        # Proceed to set it as wallpaper
    else:
        # 7. Download Image
        logger.info(f"Downloading image from {bing_info['full_url']} to {local_path}")
        download_success = core_downloader.download_image(
            bing_info["full_url"], local_path
        )
        if not download_success:
            logger.error("Failed to download Bing image.")
            send_notification(
                "ChromaDesk Update Failed",
                "Could not download the Bing image.",
                "normal",
            )
            # Clean up potentially incomplete file? Maybe not necessary if downloader handles it.
            try:
                if local_path.exists():
                    local_path.unlink()
            except OSError:
                pass
            return False  # Indicate download failure

        logger.info("Image downloaded successfully.")

    # 8. Set Wallpaper
    logger.info(f"Setting wallpaper to: {local_path}")
    set_success = core_wallpaper.set_gnome_wallpaper(local_path)

    if not set_success:
        logger.error("Failed to set wallpaper via core function.")
        send_notification(
            "ChromaDesk Update Failed",
            f"Could not set the downloaded wallpaper: {local_path.name}",
            "critical",
        )
        # Don't mark as updated if setting failed
        return False

    # 9. Update State in Config
    logger.info(
        f"Wallpaper set successfully. Updating last_update_date to {today_str}."
    )
    try:
        # No need to read config again here as we have it already from step 1
        if not core_config.set_setting("State", "last_update_date", today_str):
            logger.error("Failed to update last_update_date in config.")
    except Exception as e:
        logger.error(f"Error saving config after successful update: {e}")
        # Continue anyway - setting wallpaper was successful, just couldn't save state

    # 10. Run History Cleanup
    logger.info(f"Running history cleanup with keep_count={keep_history_count}")
    try:
        core_history.cleanup_wallpaper_history(keep=keep_history_count)
    except Exception as e:
        logger.error(f"History cleanup failed: {e}", exc_info=True)
        # Non-fatal error, continue

    # 11. Send Success Notification
    try:
        # Format a nice message with info about the image
        message = f"'{img_title}'"
        if img_description:
            message += f"\n{img_description}"
        send_notification("Wallpaper Updated", message, "normal")
    except Exception as e:
        logger.error(f"Failed to send success notification: {e}")

    logger.info("Daily update process completed successfully.")
    return True


# --- Script Entry Point ---
if __name__ == "__main__":
    logger.info("=" * 20 + " Headless Script Run Start " + "=" * 20)
    success = run_daily_update()
    logger.info("=" * 20 + f" Headless Script Run End (Success: {success}) " + "=" * 20)
    sys.exit(0 if success else 1)  # Exit with 0 on success, 1 on failure
