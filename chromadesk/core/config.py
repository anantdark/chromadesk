# chromadesk/chromadesk/core/config.py
import configparser
import logging
from pathlib import Path
from typing import Any

# Configure basic logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Define constants
APP_NAME = "ChromaDesk"  # Used for config dir name
CONFIG_DIR = Path.home() / ".config" / APP_NAME.lower()
CONFIG_FILE = CONFIG_DIR / "config.ini"

# Default settings
DEFAULT_SETTINGS = {
    "Settings": {
        "enabled": "false",  # Automatic daily updates disabled by default
        "region": "en-IN",  # Default Bing market region
        "keep_history": "7",  # Number of Bing wallpapers to keep
        "wallpaper_dir": str(
            Path.home() / "Pictures" / "wallpapers"
        ),  # Default storage location
    },
    "State": {
        "last_update_date": "",  # Stores YYYY-MM-DD of last successful Bing update
        "installed_appimage_path": "",  # Stores absolute path where AppImage was installed
    },
}


def ensure_config_dir_exists():
    """Ensures only the configuration directory exists."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        return True
    except OSError as e:
        logging.error(f"Error creating config directory {CONFIG_DIR}: {e}")
        return False


def create_default_config_if_missing():
    """Creates the default config file ONLY if it doesn't exist."""
    if not ensure_config_dir_exists():
        return False  # Cannot create file if directory fails

    if not CONFIG_FILE.is_file():
        logging.info(f"Config file not found. Creating default config at {CONFIG_FILE}")
        try:
            config = configparser.ConfigParser()
            config.read_dict(DEFAULT_SETTINGS)
            with open(CONFIG_FILE, "w") as configfile:
                config.write(configfile)
            return True
        except (OSError, configparser.Error) as e:
            logging.error(
                f"Error writing initial default config file {CONFIG_FILE}: {e}"
            )
            return False
    return True  # File already exists


def load_config():
    """Loads the configuration, creates defaults if missing, and ensures all keys exist."""
    config = configparser.ConfigParser()

    # First, ensure the default file exists if it's completely missing
    if not create_default_config_if_missing():
        # If creation failed, return in-memory defaults, don't try to read/write
        logging.warning(
            "Failed to create or access config file. Using in-memory defaults."
        )
        config.read_dict(DEFAULT_SETTINGS)
        return config

    # Try reading the existing file
    try:
        read_files = config.read(CONFIG_FILE)
        if not read_files:
            # This case should ideally not happen if create_default_config_if_missing worked,
            # but handle it defensively.
            logging.warning(
                f"Config file {CONFIG_FILE} reported as existing but couldn't be read. Using defaults."
            )
            config.read_dict(DEFAULT_SETTINGS)

    except configparser.Error as e:
        logging.error(f"Error reading config file {CONFIG_FILE}: {e}. Using defaults.")
        config = configparser.ConfigParser()  # Start fresh
        config.read_dict(DEFAULT_SETTINGS)

    # --- Check for and add missing keys/sections ---
    needs_save = False
    for section, defaults in DEFAULT_SETTINGS.items():
        if not config.has_section(section):
            config.add_section(section)
            logging.info(f"Added missing section [{section}] to config.")
            needs_save = True
        for key, value in defaults.items():
            if not config.has_option(section, key):
                config.set(section, key, value)
                logging.info(
                    f"Added missing key '{key}' to section [{section}] in config."
                )
                needs_save = True

    # Save if any keys were added
    if needs_save:
        save_config(config)  # Use the separate save function

    return config


def save_config(config):
    """Saves the configuration object to the INI file."""
    if not ensure_config_dir_exists():
        logging.error("Cannot save config, directory creation/access failed.")
        return False
    try:
        with open(CONFIG_FILE, "w") as configfile:
            config.write(configfile)
        # Only log info on explicit saves requested by user actions later,
        # or reduce noise for automatic key additions.
        # logging.info(f"Configuration saved to {CONFIG_FILE}")
        return True
    except (OSError, configparser.Error) as e:
        logging.error(f"Error writing config file {CONFIG_FILE}: {e}")
        return False


# --- Helper Functions remain the same ---
def get_setting(section, key, fallback=None) -> Any:
    """Helper function to get a specific setting."""
    config = load_config()
    # Use config.getboolean() etc. for typed values if needed later
    return config.get(section, key, fallback=fallback)


def set_setting(section, key, value):
    """Helper function to set a specific setting and save."""
    config = load_config()
    if not config.has_section(section):
        config.add_section(section)
    config.set(section, key, str(value))  # Ensure value is string
    if save_config(config):
        logging.info(f"Setting [{section}] {key} = {value} saved.")
    else:
        logging.error(f"Failed to save setting [{section}] {key} = {value}.")


def delete_config_file() -> bool:
    """Deletes the application's configuration file."""
    if not CONFIG_FILE.is_file():
        logging.warning(
            f"Config file {CONFIG_FILE} already doesn't exist. Cannot delete."
        )
        return True  # Consider it a success if it's already gone

    try:
        CONFIG_FILE.unlink()
        logging.info(f"Successfully deleted config file: {CONFIG_FILE}")
        # Optionally, try removing the directory if it's empty, but be cautious
        # try:
        #     CONFIG_DIR.rmdir() # Fails if not empty
        #     logging.info(f"Successfully deleted empty config directory: {CONFIG_DIR}")
        # except OSError:
        #     pass # Directory wasn't empty or other error, ignore
        return True
    except OSError as e:
        logging.error(f"Error deleting config file {CONFIG_FILE}: {e}")
        return False
    except Exception as e:
        logging.error(
            f"Unexpected error deleting config file {CONFIG_FILE}: {e}", exc_info=True
        )
        return False


# Example Usage (can be tested independently)
if __name__ == "__main__":
    print(f"Config Directory: {CONFIG_DIR}")
    print(f"Config File: {CONFIG_FILE}")

    # Load config (will create + add keys if necessary)
    current_config = load_config()

    print("\nCurrent Config (after loading and potential updates):")
    for section in current_config.sections():
        print(f"[{section}]")
        for key, value in current_config.items(section):
            print(f"{key} = {value}")

    # Example of getting/setting a value
    region = get_setting("Settings", "region")
    print(f"\nCurrent region: {region}")

    print("\nSetting region to 'de-DE'...")
    set_setting("Settings", "region", "de-DE")

    region = get_setting("Settings", "region")
    print(f"New region: {region}")

    print("\nSetting region back to 'en-US'...")
    set_setting("Settings", "region", "en-US")
    region = get_setting("Settings", "region")
    print(f"Restored region: {region}")

    # Example state update
    from datetime import date

    today_str = date.today().isoformat()
    print(f"\nSetting last_update_date to {today_str}")
    set_setting("State", "last_update_date", today_str)
    last_update = get_setting("State", "last_update_date")
    print(f"Current last_update_date: {last_update}")

    # Test case: Manually delete a key from the file and reload
    print("\nTesting missing key addition:")
    cfg_test = load_config()
    if cfg_test.has_option("Settings", "keep_history"):
        cfg_test.remove_option("Settings", "keep_history")
        save_config(cfg_test)
        print("Temporarily removed 'keep_history'. Reloading...")
        cfg_reloaded = load_config()
        if cfg_reloaded.has_option("Settings", "keep_history"):
            print("Reloaded config successfully added 'keep_history' back.")
            print(f"Value: {cfg_reloaded.get('Settings', 'keep_history')}")
        else:
            print("ERROR: Reloaded config did NOT add 'keep_history' back.")
    else:
        print("Could not test missing key, 'keep_history' already missing?")
