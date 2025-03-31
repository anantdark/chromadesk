# chromadesk/chromadesk/ui/main_window.py
from urllib.parse import urlparse
import logging  # Import logging
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, QUrl, Slot
from PySide6.QtGui import QDesktopServices, QIcon, QPalette, QPixmap
from PySide6.QtWidgets import QCheckBox  # Added QMessageBox
from PySide6.QtWidgets import QGroupBox  # Added QGroupBox
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStatusBar,
    QStyle,
    QVBoxLayout,
    QWidget,
)

# Add chromadesk import for version
import chromadesk

# Use .. to go up one level from ui/ to chromadesk/ then into core/
from ..core import bing as core_bing
from ..core import config as core_config
from ..core import downloader as core_downloader
from ..core import history as core_history
from ..core import wallpaper as core_wallpaper
from ..services import manager as services_manager

# Get a logger instance for this module
logger = logging.getLogger(__name__)

THUMBNAIL_SIZE = QSize(45, 80)

# Dummy data for regions (Consider moving to config or a constants file later)
BING_REGIONS = {
    "India (English)": "en-IN",
    "USA (English)": "en-US",
    "Germany (German)": "de-DE",
    "UK (English)": "en-GB",
    "Australia (English)": "en-AU",
    "Japan (Japanese)": "ja-JP",
    "China (Chinese)": "zh-CN",
    "France (French)": "fr-FR",
}


class MainWindow(QMainWindow):
    # --- Initialization ---
    def __init__(self):
        """Initializes the main application window."""
        super().__init__()
        logger.info("Initializing MainWindow...")

        self.setWindowTitle("ChromaDesk")
        self.setGeometry(100, 100, 800, 600)
        self.current_preview_path = None  # Keep track of what's in preview
        self.current_unscaled_pixmap = None

        # --- Build UI ---
        self._setup_ui()

        # --- Initial State ---
        logger.debug("Setting initial UI state...")
        self._load_initial_settings()
        self._update_ui_for_source()
        logger.debug("Populating initial history...")
        self.populate_history()
        logger.debug("Loading initial preview...")
        self.load_initial_preview()  # Load preview for default source

        # --- Connect Signals ---
        logger.debug("Connecting signals...")
        self._connect_signals()

        logger.info("MainWindow initialization complete.")

    # --- UI Setup Helper ---
    def _setup_ui(self):
        """Creates and arranges the widgets in the window."""
        logger.debug("Setting up UI widgets...")
        # Central Widget and Main Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)  # Controls | Preview

        # Left Panel (Controls)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_panel.setFixedWidth(300)

        # Source Selection
        self.source_label = QLabel("Wallpaper Source:")
        self.source_combo = QComboBox()
        self.source_combo.addItems(["Today's Bing", "History", "Custom URL"])

        # Region Selection (for Bing)
        self.region_label = QLabel("Bing Region:")
        self.region_combo = QComboBox()
        for name, code in BING_REGIONS.items():
            self.region_combo.addItem(name, code)

        # Custom URL Input
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter Image URL (JPG/PNG)")

        # History List
        self.history_label = QLabel("History")
        self.history_list = QListWidget()
        self.history_list.setIconSize(THUMBNAIL_SIZE)

        # Apply Button
        self.apply_button = QPushButton("Apply Wallpaper")

        # Info Button
        self.info_button = QPushButton()
        info_icon = self.style().standardIcon(
            QStyle.StandardPixmap.SP_MessageBoxInformation
        )
        self.info_button.setIcon(info_icon)
        self.info_button.setToolTip("Created by AnAnT")

        # Button Layout (Apply and Info side-by-side)
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.apply_button)
        button_layout.addWidget(self.info_button)

        self.daily_update_checkbox = QCheckBox("Enable Daily Automatic Updates")

        # --- Status & Config Group ---
        self.status_group_box = QGroupBox("Status & Configuration")
        status_layout = QVBoxLayout()

        self.version_label = QLabel("Version: N/A")
        self.config_region_label = QLabel("Region: N/A")
        self.config_history_label = QLabel("History Limit: N/A")
        self.config_dir_label = QLabel("Directory: N/A")
        self.timer_status_label = QLabel("Daily Timer: N/A")
        # self.last_change_label = QLabel("Last Change: N/A") # Placeholder - requires new logic

        self.uninstall_button = QPushButton("Uninstall ChromaDesk")
        self.uninstall_button.setStyleSheet(
            "color: red; font-weight: bold;"
        )  # Red, bold text

        status_layout.addWidget(self.version_label)
        status_layout.addWidget(self.config_region_label)
        status_layout.addWidget(self.config_history_label)
        status_layout.addWidget(self.config_dir_label)
        status_layout.addWidget(self.timer_status_label)
        # status_layout.addWidget(self.last_change_label)
        status_layout.addSpacing(10)  # Add some space
        status_layout.addWidget(self.uninstall_button)
        status_layout.addStretch()  # Push content to the top of the group box

        self.status_group_box.setLayout(status_layout)
        # ---------------------------

        # Add widgets to left layout
        left_layout.addWidget(self.source_label)
        left_layout.addWidget(self.source_combo)
        left_layout.addWidget(self.region_label)
        left_layout.addWidget(self.region_combo)
        left_layout.addWidget(self.url_input)
        left_layout.addWidget(self.history_label)
        left_layout.addWidget(self.history_list)
        left_layout.addWidget(self.daily_update_checkbox)
        left_layout.addSpacing(15)  # Add padding before the status box
        left_layout.addWidget(self.status_group_box)  # Add the new group box
        left_layout.addStretch()
        left_layout.addLayout(button_layout)  # Add the horizontal button layout

        # --- Adjust Info Button Size ---
        apply_button_height = self.apply_button.sizeHint().height()
        self.info_button.setFixedSize(apply_button_height, apply_button_height)
        # -------------------------------

        # Right Panel (Preview)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        self.preview_label = QLabel("Wallpaper Preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.preview_label.setAutoFillBackground(True)
        palette = self.preview_label.palette()
        palette.setColor(QPalette.ColorRole.Window, Qt.GlobalColor.darkGray)
        self.preview_label.setPalette(palette)
        self.preview_label.setMinimumSize(300, 400)

        right_layout.addWidget(self.preview_label)

        # Add panels to main layout
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel)
        self.setStatusBar(QStatusBar(self))
        self.setStatusBar(self.statusBar())
        self.status_bar = QStatusBar(self)  # Keep a reference if needed
        self.setStatusBar(self.status_bar)

        # Create a label for messages
        self.status_label = QLabel("Ready")  # Initial text
        self.status_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )  # Center align text

        # Optional: Add padding via stylesheet (adjust values as needed)
        self.status_label.setStyleSheet(
            "QLabel { padding-left: 10px; padding-right: 10px; padding-bottom: 3px; padding-top: 3px; }"
        )
        # Alternatively, apply to status bar: self.status_bar.setStyleSheet("QStatusBar { padding: 3px; }")

        # Add the label permanently to the status bar, allowing it to stretch
        self.status_bar.addWidget(
            self.status_label, stretch=1
        )  # stretch=1 makes it take available space

        # Clear the initial "Ready" message after a few seconds
        QTimer.singleShot(3000, lambda: self.status_label.setText(""))

        logger.debug("Status bar with centered label added.")
        # -----------------------------------

        logger.debug("UI widget setup complete.")

    # --- Signal Connection Helper ---
    def _connect_signals(self):
        """Connects widget signals to appropriate slots."""
        self.source_combo.currentIndexChanged.connect(self._update_ui_for_source)
        self.history_list.currentItemChanged.connect(self.on_history_selected)
        self.region_combo.currentIndexChanged.connect(
            self.on_region_changed
        )  # Connect region change
        self.apply_button.clicked.connect(self.on_apply_clicked)  # Connect apply button
        self.daily_update_checkbox.stateChanged.connect(self.on_daily_update_toggled)
        self.info_button.clicked.connect(self.open_author_github)  # Connect info button
        self.uninstall_button.clicked.connect(
            self.on_uninstall_clicked
        )  # Connect uninstall button
        # Connect signals that should trigger a status update
        self.region_combo.currentIndexChanged.connect(self._update_status_info)
        self.daily_update_checkbox.stateChanged.connect(self._update_status_info)
        # TODO: Connect URL input returnPressed/editingFinished if needed

    def _load_initial_settings(self):
        """Loads saved settings from config and updates UI controls."""
        logger.debug("Loading initial settings from config...")
        try:
            # Region
            saved_region_code = core_config.get_setting(
                "Settings", "region", fallback="en-US"
            )
            index = self.region_combo.findData(saved_region_code)
            if index != -1:
                self.region_combo.setCurrentIndex(index)
            else:
                logger.warning(
                    f"Saved region code '{saved_region_code}' not found. Using default."
                )
                self.region_combo.setCurrentIndex(0)

            # --- Load Daily Update State ---
            config_enabled = (
                core_config.get_setting("Settings", "enabled", fallback="false").lower()
                == "true"
            )
            # Check systemd status for more reliability (optional but good)
            systemd_enabled = services_manager.is_timer_enabled()
            if config_enabled != systemd_enabled:
                logger.warning(
                    f"Config 'enabled' state ({config_enabled}) differs from systemd timer state ({systemd_enabled}). Trusting systemd state."
                )
                # Update config to match reality
                core_config.set_setting(
                    "Settings", "enabled", str(systemd_enabled).lower()
                )
                current_state = systemd_enabled
            else:
                current_state = config_enabled

            # Set checkbox state without triggering the signal handler initially
            self.daily_update_checkbox.blockSignals(True)
            self.daily_update_checkbox.setChecked(current_state)
            self.daily_update_checkbox.blockSignals(False)
            logger.info(
                f"Initial daily update state loaded: {'Enabled' if current_state else 'Disabled'}"
            )
            # --- End Daily Update State ---

            # --- Update Status Info --- # Call *after* loading other settings
            self._update_status_info()  # Initial population of status labels

        except Exception as e:
            logger.error("Error loading initial settings", exc_info=True)
            QMessageBox.warning(
                self,
                "Load Settings Error",
                "Could not load saved settings. Using defaults.",
            )

    def load_initial_preview(self):
        """Loads the preview based on the default source selection."""
        selected_source = self.source_combo.currentText()
        logger.info(f"Loading initial preview for source: {selected_source}")
        if selected_source == "Today's Bing":
            self.fetch_and_display_bing()  # Fetch current Bing image
        elif selected_source == "History":
            # Select the first item in history list (if any) which triggers on_history_selected
            if (
                self.history_list.count() > 0
                and self.history_list.item(0).flags() & Qt.ItemFlag.ItemIsSelectable
            ):
                self.history_list.setCurrentRow(0)
            else:
                self.update_preview(None)  # No history, clear preview
        else:  # Custom URL or others
            self.update_preview(None)  # Clear preview initially

    # --- Core Functionality Methods ---

    def populate_history(self):
        """Loads combined wallpaper history items with thumbnails into the list widget."""
        logger.info("Populating combined history list...")
        self.history_list.clear()
        try:
            keep_count = int(
                core_config.get_setting("Settings", "keep_history", fallback="7")
            )
            history_files = core_history.get_sorted_wallpaper_history(
                max_items=keep_count
            )
            logger.info(f"Core history function returned {len(history_files)} file(s)")

            if not history_files:
                logger.info("No history files found, adding placeholder.")
                item = QListWidgetItem("No history found")  # No icon for placeholder
                item.setData(Qt.ItemDataRole.UserRole, None)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                self.history_list.addItem(item)
                return

            for file_path in history_files:
                # --- Create Icon ---
                icon = QIcon()  # Default empty icon
                try:
                    pixmap = QPixmap(str(file_path))
                    if not pixmap.isNull():
                        scaled_pixmap = pixmap.scaled(
                            THUMBNAIL_SIZE,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                        icon = QIcon(scaled_pixmap)
                    else:
                        logger.warning(
                            f"Failed to load pixmap for thumbnail: {file_path.name}"
                        )
                except Exception as thumb_err:
                    logger.warning(
                        f"Error creating thumbnail for {file_path.name}: {thumb_err}"
                    )
                # --------------------

                # --- Create List Item with Icon and Text ---
                item = QListWidgetItem(icon, file_path.name)  # Pass icon to constructor
                # -------------------------------------------
                item.setData(Qt.ItemDataRole.UserRole, file_path)
                self.history_list.addItem(item)
                logger.debug(f"Added history item: {file_path.name}")

        except Exception as e:
            logger.error("Error populating history list widget", exc_info=True)
            item = QListWidgetItem("Error loading history")
            item.setData(Qt.ItemDataRole.UserRole, None)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.history_list.addItem(item)

    def update_preview(self, image_path: Path | None):
        """
        Loads an image, stores its original pixmap, and triggers scaling/display.
        Also resets the preview if the path is invalid or None.
        """
        logger.debug(f"Updating preview for path: {image_path}")
        # Reset stored pixmap and path first
        self.current_unscaled_pixmap = None
        self.current_preview_path = None

        if isinstance(image_path, Path) and image_path.is_file():
            try:
                # Load the full pixmap from the file path
                pixmap = QPixmap(str(image_path))

                if pixmap.isNull():
                    # Pixmap failed to load (invalid image file, permissions, etc.)
                    logger.error(f"QPixmap failed to load image: {image_path}")
                    self.preview_label.setPixmap(QPixmap())  # Clear visual preview
                    self.preview_label.setText(
                        f"Preview Error:\nInvalid or unreadable image\n({image_path.name})"
                    )
                    # Keep self.current_unscaled_pixmap as None
                else:
                    # Successfully loaded, store the original unscaled pixmap
                    self.current_unscaled_pixmap = pixmap
                    self.current_preview_path = image_path  # Store path for reference
                    logger.debug(f"Stored original pixmap for {image_path.name}")
                    # Trigger the scaling and display logic
                    self._scale_and_display_preview()

            except Exception as e:
                # Catch any unexpected errors during pixmap loading
                logger.error(
                    f"Unexpected error loading pixmap for {image_path}", exc_info=True
                )
                self.preview_label.setPixmap(QPixmap())
                self.preview_label.setText(
                    f"Preview Error:\nUnexpected issue loading\n({image_path.name})"
                )
                self.current_unscaled_pixmap = None  # Ensure stored pixmap is cleared
        else:
            # Path was None, not a Path object, or file doesn't exist
            logger.debug("No valid image path provided, clearing preview.")
            self.preview_label.setPixmap(QPixmap())
            # Keep self.current_unscaled_pixmap as None
            if image_path is None:
                self.preview_label.setText("No Preview Available")
            else:  # Path was invalid or file not found
                self.preview_label.setText(
                    f"Preview Error:\nFile not found\n({image_path})"
                )

    def fetch_and_display_bing(self, region_code=None):
        """Fetches today's Bing info for the selected region and updates the preview."""
        if region_code is None:
            region_code = self.region_combo.currentData()  # Get code from combo data
        if not region_code:
            region_code = "en-US"  # Fallback
            logger.warning(
                "Could not get region code from combo, falling back to en-US"
            )

        logger.info(f"Fetching Bing wallpaper for region: {region_code}")
        self.update_status_message(f"Fetching Bing info for {region_code}...", 2000)
        self.preview_label.setText(f"Fetching for {region_code}...")  # Indicate loading
        QApplication.processEvents()  # Allow UI to update

        bing_info = core_bing.fetch_bing_wallpaper_info(region=region_code)
        self.update_status_message("")  # Clear fetching message

        if not bing_info or not bing_info.get("full_url"):
            logger.error("Failed to fetch Bing wallpaper info.")
            self.update_preview(None)
            self.preview_label.setText("Error:\nCould not fetch Bing image info.")
            QMessageBox.warning(
                self,
                "Fetch Error",
                f"Could not fetch Bing wallpaper information for region {region_code}.",
            )
            self.update_status_message("Failed to fetch Bing info.", 5000)
            return

        # Check if we already have this image downloaded (using date and filename structure)
        wallpaper_dir = core_history.get_wallpaper_dir()
        potential_filename = core_history.get_bing_filename(
            bing_info["date"], bing_info["full_url"]
        )
        local_path = wallpaper_dir / potential_filename

        if local_path.is_file():
            logger.info(f"Today's Bing image already downloaded: {local_path.name}")
            self.update_status_message("Found existing Bing image.", 3000)
            self.update_preview(local_path)
        else:
            logger.info(
                f"Today's Bing image not found locally. Downloading from {bing_info['full_url']}..."
            )
            self.preview_label.setText("Downloading...")
            self.update_status_message("Downloading Bing image...", 0)
            QApplication.processEvents()

            # Download to a temporary location first? Or directly to history? Direct for now.
            # Ensure history directory exists
            if not core_history.ensure_wallpaper_dir():
                logger.critical("Wallpaper directory cannot be created!")
                QMessageBox.critical(
                    self,
                    "Directory Error",
                    "Could not create the wallpaper storage directory.",
                )
                self.update_preview(None)
                self.preview_label.setText("Error:\nWallpaper directory missing.")
                return

            success = core_downloader.download_image(bing_info["full_url"], local_path)
            if success:
                logger.info(f"Downloaded successfully to {local_path}")
                self.update_preview(local_path)
                # Since we downloaded a new Bing image, refresh history list and maybe cleanup
                if success:
                    self.update_status_message("Bing image downloaded.", 3000)
                    self.populate_history()  # Refresh history list
                    keep_count = int(
                        core_config.get_setting(
                            "Settings", "keep_history", fallback="7"
                        )
                    )
                    core_history.cleanup_wallpaper_history(keep=keep_count)
            else:
                logger.error(f"Failed to download image from {bing_info['full_url']}")
                self.update_status_message("Bing image download failed.", 5000)
                self.update_preview(None)
                self.preview_label.setText("Error:\nDownload failed.")
                QMessageBox.warning(
                    self,
                    "Download Error",
                    f"Could not download the Bing image from:\n{bing_info['full_url']}",
                )

    # Add this new method to the MainWindow class:
    def resizeEvent(self, event):
        """Handles window resize events to rescale the preview image."""
        # Call the base class implementation first
        super().resizeEvent(event)
        # Now, rescale and display the stored preview image
        logger.debug("Window resized, rescaling preview...")
        self._scale_and_display_preview()

    # Add this new method to the MainWindow class
    def update_status_message(self, message: str, timeout: int = 5000, color="green"):
        """
        Updates the status bar label with a message and clears it after a timeout.
        A timeout of 0 means the message is persistent until cleared manually or overwritten.
        """
        logger.debug(f"Updating status message: '{message}' (timeout: {timeout})")
        self.status_label.setText(f'<font color="{color}">{message}</font>')

        # Clear the message after the timeout, unless timeout is 0
        if timeout > 0:
            QTimer.singleShot(timeout, lambda: self._clear_status_if_matches(message))

    def _clear_status_if_matches(self, message_to_clear: str, force_clear=False):
        """Helper slot to clear the status bar only if the message hasn't changed."""
        if self.status_label.text() == message_to_clear or force_clear:
            self.status_label.setText("")
            logger.debug(f"Cleared status message: '{message_to_clear}'")

    # Add this new method to the MainWindow class:
    def _scale_and_display_preview(self):
        """Scales the stored original pixmap to fit the preview label and displays it."""
        if self.current_unscaled_pixmap and not self.current_unscaled_pixmap.isNull():
            target_size = self.preview_label.size()
            if target_size.width() <= 1 or target_size.height() <= 1:
                target_size = self.preview_label.minimumSize()

            scaled_pixmap = self.current_unscaled_pixmap.scaled(
                target_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.preview_label.setPixmap(scaled_pixmap)
            self.preview_label.setText("")  # Clear any error text
            # logger.debug("Preview scaled and displayed.") # Optional debug log
        else:
            # No valid original pixmap to scale, ensure preview is clear/shows text
            self.preview_label.setPixmap(QPixmap())
            if self.current_preview_path:  # If there was supposed to be an image
                self.preview_label.setText(
                    f"Preview Error:\nCould not display\n({self.current_preview_path.name})"
                )
            else:  # No image selected
                self.preview_label.setText("No Preview Available")

    # --- UI Slots (Event Handlers) ---

    @Slot()  # Indicates this method is a slot
    def _update_ui_for_source(self):
        """Updates visibility of controls based on selected source."""
        selected_source = self.source_combo.currentText()
        logger.debug(f"Source changed to: {selected_source}. Updating UI visibility.")

        is_bing = selected_source == "Today's Bing"
        is_history = selected_source == "History"
        is_custom = selected_source == "Custom URL"

        self.region_label.setVisible(is_bing)
        self.region_combo.setVisible(is_bing)

        self.url_input.setVisible(is_custom)
        # Clear URL input when switching away from it
        if not is_custom:
            self.url_input.clear()

        self.history_label.setVisible(is_history)
        self.history_list.setVisible(is_history)

        # Update preview when source changes
        if is_bing:
            self.fetch_and_display_bing()
        elif is_history:
            # Select first item if available
            if (
                self.history_list.count() > 0
                and self.history_list.item(0).flags() & Qt.ItemFlag.ItemIsSelectable
            ):
                self.history_list.setCurrentRow(0)
                # on_history_selected will handle the preview update
            else:
                self.update_preview(None)  # No history, clear preview
        else:  # Custom URL
            self.update_preview(None)  # Clear preview for custom URL input

        # TODO: More sophisticated enable/disable logic for apply button
        self.apply_button.setEnabled(True)

    @Slot(QListWidgetItem, QListWidgetItem)
    def on_history_selected(self, current_item, previous_item):
        """Updates the preview when a history item is selected."""
        if current_item:
            logger.debug(f"History item selected: {current_item.text()}")
            image_path = current_item.data(Qt.ItemDataRole.UserRole)
            if isinstance(image_path, Path):
                self.update_preview(image_path)
            else:
                logger.warning("Selected history item has no valid path data.")
                self.update_preview(None)  # Handle "No history" item
        else:
            # This might happen if the list is cleared while an item was selected
            logger.debug("History selection cleared.")
            self.update_preview(None)

    @Slot(int)  # int corresponds to the index passed by currentIndexChanged
    def on_region_changed(self, index):
        """Handles Bing region dropdown changes."""
        region_code = self.region_combo.itemData(index)
        region_name = self.region_combo.itemText(index)
        logger.info(f"Region changed to: {region_name} ({region_code})")
        # Save the setting
        try:
            core_config.set_setting("Settings", "region", region_code)
        except Exception as e:
            logger.error(f"Failed to save region setting {region_code}", exc_info=True)
            # Optionally notify user

        # If current source is "Today's Bing", fetch new image for the selected region
        if self.source_combo.currentText() == "Today's Bing":
            self.fetch_and_display_bing(region_code=region_code)

    @Slot()
    def on_apply_clicked(self):
        """Handles the 'Apply Wallpaper' button click."""
        logger.info("Apply Wallpaper button clicked.")

        image_to_set = None
        selected_source = self.source_combo.currentText()

        if selected_source == "Today's Bing" or selected_source == "History":
            # Use the image currently shown in the preview (if valid)
            if self.current_preview_path and self.current_preview_path.is_file():
                image_to_set = self.current_preview_path
                if not image_to_set:
                    QMessageBox.warning(
                        self,
                        "Apply Error",
                        "No valid wallpaper image is currently selected or displayed.",
                    )
                    self.update_status_message(
                        "Apply failed: No image selected", 5000
                    )  # Show status too
                    return

        elif selected_source == "Custom URL":
            url = self.url_input.text().strip()
            if not url:
                logger.warning("Apply clicked for Custom URL, but URL input is empty.")
                QMessageBox.warning(self, "Input Error", "Please enter an image URL.")
                self.update_status_message("Apply failed: URL empty", 5000)
                return

            logger.info(f"Applying wallpaper from Custom URL: {url}")
            # 1. Download the image to a temporary path or directly to history?
            #    Let's save directly to history for now, similar to Bing fetch.
            if not core_history.ensure_wallpaper_dir():
                QMessageBox.critical(
                    self,
                    "Directory Error",
                    "Could not access or create the wallpaper storage directory.",
                )
                return

            wallpaper_dir = core_history.get_wallpaper_dir()
            # Determine extension based on URL or download headers later - basic for now
            extension = (
                Path(urlparse(url).path).suffix or ".jpg"
            )  # Basic extension guess
            filename = core_history.get_custom_filename(extension=extension)
            save_path = wallpaper_dir / filename

            self.apply_button.setEnabled(False)  # Disable button during download/set
            self.apply_button.setText("Downloading...")
            self.statusBar().showMessage(
                "Downloading from {url}...", 0
            )  # 0 = Persistent until changed
            QApplication.processEvents()

            success = core_downloader.download_image(url, save_path)

            self.apply_button.setText("Apply Wallpaper")  # Restore button text
            self.apply_button.setEnabled(True)
            self.update_status_message("")  # Clear persistent message

            if success:
                logger.info(f"Custom URL image downloaded to: {save_path}")
                self.statusBar().showMessage("Download complete.", 3000)
                image_to_set = save_path
                self.populate_history()
                # Add to history? Technically it's not a 'Bing' history item.
                # Maybe update preview, but don't add to the Bing list.
                self.update_preview(save_path)
            else:
                logger.error(f"Failed to download image from Custom URL: {url}")
                QMessageBox.critical(
                    self,
                    "Download Failed",
                    f"Could not download or validate the image from the specified URL:\n{url}",
                )
                self.update_status_message("Download failed.", 5000)
                return
        else:
            logger.error(f"Apply clicked with unexpected source: {selected_source}")
            return

        # --- Perform the actual wallpaper setting ---
        if image_to_set and image_to_set.is_file():
            logger.info(f"Calling core wallpaper setter for: {image_to_set}")
            self.apply_button.setEnabled(False)
            self.apply_button.setText("Setting...")
            self.update_status_message(
                "Setting wallpaper to {image_to_set.name}...", 0
            )  # Persistent
            QApplication.processEvents()

            set_success = core_wallpaper.set_gnome_wallpaper(image_to_set)

            self.apply_button.setText("Apply Wallpaper")
            self.apply_button.setEnabled(True)
            self.update_status_message("")

            if set_success:
                logger.info("Wallpaper set successfully via core function.")
                # QMessageBox.information(
                #     self,
                #     "Success",
                #     f"Wallpaper successfully set to:\n{image_to_set.name}",
                # )
                # Show a success toast/brief message
                self.update_status_message(
                    "Wallpaper applied successfully!", 5000
                )  # Show for 5 sec
            else:
                logger.error("Core wallpaper setting function returned False.")
                QMessageBox.critical(
                    self,
                    "Setting Failed",
                    "Could not set the desktop wallpaper.\nCheck logs for details.",
                )
                self.update_status_message("Failed to set wallpaper.", 5000)
        else:
            # This case shouldn't be reached if logic above is correct, but handle defensively
            logger.error("Apply clicked, but 'image_to_set' was not a valid file path.")
            QMessageBox.warning(
                self,
                "Apply Error",
                "An internal error occurred: No valid image file was selected for setting.",
            )

    @Slot(int)  # Receives the Qt.CheckState enum value (0=Unchecked, 2=Checked)
    def on_daily_update_toggled(self, state):
        """Handles enabling/disabling the daily update timer."""
        enable = state == Qt.CheckState.Checked.value  # Convert state enum to boolean
        logger.info(
            f"Daily update checkbox toggled. Attempting to set state to: {'Enable' if enable else 'Disable'}"
        )

        success = False
        action = "enable" if enable else "disable"
        self.daily_update_checkbox.setEnabled(False)  # Disable during operation
        self.update_status_message(f"{action.capitalize()}ing daily updates...", 0)
        QApplication.processEvents()  # Update UI

        try:
            if enable:
                success = services_manager.enable_timer()
                self.update_status_message(
                    f"Daily updates {action}d.", 5000
                )  # Use status bar
            else:
                success = services_manager.disable_timer()
                self.update_status_message(f"Failed to {action} daily updates.", 5000)

            if success:
                logger.info(f"Systemd timer {action}d successfully.")
                # Update config file only if systemd command succeeded
                core_config.set_setting("Settings", "enabled", str(enable).lower())
                # Optional: Show status message
                # self.statusBar().showMessage(f"Daily updates {action}d.", 3000)
            else:
                logger.error(f"Failed to {action} systemd timer.")
                QMessageBox.critical(
                    self,
                    "Timer Error",
                    f"Failed to {action} the daily update timer.\nCheck logs for details.",
                )
                # Revert checkbox state visually on failure
                self.daily_update_checkbox.blockSignals(True)
                self.daily_update_checkbox.setChecked(
                    not enable
                )  # Set back to original state
                self.daily_update_checkbox.blockSignals(False)

        except Exception as e:
            # Catch unexpected errors in manager functions
            logger.error(f"Unexpected error trying to {action} timer", exc_info=True)
            QMessageBox.critical(
                self,
                "Internal Error",
                f"An unexpected error occurred while trying to {action} the timer.",
            )
            # Revert checkbox state visually on failure
            self.daily_update_checkbox.blockSignals(True)
            self.daily_update_checkbox.setChecked(not enable)
            self.daily_update_checkbox.blockSignals(False)
        finally:
            self.daily_update_checkbox.setEnabled(True)  # Re-enable checkbox

    @Slot()
    def open_author_github(self):
        """Opens the author's GitHub profile in the default web browser."""
        logger.info("Opening author GitHub page...")
        url = QUrl("https://github.com/anantdark")
        if not QDesktopServices.openUrl(url):
            logger.error(f"Could not open URL: {url.toString()}")
            self.update_status_message("Error: Could not open browser.")

    @Slot()
    def on_uninstall_clicked(self):
        """Handles the Uninstall button click: Confirms, removes service/config, closes app."""
        logger.warning("Uninstall button clicked.")

        reply = QMessageBox.question(
            self,
            "Confirm Uninstall",
            "Are you sure you want to uninstall ChromaDesk?\n\n"
            "This will:\n"
            "- Disable and remove the daily update service/timer.\n"
            "- Delete the configuration file.\n"
            "- The application will close.\n\n"
            "(Wallpaper images will NOT be deleted.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,  # Default button
        )

        if reply == QMessageBox.StandardButton.No:
            logger.info("Uninstall cancelled by user.")
            return

        logger.info("Proceeding with uninstallation...")
        self.uninstall_button.setEnabled(False)
        self.uninstall_button.setText("Uninstalling...")
        self.update_status_message("Uninstalling...", 0)
        QApplication.processEvents()

        errors = []

        # 1. Disable and remove systemd timer/service
        try:
            logger.info("Disabling timer...")
            if not services_manager.disable_timer():
                logger.warning("Failed to disable timer (might already be disabled).")
            logger.info("Removing service files...")
            if not services_manager.remove_service_files():
                errors.append(
                    "Could not remove the systemd service/timer files.\nManual removal might be needed."
                )
                logger.error("Failed to remove service files.")

        except Exception as e:
            logger.error("Error during service/timer removal", exc_info=True)
            errors.append("An error occurred removing systemd files.")

        # 2. Delete configuration file
        try:
            logger.info("Deleting config file...")
            if not core_config.delete_config_file():
                errors.append(
                    "Could not delete the configuration file.\nManual removal might be needed."
                )
                logger.error("Failed to delete config file.")

        except Exception as e:
            logger.error("Error during config file deletion", exc_info=True)
            errors.append("An error occurred deleting the configuration file.")

        # 3. Report results and close
        if errors:
            error_message = "Uninstallation completed with errors:\n\n- " + "\n- ".join(
                errors
            )
            logger.error(f"Uninstallation errors: {errors}")
            QMessageBox.warning(self, "Uninstallation Issues", error_message)
        else:
            logger.info("Uninstallation successful.")
            QMessageBox.information(
                self,
                "Uninstallation Complete",
                "ChromaDesk service and configuration removed successfully.",
            )

        logger.info("Closing application after uninstall.")
        self.close()  # Close the application window

    # --- New Method --- #
    def _update_status_info(self):
        """Fetches current status and config, updates status labels."""
        logger.debug("Updating status info labels...")

        # Version
        try:
            self.version_label.setText(f"Version: {chromadesk.__version__}")
        except Exception as e:
            logger.error("Failed to get version", exc_info=True)
            self.version_label.setText("Version: Error")

        # Config Region
        try:
            region_code = core_config.get_setting("Settings", "region", fallback="N/A")
            region_name = region_code
            for name, code in BING_REGIONS.items():
                if code == region_code:
                    region_name = name
                    break
            self.config_region_label.setText(f"Region: {region_name} ({region_code})")
        except Exception as e:
            logger.error("Failed to get region config", exc_info=True)
            self.config_region_label.setText("Region: Error")

        # Config History Limit
        try:
            history_limit = core_config.get_setting(
                "Settings", "keep_history", fallback="N/A"
            )
            self.config_history_label.setText(f"History Limit: {history_limit}")
        except Exception as e:
            logger.error("Failed to get history limit config", exc_info=True)
            self.config_history_label.setText("History Limit: Error")

        # Config Directory
        try:
            wallpaper_dir = core_history.get_wallpaper_dir()
            dir_text = str(wallpaper_dir) if wallpaper_dir else "Not Set"
            self.config_dir_label.setText(f"Directory: {dir_text}")
            self.config_dir_label.setToolTip(dir_text)  # Add tooltip for full path
        except Exception as e:
            logger.error("Failed to get wallpaper directory", exc_info=True)
            self.config_dir_label.setText("Directory: Error")

        # Timer Status
        try:
            timer_enabled = services_manager.is_timer_enabled()
            self.timer_status_label.setText(
                f"Daily Timer: {'Active' if timer_enabled else 'Inactive'}"
            )
        except Exception as e:
            logger.error("Failed to get timer status", exc_info=True)
            self.timer_status_label.setText("Daily Timer: Error")

        # Last Change (Placeholder)
        # try:
        #     # Future logic to get last change status
        #     self.last_change_label.setText("Last Change: N/A")
        # except Exception as e:
        #     logger.error("Failed to get last change status", exc_info=True)
        #     self.last_change_label.setText("Last Change: Error")
