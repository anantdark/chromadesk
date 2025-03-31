import argparse
import logging
import os
import sys
from importlib.metadata import \
    version as get_version  # Import earlier for version/internal commands
from pathlib import Path

# Import core config early for internal command use
from chromadesk.core import config as core_config

# Configure logging
log_format = "%(asctime)s - %(levelname)s - %(message)s"
log_file_path = Path.home() / ".config" / "chromadesk" / "chromadesk.log"
try:
    log_file_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[logging.FileHandler(log_file_path), logging.StreamHandler()],
    )
except Exception as e:
    # Fallback basic logging if file handler fails
    logging.basicConfig(level=logging.WARNING, format=log_format)
    logging.critical(f"Failed to configure file logging: {e}")

logger = logging.getLogger(__name__)

# Suppress Mesa Intel warning
os.environ["MESA_DEBUG"] = "silent"


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="ChromaDesk - Daily Wallpaper Changer")

    # GUI mode (default)
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Launch the GUI application (default behavior if no args)",
    )

    # Headless update mode
    parser.add_argument(
        "--headless", action="store_true", help="Run the daily wallpaper update check"
    )

    # Version info
    parser.add_argument(
        "--version", action="store_true", help="Show version information"
    )

    # Internal command for installer (hidden from help)
    parser.add_argument(
        "--internal-set-config",
        nargs=3,
        metavar=("SECTION", "KEY", "VALUE"),
        help=argparse.SUPPRESS,
    )

    args = parser.parse_args()

    # If no specific mode is requested, default to GUI
    # (Ensure internal command doesn't trigger default GUI)
    if not args.headless and not args.version and not args.internal_set_config:
        args.gui = True

    return args


def main():
    """Main entry point for ChromaDesk."""
    args = parse_args()

    # Handle internal config setting command first
    if args.internal_set_config:
        section, key, value = args.internal_set_config
        try:
            logger.info(
                f"Internal command: Setting config [{section}].{key} = '{value}'"
            )
            # Ensure config dir exists first
            if not core_config.ensure_config_dir_exists():
                raise RuntimeError("Failed to ensure config directory exists.")
            # Create default if it doesn't exist (might be first run after install)
            if not core_config.create_default_config_if_missing():
                raise RuntimeError("Failed to create default config file.")

            success = core_config.set_setting(section, key, value)
            if success:
                logger.info("Internal command: Config updated successfully.")
                return 0  # Exit successfully
            else:
                logger.error(
                    "Internal command: Failed to update config using set_setting."
                )
                return 1  # Exit with error
        except Exception as e:
            logger.critical(
                f"Internal command: Error setting config: {e}", exc_info=True
            )
            return 1  # Exit with error

    # Show version info if requested
    if args.version:
        try:
            ver = get_version("chromadesk")
            print(f"ChromaDesk version {ver}")
        except Exception:  # More general exception if metadata fails
            print("ChromaDesk (version unknown)")
        return 0

    # Handle headless update mode
    if args.headless:
        logger.info("Running in --headless update mode")
        # Import necessary core functions for headless operation
        try:
            # config already imported
            from datetime import date

            from chromadesk.core import bing as core_bing
            from chromadesk.core import downloader as core_downloader
            from chromadesk.core import history as core_history
            from chromadesk.core import wallpaper as core_wallpaper
        except ImportError as e:
            logger.critical(f"Failed to import core components for headless mode: {e}")
            return 1

        # --- Perform the headless update logic ---
        success = False
        try:
            logger.info("Headless: Starting daily update check.")

            # 1. Check config if enabled (although timer shouldn't run if not)
            config = core_config.load_config()
            if config.getboolean("Settings", "enabled", fallback=False):
                logger.info("Headless: Daily updates are enabled in config.")

                # 2. Get region
                region = config.get("Settings", "region", fallback="en-US")

                # 3. Fetch Bing info
                logger.info(f"Headless: Fetching Bing info for region: {region}")
                bing_info = core_bing.fetch_bing_wallpaper_info(region=region)

                if bing_info and bing_info.get("full_url"):
                    logger.info(
                        f"Headless: Successfully fetched Bing info for date {bing_info.get('date')}"
                    )

                    # 4. Check if already updated today
                    today_str = date.today().isoformat()
                    last_update_date = config.get(
                        "State", "last_update_date", fallback=""
                    )
                    if last_update_date == today_str:
                        logger.info(
                            f"Headless: Wallpaper already updated today ({today_str}). Skipping."
                        )
                        success = True  # Consider it success if already done
                    else:
                        logger.info(
                            f"Headless: Last update was {last_update_date}, proceeding with update for {today_str}."
                        )
                        # 5. Download image
                        if not core_history.ensure_wallpaper_dir():
                            raise RuntimeError(
                                "Headless: Cannot create wallpaper directory."
                            )

                        wallpaper_dir = core_history.get_wallpaper_dir()
                        filename = core_history.get_bing_filename(
                            bing_info["date"], bing_info["full_url"]
                        )
                        save_path = wallpaper_dir / filename

                        if save_path.is_file():
                            logger.info(
                                f"Headless: Image {filename} already exists. Using existing file."
                            )
                            download_ok = True
                        else:
                            logger.info(
                                f"Headless: Downloading image to {save_path}..."
                            )
                            download_ok = core_downloader.download_image(
                                bing_info["full_url"], save_path
                            )

                        if download_ok:
                            logger.info(
                                "Headless: Download successful (or file existed)."
                            )
                            # 6. Set Wallpaper
                            logger.info(f"Headless: Setting wallpaper to {save_path}")
                            set_ok = core_wallpaper.set_gnome_wallpaper(save_path)

                            if set_ok:
                                logger.info("Headless: Wallpaper set successfully.")
                                # 7. Update state and cleanup history
                                core_config.set_setting(
                                    "State", "last_update_date", today_str
                                )
                                keep_count = config.getint(
                                    "Settings", "keep_history", fallback=7
                                )
                                core_history.cleanup_wallpaper_history(keep=keep_count)

                                # 8. Send notification
                                try:
                                    title = bing_info.get("title", "Unknown Title")
                                    core_wallpaper.send_notification(
                                        "ChromaDesk Update",
                                        f"Wallpaper updated successfully to: {title}",
                                    )
                                except Exception as notify_err:
                                    logger.warning(
                                        f"Headless: Failed to send notification: {notify_err}"
                                    )

                                success = True
                            else:
                                logger.error("Headless: Failed to set wallpaper.")
                        else:
                            logger.error("Headless: Failed to download image.")
                else:
                    logger.error("Headless: Failed to fetch Bing wallpaper info.")
            else:
                logger.info("Headless: Daily updates are disabled in config. Skipping.")
                success = True  # Not an error if disabled

        except Exception as e:
            logger.critical(
                f"Headless: An error occurred during the update process: {e}",
                exc_info=True,
            )
            success = False
        # --- End headless update logic ---

        logger.info(f"Headless update finished. Success: {success}")
        return 0 if success else 1

    # Handle GUI mode
    elif args.gui:
        logger.info("Starting GUI application")
        try:
            from PySide6.QtWidgets import QApplication
            from chromadesk.ui.main_window import MainWindow
        except ImportError as e:
            logger.critical(f"Failed to import GUI components: {e}")
            return 1

        try:
            app = QApplication(sys.argv)
            app.setApplicationName("ChromaDesk")
            app.setOrganizationName("chromadesk")

            window = MainWindow()
            logger.info("MainWindow initialized.")
            window.show()
            result = app.exec()
            return result
        except Exception as e:
            logger.critical(
                f"An error occurred during GUI execution: {e}", exc_info=True
            )
            return 1


if __name__ == "__main__":
    logger.debug("Script starting in __main__...")
    result = main()
    logger.debug(f"main() finished with exit code: {result}")
    sys.exit(result)
