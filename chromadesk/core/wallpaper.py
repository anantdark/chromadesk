# chromadesk/chromadesk/core/wallpaper.py
import subprocess
import logging
from pathlib import Path
import shutil

logger = logging.getLogger(__name__)

# Define GNOME settings schemas and keys
SCHEMA_BACKGROUND = "org.gnome.desktop.background"
KEY_PICTURE_URI = "picture-uri"
KEY_PICTURE_URI_DARK = "picture-uri-dark" # Set both for light/dark theme consistency
KEY_PICTURE_OPTIONS = "picture-options" # Controls how image is scaled (e.g., 'zoom', 'scaled', 'centered')

def _send_notification_notify2(title: str, message: str, icon_path: str | None = None):
    """Sends a notification using the notify2 library."""
    try:
        import notify2 # Import inside function
        import dbus # Import for exception handling

        notify2.init("ChromaDesk")
        icon = icon_path if icon_path and Path(icon_path).exists() else "dialog-information" # Fallback icon
        notification = notify2.Notification(title, message, icon)
        notification.set_urgency(notify2.URGENCY_LOW)
        notification.set_timeout(5000) # milliseconds
        notification.show()
        logger.info(f"Notification sent via notify2: '{title}'")
        return True
    except ImportError:
        logger.debug("notify2 library not found, falling back.")
        return False
    except dbus.exceptions.DBusException as e:
        logger.warning(f"DBusException while sending notification via notify2: {e}")
        logger.warning("This might happen if the DBus session bus is unavailable (e.g., running outside graphical session without correct env vars).")
        return False
    except Exception as e:
        logger.error(f"Error sending notification via notify2: {e}", exc_info=True)
        return False

def _send_notification_dbus(title: str, message: str, icon_name: str = "dialog-information"):
    """Sends a notification using raw dbus-python (fallback)."""
    try:
        import dbus # Import inside function

        bus = dbus.SessionBus()
        notify_proxy = bus.get_object('org.freedesktop.Notifications', '/org/freedesktop/Notifications')
        notify_interface = dbus.Interface(notify_proxy, 'org.freedesktop.Notifications')

        # Parameters for Notify method:
        # app_name, replaces_id, app_icon, summary, body, actions, hints, expire_timeout
        notify_interface.Notify(
            "ChromaDesk",      # app_name
            dbus.UInt32(0),    # replaces_id (0 means new notification)
            icon_name,         # app_icon (use a standard Freedesktop icon name)
            title,             # summary (title)
            message,           # body
            dbus.Array([], signature='s'), # actions
            dbus.Dictionary({}, signature='sv'), # hints
            dbus.Int32(5000)    # expire_timeout (milliseconds)
        )
        logger.info(f"Notification sent via dbus-python: '{title}'")
        return True
    except ImportError:
        logger.warning("dbus-python library not found. Cannot send notification via dbus.")
        return False
    except dbus.exceptions.DBusException as e:
        logger.warning(f"DBusException while sending notification via dbus-python: {e}")
        logger.warning("Ensure DBus session bus is running and accessible.")
        return False
    except Exception as e:
        logger.error(f"Error sending notification via dbus-python: {e}", exc_info=True)
        return False

def send_notification(title: str, message: str):
    """Attempts to send a desktop notification, preferring notify2."""
    logger.debug(f"Attempting to send notification: '{title}' - '{message}'")
    
    # Potential icon path (relative to this file? Needs thought)
    # For now, let notify2/dbus use standard icons or its default
    # icon_path = Path(__file__).parent.parent / "data" / "icons" / "io.github.anantdark.chromadesk.png"
    icon_path_str = None # str(icon_path.resolve()) if icon_path.exists() else None

    # Try notify2 first
    if _send_notification_notify2(title, message, icon_path_str):
        return

    # Fallback to dbus-python using a standard icon name
    if _send_notification_dbus(title, message, icon_name="dialog-information"): # Or maybe use "preferences-desktop-wallpaper"?
        return

    logger.warning("Failed to send notification using all available methods.")

def set_gnome_wallpaper(image_path: Path) -> bool:
    """
    Sets the GNOME desktop wallpaper using the gsettings command.

    Args:
        image_path (Path): The absolute path to the image file.

    Returns:
        bool: True if the wallpaper was set successfully, False otherwise.
    """
    if not image_path.is_file():
        logger.error(f"Wallpaper image file not found: {image_path}")
        return False

    # Check if gsettings command exists
    if not shutil.which("gsettings"):
         logger.error("'gsettings' command not found. Cannot set GNOME wallpaper.")
         # Consider notifying the user more explicitly in the UI later
         return False

    # Convert the Path object to a file URI (e.g., "file:///home/user/Pictures/image.jpg")
    # Ensure the path is absolute first
    try:
        abs_image_path = image_path.resolve(strict=True)
        file_uri = abs_image_path.as_uri()
    except FileNotFoundError:
         logger.error(f"Wallpaper image file not found (during resolve): {image_path}")
         return False
    except Exception as e:
         logger.error(f"Error resolving path or creating file URI for {image_path}: {e}")
         return False


    logger.info(f"Setting GNOME wallpaper to: {file_uri}")
    commands_to_run = [
        ['gsettings', 'set', SCHEMA_BACKGROUND, KEY_PICTURE_OPTIONS, 'zoom'], # or 'scaled', 'stretched'
        ['gsettings', 'set', SCHEMA_BACKGROUND, KEY_PICTURE_URI, file_uri],
    ]

    success = True
    for cmd in commands_to_run:
        try:
            # Run the command, capture output, check return code
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=5)
            logger.debug(f"Command {' '.join(cmd)} successful. Output: {result.stdout.strip()}")
        except FileNotFoundError:
            logger.error(f"Command failed: '{cmd[0]}' not found.")
            success = False
            break # Stop if gsettings fails
        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out: {' '.join(cmd)}")
            success = False
            break
        except subprocess.CalledProcessError as e:
            # This catches non-zero exit codes
            logger.error(f"Command failed: {' '.join(cmd)}")
            logger.error(f"  Return Code: {e.returncode}")
            logger.error(f"  Stderr: {e.stderr.strip()}")
            logger.error(f"  Stdout: {e.stdout.strip()}")
            success = False
            break # Stop on first error
        except Exception as e:
             logger.error(f"An unexpected error occurred running command {' '.join(cmd)}: {e}")
             success = False
             break

    if success:
        logger.info("Successfully set GNOME wallpaper.")
    else:
        logger.error("Failed to set GNOME wallpaper.")

    return success

# Example Usage (can be tested independently)
if __name__ == "__main__":
    print("Testing GNOME Wallpaper Setter...")
    # WARNING: This will actually change your desktop wallpaper if it succeeds!

    # Option 1: Use one of the previously downloaded test images
    test_image_path = Path("./temp_downloads/test_bing.jpg").resolve()
    # Option 2: Specify a path to any other JPG/PNG on your system
    # test_image_path = Path.home() / "Pictures" / "my_other_wallpaper.jpg"

    if test_image_path.is_file():
        print(f"\nAttempting to set wallpaper to: {test_image_path}")
        set_success = set_gnome_wallpaper(test_image_path)
        print(f"Wallpaper set successfully: {set_success}")

        if set_success:
            print("\nCheck your desktop background!")
            print("(You might need to manually change it back later)")
        else:
            print("\nWallpaper setting failed. Check logs above for errors.")
    else:
        print(f"\nTest image not found: {test_image_path}")
        print("Please download an image first (e.g., run downloader.py) or specify a valid path.")
