# chromadesk/core/wallpaper.py
"""
Handles setting the desktop wallpaper for GNOME environments and sending
notifications, adapting to different session types and available settings keys.
"""

import logging
import os
import shutil
import subprocess
from pathlib import Path

# Attempt imports for notification libraries - handle if missing
try:
    import notify2

    NOTIFY2_AVAILABLE = True
except ImportError:
    NOTIFY2_AVAILABLE = False
try:
    import dbus

    DBUS_PYTHON_AVAILABLE = True
except ImportError:
    DBUS_PYTHON_AVAILABLE = False


logger = logging.getLogger(__name__)

# Define GNOME settings schemas and keys
SCHEMA_BACKGROUND = "org.gnome.desktop.background"
KEY_PICTURE_URI = "picture-uri"
KEY_PICTURE_URI_DARK = "picture-uri-dark"  # Existence is checked before use
KEY_PICTURE_OPTIONS = "picture-options"

# ==============================================================================
# Notification Functions
# ==============================================================================


def _send_notification_notify2(
    title: str, message: str, icon_path: str | None = None
) -> bool:
    """Sends a notification using the notify2 library if available."""
    if not NOTIFY2_AVAILABLE:
        logger.debug(
            "notify2 library not available, cannot send notification via notify2."
        )
        return False
    if not DBUS_PYTHON_AVAILABLE:  # notify2 uses dbus-python
        logger.debug("dbus-python library not available, notify2 cannot function.")
        return False

    try:
        # Ensure notify2 is initialized (safe to call multiple times)
        # Check if already initialized to avoid potential issues if called frequently
        if not notify2.is_initted():
            notify2.init("ChromaDesk")

        # Determine icon: use provided path if valid, otherwise fallback
        icon = (
            icon_path
            if icon_path and Path(icon_path).exists()
            else "dialog-information"
        )
        notification = notify2.Notification(title, message, icon)
        notification.set_urgency(notify2.URGENCY_LOW)
        notification.set_timeout(5000)  # milliseconds
        notification.show()
        logger.info(f"Notification sent via notify2: '{title}'")
        return True
    # Catch DBus errors specifically, as they are common if session bus is bad
    except dbus.exceptions.DBusException as e:
        logger.warning(f"DBusException while sending notification via notify2: {e}")
        logger.warning(
            "This might happen if the DBus session bus is unavailable (e.g., running outside graphical session without correct env vars)."
        )
        return False
    # Catch other potential errors during notification showing
    except Exception as e:
        logger.error(f"Error sending notification via notify2: {e}", exc_info=True)
        return False


def _send_notification_dbus(
    title: str, message: str, icon_name: str = "dialog-information"
) -> bool:
    """Sends a notification using raw dbus-python (fallback if notify2 fails/missing)."""
    if not DBUS_PYTHON_AVAILABLE:
        logger.warning(
            "dbus-python library not available. Cannot send notification via dbus."
        )
        return False

    try:
        # Get the session bus
        bus = dbus.SessionBus()
        # Get the notification service proxy object
        notify_proxy = bus.get_object(
            "org.freedesktop.Notifications", "/org/freedesktop/Notifications"
        )
        # Get the interface to call methods on the proxy
        notify_interface = dbus.Interface(notify_proxy, "org.freedesktop.Notifications")

        # Call the Notify method
        # Parameters: app_name, replaces_id, app_icon, summary, body, actions, hints, expire_timeout
        notify_interface.Notify(
            "ChromaDesk",  # app_name
            dbus.UInt32(0),  # replaces_id (0 means create a new notification)
            icon_name,  # app_icon (use a standard Freedesktop icon name)
            title,  # summary (the title)
            message,  # body (the main message)
            dbus.Array([], signature="s"),  # actions (list of action identifiers)
            dbus.Dictionary({}, signature="sv"),  # hints (extra options, e.g., urgency)
            dbus.Int32(
                5000
            ),  # expire_timeout in milliseconds (0 = default, -1 = never)
        )
        logger.info(f"Notification sent via dbus-python: '{title}'")
        return True
    # Handle common DBus errors
    except dbus.exceptions.DBusException as e:
        logger.warning(f"DBusException while sending notification via dbus-python: {e}")
        logger.warning("Ensure DBus session bus is running and accessible.")
        return False
    # Catch any other unexpected errors
    except Exception as e:
        logger.error(f"An unexpected error occurred checking gsettings keys: {e}")
        return False


def send_notification(title: str, message: str):
    """
    Attempts to send a desktop notification.

    It first tries using the `notify2` library (if available),
    and falls back to using `dbus-python` directly if the first attempt fails
    or `notify2` is not installed.

    Args:
        title: The title of the notification.
        message: The main body text of the notification.
    """
    logger.debug(f"Attempting to send notification: '{title}' - '{message}'")

    # Define a potential path to a custom icon (adjust if needed)
    # For now, we'll let the libraries use standard icons.
    # icon_path = Path(__file__).parent.parent / "data" / "icons" / "io.github.anantdark.chromadesk.png"
    # icon_path_str = str(icon_path.resolve()) if icon_path.exists() else None
    icon_path_str = None  # Using None to rely on fallback icons

    # --- Try notify2 first ---
    if _send_notification_notify2(title, message, icon_path_str):
        return  # Success!

    # --- Fallback to dbus-python ---
    # Use a standard Freedesktop icon name for broader compatibility
    standard_icon_name = "dialog-information"
    # Alternative icon name suggestion: "preferences-desktop-wallpaper"
    if _send_notification_dbus(title, message, icon_name=standard_icon_name):
        return  # Success!

    # --- If both methods fail ---
    logger.warning(
        "Failed to send notification using all available methods (notify2/dbus-python)."
    )


# ==============================================================================
# Wallpaper Setting Functions
# ==============================================================================


def _check_gsettings_key_exists(schema: str, key: str) -> bool:
    """
    Checks if a specific key exists within a gsettings schema using the CLI tool.

    Args:
        schema: The gsettings schema path (e.g., "org.gnome.desktop.background").
        key: The specific key name to check for (e.g., "picture-uri-dark").

    Returns:
        True if the key exists and can be listed, False otherwise.
    """
    # Ensure the command-line tool is available first
    if not shutil.which("gsettings"):
        logger.warning("Cannot check gsettings key: 'gsettings' command not found.")
        return False  # Assume key doesn't exist if we can't check

    cmd = ["gsettings", "list-keys", schema]
    try:
        # Execute 'gsettings list-keys <schema>'
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True, timeout=5
        )
        key_list = result.stdout.splitlines()  # Get list of keys in the schema
        exists = key in key_list  # Check if our target key is in the list
        logger.debug(f"Schema '{schema}' keys checked. Key '{key}' exists: {exists}")
        return exists
    except FileNotFoundError:
        # Defensive check, though shutil.which should catch it.
        logger.error(f"Command failed: '{cmd[0]}' not found during key check.")
        return False
    except subprocess.TimeoutExpired:
        logger.error(f"Command timed out while listing keys for schema '{schema}'.")
        return False
    except subprocess.CalledProcessError as e:
        # gsettings might fail if the schema itself doesn't exist
        logger.warning(
            f"Command failed while listing keys for schema '{schema}'. "
            f"Maybe schema not installed? Stderr: {e.stderr.strip()}"
        )
        return False  # Failed to list keys, assume the specific key doesn't exist
    except Exception as e:
        logger.error(
            f"An unexpected error occurred checking gsettings keys: {e}", exc_info=True
        )
        return False


def set_gnome_wallpaper(image_path: Path) -> bool:
    """
    Sets the GNOME desktop wallpaper using the gsettings command-line tool.

    This function adapts its behavior based on the desktop session type
    (X11 vs. Wayland/other) and the availability of the 'picture-uri-dark'
    gsettings key to maximize compatibility across different GNOME versions.
    Sets the GNOME desktop wallpaper using the gsettings command-line tool.

    This function adapts its behavior based on the desktop session type
    (X11 vs. Wayland/other) and the availability of the 'picture-uri-dark'
    gsettings key to maximize compatibility across different GNOME versions.

    Args:
        image_path: The absolute Path object pointing to the desired wallpaper image.
        image_path: The absolute Path object pointing to the desired wallpaper image.

    Returns:
        True if the necessary gsettings commands were executed successfully,
        False otherwise. Note: Success indicates the commands ran without error,
        but doesn't guarantee the desktop visually updated if there are other
        desktop environment issues.
        True if the necessary gsettings commands were executed successfully,
        False otherwise. Note: Success indicates the commands ran without error,
        but doesn't guarantee the desktop visually updated if there are other
        desktop environment issues.
    """
    if not image_path.is_file():
        logger.error(f"Wallpaper image file not found: {image_path}")
        return False

    # Check if gsettings command exists early on
    # Check if gsettings command exists early on
    if not shutil.which("gsettings"):
        logger.error("'gsettings' command not found. Cannot set GNOME wallpaper.")
        return False

    # Convert the Path object to an absolute file URI (e.g., "file:///...")
    # Convert the Path object to an absolute file URI (e.g., "file:///...")
    try:
        abs_image_path = image_path.resolve(strict=True)  # Ensures path exists
        abs_image_path = image_path.resolve(strict=True)  # Ensures path exists
        file_uri = abs_image_path.as_uri()
    except FileNotFoundError:
        logger.error(f"Wallpaper image file not found (during resolve): {image_path}")
        return False
    except Exception as e:
        logger.error(f"Error resolving path or creating file URI for {image_path}: {e}")
        return False

    # --- Determine which keys need to be set based on environment ---
    session_type = os.environ.get("XDG_SESSION_TYPE", "unknown").lower()
    is_x11 = session_type == "x11"
    should_set_dark_uri = False  # Default to not setting the dark URI

    if is_x11:
        # On X11, GNOME traditionally uses only picture-uri for both light/dark
        logger.info("X11 session detected. Will only set 'picture-uri'.")
    else:
        # On Wayland (or unknown sessions), check if the modern 'picture-uri-dark' exists
        logger.info(
            f"Session type '{session_type}' detected (or unknown). Checking for '{KEY_PICTURE_URI_DARK}'."
        )
        if _check_gsettings_key_exists(SCHEMA_BACKGROUND, KEY_PICTURE_URI_DARK):
            logger.info(
                f"Key '{KEY_PICTURE_URI_DARK}' found. Will set both light and dark URIs."
            )
            should_set_dark_uri = True
        else:
            logger.info(
                f"Key '{KEY_PICTURE_URI_DARK}' not found. Will only set 'picture-uri'."
            )

    # --- Build the list of commands to execute ---
    # --- Determine which keys need to be set based on environment ---
    session_type = os.environ.get("XDG_SESSION_TYPE", "unknown").lower()
    is_x11 = session_type == "x11"
    should_set_dark_uri = False  # Default to not setting the dark URI

    if is_x11:
        # On X11, GNOME traditionally uses only picture-uri for both light/dark
        logger.info("X11 session detected. Will only set 'picture-uri'.")
    else:
        # On Wayland (or unknown sessions), check if the modern 'picture-uri-dark' exists
        logger.info(
            f"Session type '{session_type}' detected (or unknown). Checking for '{KEY_PICTURE_URI_DARK}'."
        )
        if _check_gsettings_key_exists(SCHEMA_BACKGROUND, KEY_PICTURE_URI_DARK):
            logger.info(
                f"Key '{KEY_PICTURE_URI_DARK}' found. Will set both light and dark URIs."
            )
            should_set_dark_uri = True
        else:
            logger.info(
                f"Key '{KEY_PICTURE_URI_DARK}' not found. Will only set 'picture-uri'."
            )

    # --- Build the list of commands to execute ---
    commands_to_run = [
        # 1. Set picture options (e.g., how the image is scaled)
        [
            "gsettings",
            "set",
            SCHEMA_BACKGROUND,
            KEY_PICTURE_OPTIONS,
            "zoom",
        ],  # 'zoom' is usually a good default
        # 2. Always set the primary picture URI
        # 1. Set picture options (e.g., how the image is scaled)
        [
            "gsettings",
            "set",
            SCHEMA_BACKGROUND,
            KEY_PICTURE_OPTIONS,
            "zoom",
        ],  # 'zoom' is usually a good default
        # 2. Always set the primary picture URI
        ["gsettings", "set", SCHEMA_BACKGROUND, KEY_PICTURE_URI, file_uri],
    ]

    # 3. Conditionally add the command for the dark URI if needed
    if should_set_dark_uri:
        commands_to_run.append(
            ["gsettings", "set", SCHEMA_BACKGROUND, KEY_PICTURE_URI_DARK, file_uri]
        )

    logger.info(
        f"Attempting to set wallpaper using {len(commands_to_run)} gsettings command(s). Target URI: {file_uri}"
    )

    # --- Execute the gsettings commands ---
    # 3. Conditionally add the command for the dark URI if needed
    if should_set_dark_uri:
        commands_to_run.append(
            ["gsettings", "set", SCHEMA_BACKGROUND, KEY_PICTURE_URI_DARK, file_uri]
        )

    logger.info(
        f"Attempting to set wallpaper using {len(commands_to_run)} gsettings command(s). Target URI: {file_uri}"
    )

    # --- Execute the gsettings commands ---
    success = True
    for cmd in commands_to_run:
        try:
            logger.debug(f"Running command: {' '.join(cmd)}")
            # Run the command, check for non-zero exit code, capture output
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=True, timeout=10
            )
            logger.debug("Command successful.")  # Keep success log concise
            logger.debug(f"Running command: {' '.join(cmd)}")
            # Run the command, check for non-zero exit code, capture output
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=True, timeout=10
            )
            logger.debug("Command successful.")  # Keep success log concise
        except FileNotFoundError:
            logger.error(f"Command failed: '{cmd[0]}' not found. Check PATH.")
            logger.error(f"Command failed: '{cmd[0]}' not found. Check PATH.")
            success = False
            break  # Cannot continue if gsettings is missing
            break  # Cannot continue if gsettings is missing
        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out: {' '.join(cmd)}")
            success = False
            break  # Stop if a command hangs
            break  # Stop if a command hangs
        except subprocess.CalledProcessError as e:
            # This catches gsettings commands that exit with an error
            # This catches gsettings commands that exit with an error
            logger.error(f"Command failed: {' '.join(cmd)}")
            logger.error(f"  Return Code: {e.returncode}")
            logger.error(f"  Stderr: {e.stderr.strip()}")
            # If setting the main URI fails, no point setting dark. If options fail, maybe continue?
            # For simplicity, we break on the first error.
            # If setting the main URI fails, no point setting dark. If options fail, maybe continue?
            # For simplicity, we break on the first error.
            success = False
            break
            break
        except Exception as e:
            # Catch any other unexpected exceptions during subprocess execution
            logger.error(
                f"An unexpected error occurred running command {' '.join(cmd)}: {e}",
                exc_info=True,
            )
            # Catch any other unexpected exceptions during subprocess execution
            logger.error(
                f"An unexpected error occurred running command {' '.join(cmd)}: {e}",
                exc_info=True,
            )
            success = False
            break

    # Final status log
    # Final status log
    if success:
        logger.info("Successfully executed necessary gsettings commands for wallpaper.")
        # Attempt to send a success notification AFTER setting the wallpaper
        send_notification(
            "ChromaDesk", f"Wallpaper successfully set to {image_path.name}"
        )
    else:
        logger.error(
            "Failed to execute all necessary gsettings commands for wallpaper."
        )
        # Attempt to send a failure notification
        send_notification("ChromaDesk Error", "Failed to set wallpaper. Check logs.")

    return success
