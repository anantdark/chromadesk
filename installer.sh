#!/bin/bash
# Installer script for ChromaDesk

# set -e # Exit on first error (Temporarily disabled for debugging)

# --- Configuration ---
APP_NAME="ChromaDesk"
GITHUB_REPO="anantdark/chromadesk"
BIN_NAME="io.github.anantdark.chromadesk" # Executable name after installation
ICON_NAME="io.github.anantdark.chromadesk.png"
DESKTOP_FILE_NAME="io.github.anantdark.chromadesk.desktop"
ICON_SOURCE_PATH="data/icons/io.github.anantdark.chromadesk.png"

# Standard user install locations
INSTALL_DIR_BIN="$HOME/.local/bin"
INSTALL_DIR_DESKTOP="$HOME/.local/share/applications"
INSTALL_DIR_ICONS_BASE="$HOME/.local/share/icons"
INSTALL_DIR_ICONS="$INSTALL_DIR_ICONS_BASE/hicolor/128x128/apps" # Standard size

FINAL_BIN_PATH="$INSTALL_DIR_BIN/$BIN_NAME"
FINAL_DESKTOP_PATH="$INSTALL_DIR_DESKTOP/$DESKTOP_FILE_NAME"
FINAL_ICON_PATH="$INSTALL_DIR_ICONS/$ICON_NAME"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# --- Helper Functions ---
echo_green() {
    echo -e "${GREEN}$1${NC}"
}
echo_yellow() {
    echo -e "${YELLOW}$1${NC}"
}
echo_red() {
    echo -e "${RED}$1${NC}"
}

# --- Dependency Check ---
check_deps() {
    echo "Checking dependencies..."
    local missing_deps=0
    if ! command -v curl &> /dev/null; then
        echo_red "Error: 'curl' command not found. Please install curl."
        missing_deps=1
    fi
    # jq is preferred but optional (fallback exists)
    if ! command -v jq &> /dev/null; then
        echo_yellow "Warning: 'jq' command not found. Using less robust fallback for GitHub API parsing."
    fi
    # Add checks for other essential tools if needed (find, grep, sed, mkdir, mv, chmod, cp)

    if [[ $missing_deps -ne 0 ]]; then
        exit 1
    fi
}

# --- Download Logic ---
download_latest_appimage() {
    echo_yellow "Attempting to download latest release from GitHub ($GITHUB_REPO)..."
    local api_url="https://api.github.com/repos/$GITHUB_REPO/releases/latest"
    local release_json
    local download_url
    local filename

    # Fetch release data
    echo "Fetching latest release info from $api_url ..."
    release_json=$(curl -sL "$api_url")
    if [[ $? -ne 0 ]]; then
        echo_red "Error: Failed to fetch release data from GitHub API."
        return 1 # Indicate failure
    fi

    # Parse JSON to find AppImage URL and filename
    if command -v jq &> /dev/null; then
        download_url=$(echo "$release_json" | jq -r '.assets[] | select(.name | test("chromadesk-.*\\.AppImage$")) | .browser_download_url')
        filename=$(echo "$release_json" | jq -r '.assets[] | select(.name | test("chromadesk-.*\\.AppImage$")) | .name')
    else
        # Fallback using grep (less reliable, assumes URL structure)
        download_url=$(echo "$release_json" | grep -o 'https://github.com/[^" ]*/releases/download/[^" ]*chromadesk-[^" ]*\.AppImage' | head -n 1)
        if [[ -n "$download_url" ]]; then
            filename=$(basename "$download_url")
        fi
    fi

    if [[ -z "$download_url" || "$download_url" == "null" || -z "$filename" ]]; then
        echo_red "Error: Could not find AppImage download URL or filename in the latest GitHub release."
        echo "API Response Snippet: $(echo "$release_json" | head -n 10)"
        return 1 # Indicate failure
    fi

    echo "Found AppImage: $filename"
    echo "Download URL: $download_url"

    # Download the AppImage
    echo "Downloading $filename ..."
    curl -L -o "$filename" "$download_url"
    if [[ $? -ne 0 ]]; then
        echo_red "Error: Download failed."
        rm -f "$filename" # Clean up partial download
        return 1 # Indicate failure
    fi

    chmod +x "$filename"
    echo_green "Download complete: $filename"
    echo "$filename" # Return the filename on success
    return 0
}

# --- Installation Logic ---
install_app() {
    echo_green "Starting ChromaDesk Installation..."

    # 1. Find or Build AppImage
    APPIMAGE_FILE=$(find . -maxdepth 1 -name 'chromadesk-*.AppImage' -print -quit)

    if [[ -z "$APPIMAGE_FILE" ]]; then
        echo_yellow "No existing ChromaDesk AppImage found. Building..."
        if [[ ! -f "build.sh" ]]; then
            echo_red "Error: build.sh not found in the current directory. Cannot build."
            exit 1
        fi
        echo "Running ./build.sh --appimage ..."
        if ./build.sh --appimage; then
            APPIMAGE_FILE=$(find . -maxdepth 1 -name 'chromadesk-*.AppImage' -print -quit)
            if [[ -z "$APPIMAGE_FILE" ]]; then
                echo_red "Error: Build script ran but could not find the built AppImage."
                exit 1 # Exit if build claims success but file not found
            fi
            echo_green "Build successful."
        else
            echo_yellow "Local build failed. Attempting to download latest release from GitHub..."
            local downloaded_filename
            downloaded_filename=$(download_latest_appimage)
            if [[ $? -eq 0 && -n "$downloaded_filename" ]]; then
                echo_green "Successfully downloaded latest release: $downloaded_filename"
                APPIMAGE_FILE="$downloaded_filename" # Use the downloaded file
            else
                echo_red "Error: Local build failed and download from GitHub also failed."
                exit 1
            fi
        fi
    else
        echo_green "Found existing AppImage: $APPIMAGE_FILE"
    fi

    # 2. Create Directories
    echo "Ensuring installation directories exist..."
    mkdir -p "$INSTALL_DIR_BIN"
    mkdir -p "$INSTALL_DIR_DESKTOP"
    mkdir -p "$INSTALL_DIR_ICONS"

    # 3. Move and Rename AppImage
    echo "Installing executable to $FINAL_BIN_PATH ..."
    mv "$APPIMAGE_FILE" "$FINAL_BIN_PATH"
    chmod +x "$FINAL_BIN_PATH"

    # --- Store installed path in config --- 
    echo "Storing installation path in configuration..."
    # Use python to call the config setting function
    # Ensure venv is active if installer needs it, or use system python if chromadesk is installed
    PYTHON_CMD="python3" # Default to system python
    if [[ -f ".venv/bin/python" ]]; then
         PYTHON_CMD=".venv/bin/python"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    fi
    
    # Try setting config using Python import first
    if $PYTHON_CMD -c "from chromadesk.core import config; config.set_setting('State', 'installed_appimage_path', '$FINAL_BIN_PATH')" &> /dev/null; then
         echo "Stored path via Python import: $FINAL_BIN_PATH"
    else
        echo_yellow "Warning: Could not set config via Python import. Attempting fallback..."
        # Fallback: Use the installed binary itself
        if "$FINAL_BIN_PATH" --internal-set-config State installed_appimage_path "$FINAL_BIN_PATH"; then
            echo "Stored path via installed binary fallback: $FINAL_BIN_PATH"
        else
            echo_red "Error: Failed to store installation path using both methods."
            echo_yellow "       The daily update timer might not work correctly."
            # Don't exit, installation of binary/desktop files might still be useful
        fi
    fi
    # --------------------------------------

    # 4. Install Icon
    if [[ ! -f "$ICON_SOURCE_PATH" ]]; then
        echo_red "Error: Icon file not found at $ICON_SOURCE_PATH. Skipping icon installation."
    else
        echo "Installing icon to $FINAL_ICON_PATH ..."
        cp "$ICON_SOURCE_PATH" "$FINAL_ICON_PATH"
        # Also copy with simple name for compatibility
        echo "Installing icon as $INSTALL_DIR_ICONS/chromadesk.png ..."
        cp "$ICON_SOURCE_PATH" "$INSTALL_DIR_ICONS/chromadesk.png"

        # Also install icon to pixmaps directory for compatibility
        PIXMAP_DIR="$HOME/.local/share/pixmaps"
        FINAL_PIXMAP_PATH="$PIXMAP_DIR/$ICON_NAME" # Full RDN name path
        SIMPLE_PIXMAP_PATH="$PIXMAP_DIR/chromadesk.png" # Simple name path
        echo "Installing icon to $FINAL_PIXMAP_PATH ..."
        mkdir -p "$PIXMAP_DIR"
        cp "$ICON_SOURCE_PATH" "$FINAL_PIXMAP_PATH"
        # Also copy with simple name for compatibility
        echo "Installing icon as $SIMPLE_PIXMAP_PATH ..."
        cp "$ICON_SOURCE_PATH" "$SIMPLE_PIXMAP_PATH"
    fi

    # 5. Create and Install .desktop file
    echo "Creating desktop file at $FINAL_DESKTOP_PATH ..."
    # Revert to generating the file, but use simple icon name
    # Ensure StartupWMClass is included, similar to build script generated file
    cat > "$FINAL_DESKTOP_PATH" << EOF
[Desktop Entry]
Version=1.0
Name=$APP_NAME
GenericName=Wallpaper Changer
Comment=Daily Bing/Custom Wallpaper Changer for GNOME
Exec=$FINAL_BIN_PATH
Icon=chromadesk # Use simple name, matching one of the installed icon files
Terminal=false
Type=Application
Categories=Utility;GTK;GNOME;
Keywords=wallpaper;background;bing;daily;desktop;image;
StartupNotify=true
StartupWMClass=ChromaDesk
EOF

    # 6. Update Desktop Database
    echo "Updating desktop database..."
    if command -v update-desktop-database &> /dev/null; then
        update-desktop-database "$INSTALL_DIR_DESKTOP"
    else
        echo_yellow "Warning: 'update-desktop-database' command not found. Application menu might not update immediately."
    fi

    # 7. Update Icon Cache
    echo "Updating icon cache..."
    if command -v gtk-update-icon-cache &> /dev/null; then
        # Ensure the base directory exists before updating
        if [ -d "$INSTALL_DIR_ICONS_BASE/hicolor" ]; then
            gtk-update-icon-cache -f -t "$INSTALL_DIR_ICONS_BASE/hicolor"
        else
             echo_yellow "Warning: Icon base directory ($INSTALL_DIR_ICONS_BASE/hicolor) not found, skipping icon cache update."
        fi
    else
        echo_yellow "Warning: 'gtk-update-icon-cache' command not found. Icon might not appear immediately."
    fi

    echo_green "Installation Complete!"
    echo "You can now run ChromaDesk by typing 'chromadesk' in your terminal"
    echo "or finding it in your application menu (may require logout/login)."
    echo_yellow "Note: If 'chromadesk' command is not found, ensure $INSTALL_DIR_BIN is in your PATH."
    echo "You can usually add it by editing ~/.profile or ~/.bashrc and adding:"
    echo "  export PATH=\"$HOME/.local/bin:\$PATH\""

}

# --- Uninstallation Logic ---
uninstall_app() {
    echo_yellow "Uninstalling ChromaDesk..."

    echo "Checking for installed files..."
    found_files=0

    # Check for binary
    if [[ -f "$FINAL_BIN_PATH" ]]; then
        echo "Found binary: $FINAL_BIN_PATH"
        ((found_files++))
    else
        echo "Binary not found at $FINAL_BIN_PATH."
    fi

    # Check for desktop file
    if [[ -f "$FINAL_DESKTOP_PATH" ]]; then
        echo "Found desktop file: $FINAL_DESKTOP_PATH"
        ((found_files++))
    else
        echo "Desktop file not found at $FINAL_DESKTOP_PATH."
    fi

    # Check for icon file
    if [[ -f "$FINAL_ICON_PATH" ]]; then
        echo "Found icon file: $FINAL_ICON_PATH"
        ((found_files++))
    else
        echo "Icon file not found at $FINAL_ICON_PATH."
    fi

    if [[ $found_files -eq 0 ]]; then
        echo_green "ChromaDesk does not appear to be installed in the user local directories. Nothing to do."
        exit 0
    fi

    # Confirmation
    read -p "Are you sure you want to remove these files? (y/N): " confirm
    if [[ "${confirm,,}" != "y" ]]; then # Convert to lowercase
        echo "Uninstallation cancelled."
        exit 0
    fi

    # Remove files
    echo "Removing files..."
    rm -f "$FINAL_BIN_PATH"
    rm -f "$FINAL_DESKTOP_PATH"
    rm -f "$FINAL_ICON_PATH"
    rm -f "$INSTALL_DIR_ICONS/chromadesk.png" # Remove simple hicolor name
    # Also remove pixmap icon
    PIXMAP_DIR="$HOME/.local/share/pixmaps"
    FINAL_PIXMAP_PATH="$PIXMAP_DIR/$ICON_NAME"
    SIMPLE_PIXMAP_PATH="$PIXMAP_DIR/chromadesk.png" # Simple name path
    rm -f "$FINAL_PIXMAP_PATH"
    rm -f "$SIMPLE_PIXMAP_PATH" # Remove simple pixmap name

    # --- Clear installed path in config --- 
    echo "Clearing installation path in configuration..."
    PYTHON_CMD="python3"
    if [[ -f ".venv/bin/python" ]]; then PYTHON_CMD=".venv/bin/python"; 
    elif command -v python &> /dev/null; then PYTHON_CMD="python"; fi
    
    # Try to clear the setting via Python import, ignore errors
    if $PYTHON_CMD -c "from chromadesk.core import config; config.set_setting('State', 'installed_appimage_path', '')" &> /dev/null; then
        echo "Cleared path via Python import."
    else
        echo_yellow "Warning: Could not clear config via Python import. Attempting fallback..."
        # Fallback: Use the installed binary (if it still exists) to clear the setting
        if [[ -f "$FINAL_BIN_PATH" ]]; then
            if "$FINAL_BIN_PATH" --internal-set-config State installed_appimage_path ""; then
                echo "Cleared path via installed binary fallback."
            else
                echo_yellow "Warning: Failed to clear path using installed binary fallback."
            fi
        else
            # Check for the old name too, just in case, before giving up completely
            OLD_BIN_PATH="$INSTALL_DIR_BIN/chromadesk"
            if [[ -f "$OLD_BIN_PATH" ]]; then
                 if "$OLD_BIN_PATH" --internal-set-config State installed_appimage_path ""; then
                      echo "Cleared path via OLD installed binary fallback (chromadesk)."
                 else 
                      echo_yellow "Warning: Failed to clear path using OLD installed binary fallback."
                 fi
            else 
                echo_yellow "Installed binary ('$BIN_NAME' or 'chromadesk') not found, could not use fallback to clear config."
            fi
        fi
    fi
    # --------------------------------------

    # Update Desktop Database
    echo "Updating desktop database..."
    if command -v update-desktop-database &> /dev/null; then
        update-desktop-database "$INSTALL_DIR_DESKTOP"
    else
        echo_yellow "Warning: 'update-desktop-database' command not found. Application menu might not update immediately."
    fi

    # Update Icon Cache (also during uninstall to potentially clean up)
    echo "Updating icon cache..."
    if command -v gtk-update-icon-cache &> /dev/null; then
        if [ -d "$INSTALL_DIR_ICONS_BASE/hicolor" ]; then
            gtk-update-icon-cache -f -t "$INSTALL_DIR_ICONS_BASE/hicolor"
        fi
        # No warning needed if dir doesn't exist during uninstall
    else
        echo_yellow "Warning: 'gtk-update-icon-cache' command not found. Icon cache might not be updated."
    fi

    echo_green "ChromaDesk uninstallation complete."
    echo_yellow "Note: Configuration (~/.config/chromadesk) and wallpaper files (~/Pictures/wallpapers) were NOT removed."
    echo_yellow "      You can remove these manually if desired."
}

# --- Main Script --- 
check_deps # Run dependency check first

if [[ "$1" == "--uninstall" ]]; then
    uninstall_app
else
    install_app
fi

exit 0 