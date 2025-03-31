# chromadesk/chromadesk/services/manager.py
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Import config module directly
from ..core import config as core_config

logger = logging.getLogger(__name__)

# --- Constants ---
SERVICE_NAME = "chromadesk-daily"
SERVICE_FILE = f"{SERVICE_NAME}.service"
TIMER_FILE = f"{SERVICE_NAME}.timer"
SYSTEMD_USER_DIR = Path.home() / ".config" / "systemd" / "user"
TEMPLATE_DIR = Path(__file__).parent / "templates"  # Path relative to this file

# --- Helper Functions ---


def _run_systemctl(
    command: list, check: bool = False, capture: bool = False
) -> subprocess.CompletedProcess | None:
    """Runs a systemctl --user command."""
    base_cmd = ["systemctl", "--user"]
    full_cmd = base_cmd + command
    logger.debug(f"Running systemctl command: {' '.join(full_cmd)}")
    try:
        result = subprocess.run(
            full_cmd,
            check=check,  # Raise exception on non-zero exit code if True
            capture_output=capture,  # Capture stdout/stderr if True
            text=True,  # Work with text streams
            timeout=10,  # Prevent hanging
        )
        if capture:
            logger.debug(f"systemctl stdout: {result.stdout.strip()}")
            logger.debug(f"systemctl stderr: {result.stderr.strip()}")
        logger.debug(f"systemctl finished with code: {result.returncode}")
        return result
    except FileNotFoundError:
        logger.error("'systemctl' command not found. Cannot manage systemd units.")
        return None
    except subprocess.TimeoutExpired:
        logger.error(f"systemctl command timed out: {' '.join(full_cmd)}")
        return None
    except subprocess.CalledProcessError as e:
        # Error is logged automatically if check=True caused it
        if not check:  # Log error if check was False but it still failed somehow
            logger.error(
                f"systemctl command failed: {' '.join(full_cmd)} (Code: {e.returncode})"
            )
            if capture:
                logger.error(f"  Stderr: {e.stderr.strip()}")
        return None  # Indicate failure
    except Exception as e:
        logger.error(f"Unexpected error running systemctl: {e}", exc_info=True)
        return None


def _get_python_executable() -> str | None:
    """Gets the preferred Python executable path, prioritizing venv.
    Returns None if no suitable executable is found.
    """
    project_root = _get_project_root()
    venv_python = None

    # 1. Check for virtual environment Python
    if project_root:
        venv_path = Path(project_root) / ".venv" / "bin" / "python"
        if venv_path.is_file():
            try:
                venv_python = str(venv_path.resolve(strict=True))
                logger.debug(f"Using virtual environment Python: {venv_python}")
                return venv_python
            except Exception as e:
                logger.warning(
                    f"Found venv python {venv_path} but failed to resolve: {e}"
                )
        else:
            logger.debug("Virtual environment Python not found at expected location.")

    # 2. Check for system 'python3' in PATH
    system_python3 = shutil.which("python3")
    if system_python3:
        logger.debug(f"Using system python3: {system_python3}")
        return system_python3

    # 3. Check for system 'python' in PATH
    system_python = shutil.which("python")
    if system_python:
        logger.debug(f"Using system python: {system_python}")
        return system_python

    # 4. REMOVED Fallback to sys.executable
    #    This was causing it to pick up the Cursor AppImage path.
    #    If we reach here, we haven't found a suitable Python.
    # sys_executable_path = sys.executable
    # if sys_executable_path:
    #     logger.warning(f"Could not find venv or system Python. Falling back to sys.executable: {sys_executable_path}")
    #     logger.warning("This might be incorrect if running inside an unrelated AppImage (e.g., an IDE).")
    #     return str(Path(sys_executable_path).resolve())

    # 5. Absolute failure
    logger.error(
        "Could not determine any suitable Python executable path (checked venv, python3, python)."
    )
    return None


def _get_script_path() -> str:
    """Gets the absolute path to the main.py script."""
    # Assumes main.py is in the parent directory of this 'services' dir
    try:
        script_path = Path(__file__).parent.parent / "main.py"
        abs_path = str(script_path.resolve(strict=True))
        logger.debug(f"Found main script path: {abs_path}")
        return abs_path
    except FileNotFoundError:
        logger.error("main.py not found relative to manager.py!")
        return ""  # Should cause failure later


def _get_project_root() -> str | None:
    """Gets the absolute path to the project root directory.
    Returns None if resolution fails.
    """
    # Assumes project root is the parent of the 'chromadesk' package directory
    # where main.py resides (i.e., parent of parent of this file's dir)
    try:
        root_path = Path(__file__).parent.parent.parent
        # Use resolve() without strict=True initially
        abs_path = str(root_path.resolve())
        # Basic check: does pyproject.toml exist?
        if (root_path / "pyproject.toml").is_file():
            logger.debug(f"Using project root (working directory): {abs_path}")
            return abs_path
        else:
            logger.warning(
                f"Determined path {abs_path} does not appear to be project root (pyproject.toml missing). Returning None."
            )
            return None
    except Exception as e:
        logger.error(f"Could not determine project root directory: {e}")
        return None


def _get_dbus_address() -> str:
    """Gets the DBUS_SESSION_BUS_ADDRESS from the environment."""
    dbus_addr = os.environ.get("DBUS_SESSION_BUS_ADDRESS", "")
    if not dbus_addr:
        logger.warning(
            "DBUS_SESSION_BUS_ADDRESS environment variable not found. Notifications from timer might fail."
        )
    else:
        logger.debug(f"Found DBUS_SESSION_BUS_ADDRESS: {dbus_addr}")
    return dbus_addr


def _get_template_dir() -> Path:
    """Finds the template directory, checking sys._MEIPASS or relative paths."""
    # Check PyInstaller temp dir first
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # Templates are bundled into a 'templates' subdir by --add-data
        meipass_path = Path(sys._MEIPASS) / "templates"
        if meipass_path.is_dir():
            logger.debug(f"Found templates in MEIPASS: {meipass_path}")
            return meipass_path
        else:
            logger.debug("Templates dir not found in MEIPASS at expected location.")

    # Fallback for development: relative to this file
    dev_path = Path(__file__).parent / "templates"
    if dev_path.is_dir():
        logger.debug(f"Found templates in development path: {dev_path}")
        return dev_path

    logger.error("Template directory not found!")
    raise FileNotFoundError("ChromaDesk systemd templates not found.")


def create_unit_files() -> bool:
    """Creates the .service and .timer files using AppImage path, config, or fallback."""
    logger.info("Creating/Updating systemd unit files...")

    exec_command = ""
    working_dir = ""
    dbus_address = _get_dbus_address()

    # --- Determine Execution Command and Working Directory ---

    # Priority 1: Check if running from an AppImage
    appimage_path = os.environ.get("APPIMAGE")
    if appimage_path and Path(appimage_path).is_file():
        logger.info(f"Detected running from AppImage: {appimage_path}")
        exec_command = f'"{appimage_path}" --headless'  # Quote path in case of spaces
        working_dir = str(
            Path.home()
        )  # Use home dir as working dir for AppImage service
        logger.info(
            f"Using AppImage path for ExecStart. WorkingDirectory={working_dir}"
        )

    # Priority 2: Check config file for manually installed path
    if not exec_command:  # Only check if AppImage wasn't detected
        try:
            installed_appimage_path = core_config.get_setting(
                "State", "installed_appimage_path"
            )
            if installed_appimage_path and Path(installed_appimage_path).is_file():
                logger.info(
                    f"Using installed AppImage path from config: {installed_appimage_path}"
                )
                exec_command = f'"{installed_appimage_path}" --headless'  # Quote path
                working_dir = str(
                    Path.home()
                )  # Use home dir for installed AppImage service
                logger.info(
                    f"Using installed path for ExecStart. WorkingDirectory={working_dir}"
                )
            else:
                if installed_appimage_path:
                    logger.warning(
                        f"Found path in config ('{installed_appimage_path}'), but it's not a valid file. Falling back."
                    )
                else:
                    logger.info(
                        "No valid installed AppImage path found in config. Checking fallback."
                    )
        except Exception as e:
            logger.error(
                f"Error reading installed_appimage_path from config: {e}. Checking fallback."
            )

    # Priority 3: Fallback to Python executable and script path (development mode)
    if not exec_command:
        logger.info(
            "Using development mode (python executable + script path) for ExecStart."
        )
        current_executable = _get_python_executable()
        script_path = _get_script_path()
        derived_project_root = _get_project_root()

        if not current_executable or not script_path or not derived_project_root:
            logger.critical(
                "Could not determine necessary paths (python/script/root) for fallback execution. Aborting unit file creation."
            )
            return False

        exec_command = (
            f'"{current_executable}" "{script_path}" --headless'  # Quote paths
        )
        working_dir = derived_project_root  # Use project root for dev mode
        logger.info(f"Using dev paths for ExecStart. WorkingDirectory={working_dir}")

    # Sanity check - should have command and dir by now
    if not exec_command or not working_dir:
        logger.critical(
            "Failed to determine ExecStart command or WorkingDirectory. Aborting unit file creation."
        )
        return False

    logger.info(f"Final determined ExecStart: {exec_command}")
    logger.info(f"Final determined WorkingDirectory: {working_dir}")
    # -----------------------------------------------------------

    # Ensure systemd user directory exists
    try:
        SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)
        TEMPLATE_DIR = _get_template_dir()  # Need for timer template
        logger.debug(f"Ensured systemd user directory exists: {SYSTEMD_USER_DIR}")
    except FileNotFoundError:
        logger.critical(
            "Cannot create unit files because template directory was not found."
        )
        return False
    except OSError as e:
        logger.error(f"Error creating systemd directory {SYSTEMD_USER_DIR}: {e}")
        return False

    all_success = True

    # --- Create .service file directly ---
    service_dest_path = SYSTEMD_USER_DIR / SERVICE_FILE
    logger.debug(f"Generating {service_dest_path} directly")
    service_content = f"""[Unit]
Description=ChromaDesk Daily Wallpaper Update
After=network.target graphical-session.target
Requires=graphical-session.target

[Service]
Type=oneshot
WorkingDirectory={working_dir}
Environment="DBUS_SESSION_BUS_ADDRESS={dbus_address}"
ExecStart={exec_command}

[Install]
WantedBy=default.target
"""
    try:
        service_dest_path.write_text(service_content)
        logger.info(f"Successfully wrote unit file: {service_dest_path}")
    except OSError as e:
        logger.error(f"Failed to write unit file {service_dest_path}: {e}")
        all_success = False
    except Exception as e:
        logger.error(
            f"Unexpected error writing service file {service_dest_path}: {e}",
            exc_info=True,
        )
        all_success = False

    # --- Create .timer file from template ---
    timer_filename = TIMER_FILE
    if all_success and "TEMPLATE_DIR" in locals() and TEMPLATE_DIR:
        timer_template_path = TEMPLATE_DIR / f"{timer_filename}.in"
        timer_dest_path = SYSTEMD_USER_DIR / timer_filename
        logger.debug(f"Processing template {timer_template_path} to {timer_dest_path}")
        try:
            if not timer_template_path.is_file():
                logger.error(f"Template file not found: {timer_template_path}")
                all_success = False
            else:
                timer_content = timer_template_path.read_text()
                timer_dest_path.write_text(timer_content)
                logger.info(f"Successfully wrote unit file: {timer_dest_path}")
        except OSError as e:
            logger.error(
                f"Failed to read template or write unit file {timer_dest_path}: {e}"
            )
            all_success = False
        except Exception as e:
            logger.error(
                f"Unexpected error processing template {timer_template_path}: {e}",
                exc_info=True,
            )
            all_success = False
    elif all_success:
        logger.error("TEMPLATE_DIR not determined correctly, cannot create timer file.")
        all_success = False

    # Reload systemd daemon if files were possibly changed
    if all_success:
        logger.info("Reloading systemd user daemon...")
        result = _run_systemctl(["daemon-reload"])
        if result is None:
            logger.error("Failed to reload systemd daemon after creating unit files.")
            return False
    else:
        logger.error("One or more unit files failed to be created.")

    return all_success


def enable_timer() -> bool:
    """Creates unit files and enables/starts the systemd timer."""
    logger.info(f"Enabling systemd timer: {TIMER_FILE}")
    # Ensure files are up-to-date first
    if not create_unit_files():
        logger.error("Failed to create necessary unit files. Cannot enable timer.")
        return False

    # Enable and start the timer immediately
    result = _run_systemctl(["enable", "--now", TIMER_FILE], check=True)
    if result is not None:
        logger.info(f"Systemd timer {TIMER_FILE} enabled and started successfully.")
        return True
    else:
        logger.error(f"Failed to enable/start systemd timer {TIMER_FILE}.")
        return False


def disable_timer() -> bool:
    """Disables and stops the systemd timer."""
    logger.info(f"Disabling systemd timer: {TIMER_FILE}")
    # Stop and disable the timer
    result = _run_systemctl(
        ["disable", "--now", TIMER_FILE]
    )  # Don't use check=True, disable fails if not enabled
    if result is not None:  # Command ran successfully (even if it did nothing)
        logger.info(f"Systemd timer {TIMER_FILE} disabled and stopped.")
        # Optionally remove the files? Or leave them for easy re-enabling? Leave for now.
        # try:
        #     (SYSTEMD_USER_DIR / TIMER_FILE).unlink(missing_ok=True)
        #     (SYSTEMD_USER_DIR / SERVICE_FILE).unlink(missing_ok=True)
        #     _run_systemctl(['daemon-reload']) # Reload after removing
        # except OSError as e:
        #      logger.warning(f"Could not remove unit files: {e}")
        return True
    else:
        # Only log error if systemctl command itself failed (e.g., couldn't connect)
        if result is None:  # Check if _run_systemctl indicated command failure
            logger.error(
                f"Failed to execute disable command for systemd timer {TIMER_FILE}."
            )
        return False


def remove_service_files() -> bool:
    """Removes the .service and .timer files and reloads the systemd daemon."""
    logger.info(f"Removing systemd unit files: {SERVICE_FILE}, {TIMER_FILE}")
    service_path = SYSTEMD_USER_DIR / SERVICE_FILE
    timer_path = SYSTEMD_USER_DIR / TIMER_FILE
    files_found = False
    all_removed = True

    # Remove service file
    if service_path.is_file():
        files_found = True
        try:
            service_path.unlink()
            logger.info(f"Removed {service_path}")
        except OSError as e:
            logger.error(f"Failed to remove {service_path}: {e}")
            all_removed = False
    else:
        logger.debug(f"Service file {service_path} not found, skipping removal.")

    # Remove timer file
    if timer_path.is_file():
        files_found = True
        try:
            timer_path.unlink()
            logger.info(f"Removed {timer_path}")
        except OSError as e:
            logger.error(f"Failed to remove {timer_path}: {e}")
            all_removed = False
    else:
        logger.debug(f"Timer file {timer_path} not found, skipping removal.")

    # Reload daemon if we removed any files
    if files_found and all_removed:
        logger.info("Reloading systemd user daemon after removing unit files...")
        result = _run_systemctl(["daemon-reload"])
        if result is None:
            logger.warning(
                "Failed to reload systemd daemon after removing files. Manual reload might be needed."
            )
            # Still return True as file removal succeeded, but log the warning
    elif files_found and not all_removed:
        logger.error("Failed to remove one or more systemd unit files.")
    elif not files_found:
        logger.info("No systemd unit files found to remove.")
        # If no files were found, we consider it a success in terms of removal
        all_removed = True

    return all_removed


def is_timer_active() -> bool:
    """Checks if the timer unit is currently active."""
    logger.debug(f"Checking active state of timer: {TIMER_FILE}")
    result = _run_systemctl(["is-active", TIMER_FILE])
    # is-active returns 0 and prints "active" if active, non-zero otherwise
    # We check return code directly
    active = result is not None and result.returncode == 0
    logger.debug(f"Timer active state: {active}")
    return active


def is_timer_enabled() -> bool:
    """Checks if the timer unit is enabled to start on login."""
    logger.debug(f"Checking enabled state of timer: {TIMER_FILE}")
    result = _run_systemctl(["is-enabled", TIMER_FILE])
    # is-enabled returns 0 and prints "enabled" if enabled, 1 otherwise
    enabled = result is not None and result.returncode == 0
    logger.debug(f"Timer enabled state: {enabled}")
    return enabled


# Example Usage (can be tested manually, CAUTION: modifies systemd state)
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - MANAGER_TEST - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )
    print("--- Testing Systemd Service Manager ---")
    print(f"Systemd User Dir: {SYSTEMD_USER_DIR}")
    print(f"Service File: {SERVICE_FILE}")
    print(f"Timer File: {TIMER_FILE}")

    print("\n1. Creating unit files...")
    created = create_unit_files()
    print(f"   Success: {created}")
    if created:
        print(f"   Check files in: {SYSTEMD_USER_DIR}")

    print("\n2. Checking if timer is enabled (before enabling)...")
    enabled_before = is_timer_enabled()
    print(f"   Is Enabled: {enabled_before}")

    print("\n3. Checking if timer is active (before enabling)...")
    active_before = is_timer_active()
    print(f"   Is Active: {active_before}")

    if created:  # Only try enabling if files were created
        print("\n4. Enabling timer...")
        enabled_cmd = enable_timer()
        print(f"   Enable Command Success: {enabled_cmd}")

        print("\n5. Checking if timer is enabled (after enabling)...")
        enabled_after = is_timer_enabled()
        print(f"   Is Enabled: {enabled_after}")

        print("\n6. Checking if timer is active (after enabling)...")
        active_after = is_timer_active()
        print(f"   Is Active: {active_after}")

        input("\n---> Press Enter to disable the timer...")  # Pause for inspection

        print("\n7. Disabling timer...")
        disabled_cmd = disable_timer()
        print(f"   Disable Command Success: {disabled_cmd}")

        print("\n8. Checking if timer is enabled (after disabling)...")
        enabled_final = is_timer_enabled()
        print(f"   Is Enabled: {enabled_final}")

        print("\n9. Checking if timer is active (after disabling)...")
        active_final = is_timer_active()
        print(f"   Is Active: {active_final}")
    else:
        print("\nSkipping enable/disable tests as unit file creation failed.")

    print("\n--- Test Complete ---")
