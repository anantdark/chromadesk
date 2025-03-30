#!/bin/bash
set -e  # Exit immediately if a command exits with a non-zero status

# Colors for better readability
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Display usage information
show_help() {
    echo -e "${GREEN}ChromaDesk Build Script${NC}"
    echo -e "Usage: $0 [options]"
    echo -e ""
    echo -e "Options:"
    echo -e "  --help, -h             Display this help message"
    echo -e "  --version-update VER   Update version to specified version (e.g., 0.2.0)"
    echo -e "  --build-only           Only build, don't update version"
    echo -e "  --appimage             Create an AppImage after building the executable"
    echo -e "  --debug                Enable verbose debugging output"
    echo -e ""
    echo -e "Examples:"
    echo -e "  $0                      Build the executable using current version"
    echo -e "  $0 --version-update 0.2.0    Update version to 0.2.0 and build"
    echo -e "  $0 --appimage               Build and create an AppImage"
}

# Parse command line arguments
VERSION_UPDATE=""
BUILD_ONLY=false
CREATE_APPIMAGE=false
DEBUG_MODE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --help|-h)
            show_help
            exit 0
            ;;
        --version-update)
            VERSION_UPDATE="$2"
            shift # past argument
            shift # past value
            ;;
        --build-only)
            BUILD_ONLY=true
            shift # past argument
            ;;
        --appimage)
            CREATE_APPIMAGE=true
            shift # past argument
            ;;
        --debug)
            DEBUG_MODE=true
            set -x  # Enable command tracing
            shift # past argument
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            show_help
            exit 1
            ;;
    esac
done

# Function to update version in files
update_version() {
    local version=$1
    
    # Validate version format (simple validation, can be enhanced)
    if ! [[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo -e "${RED}Invalid version format. Please use semantic versioning (e.g., 0.2.0).${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}Updating version to ${YELLOW}$version${NC}"
    
    # Update version in __init__.py
    echo -e "${YELLOW}Updating version in __init__.py...${NC}"
    sed -i "s/__version__ = \".*\"/__version__ = \"$version\"/" chromadesk/__init__.py
    
    # Update version in pyproject.toml
    echo -e "${YELLOW}Updating version in pyproject.toml...${NC}"
    sed -i "s/version = \".*\" # Updated version/version = \"$version\" # Updated version/" pyproject.toml
    sed -i "s/version = \".*\" # Initial version/version = \"$version\" # Updated version/" pyproject.toml
    
    echo -e "${GREEN}Version updated successfully!${NC}"
}

echo -e "${GREEN}=== ChromaDesk Builder ===${NC}"

# Check if the script is run from the project root
if [ ! -f "pyproject.toml" ]; then
    echo -e "${RED}Error: This script must be run from the project root directory!${NC}"
    exit 1
fi

# Update version if specified
if [ -n "$VERSION_UPDATE" ]; then
    update_version "$VERSION_UPDATE"
    
    if [ "$BUILD_ONLY" = true ]; then
        echo -e "${GREEN}Version updated. Skipping build as requested.${NC}"
        exit 0
    fi
fi

# Check for virtual environment
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}Virtual environment not found. Creating one...${NC}"
    python3 -m venv .venv
fi

# Activate virtual environment
echo -e "${GREEN}Activating virtual environment...${NC}"
source .venv/bin/activate

# Verify python is working correctly
echo -e "${GREEN}Checking Python...${NC}"
if ! python --version; then
    echo -e "${RED}Error: Python not functioning correctly in the virtual environment.${NC}"
    exit 1
fi

# Install/upgrade required packages
echo -e "${GREEN}Installing required packages...${NC}"
pip install --upgrade pip
pip install --upgrade build wheel
pip install --upgrade pyinstaller
pip install -e .

# --- Install Dependencies --- 

echo "Installing build dependencies and project into venv..."
.venv/bin/pip install -U pip setuptools wheel build
echo "Installing project core dependencies..."
.venv/bin/pip install .
echo "Installing optional dependencies for AppImage [notifications]..."
.venv/bin/pip install ".[notifications]"

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to install dependencies.${NC}"
    exit 1
fi

# Get version information
VERSION=$(python -c "import chromadesk; print(chromadesk.__version__)")
echo -e "${GREEN}Building version: ${YELLOW}$VERSION${NC}"

# Prepare the build directory
BUILD_DIR="dist"
rm -rf "$BUILD_DIR"
rm -f "chromadesk.desktop" # Clean up previous temporary file if it exists
mkdir -p "$BUILD_DIR"

# Copy icon and desktop file for Linux desktop integration
echo -e "${YELLOW}Preparing desktop integration files...${NC}"
mkdir -p "$BUILD_DIR/usr/share/applications"
mkdir -p "$BUILD_DIR/usr/share/icons/hicolor/128x128/apps"
mkdir -p "$BUILD_DIR/usr/share/pixmaps"

# Create a .desktop file to install to the local desktop
cat > "chromadesk.desktop" << EOF
[Desktop Entry]
Version=1.0
Name=ChromaDesk
GenericName=Wallpaper Changer
Comment=Daily Bing/Custom Wallpaper Changer for GNOME
Exec=chromadesk
Icon=chromadesk
Terminal=false
Type=Application
Categories=Utility;GTK;GNOME;
Keywords=wallpaper;background;bing;daily;desktop;image;
StartupNotify=true
StartupWMClass=ChromaDesk
EOF

# Copy original desktop file to standard locations
cp data/io.github.anantdark.chromadesk.desktop "$BUILD_DIR/usr/share/applications/"

# Copy icon files to various locations for compatibility
cp data/icons/io.github.anantdark.chromadesk.png "$BUILD_DIR/usr/share/icons/hicolor/128x128/apps/"
cp data/icons/io.github.anantdark.chromadesk.png "$BUILD_DIR/usr/share/pixmaps/chromadesk.png"

# Create icon in standard locations with standard names (following freedesktop specs)
cp data/icons/io.github.anantdark.chromadesk.png "$BUILD_DIR/usr/share/icons/hicolor/128x128/apps/chromadesk.png"

# AppImage requires the icon in the root with the EXACT same name as referenced in the desktop file
cp data/icons/io.github.anantdark.chromadesk.png "$BUILD_DIR/chromadesk.png"

# For AppImage icon to work properly, also create .DirIcon symlink in the AppDir root
ln -sf "chromadesk.png" "$BUILD_DIR/.DirIcon"

# Create proper desktop file in AppDir root for AppImage
echo -e "${YELLOW}Creating desktop file for AppImage...${NC}"
cp "chromadesk.desktop" "$BUILD_DIR/chromadesk.desktop"

# Modify AppDir desktop file for AppImage (crucial for AppImage)
sed -i 's/Exec=.*/Exec=AppRun/' "$BUILD_DIR/chromadesk.desktop"

# Also create the standard name desktop file in the root
cp "$BUILD_DIR/chromadesk.desktop" "$BUILD_DIR/io.github.anantdark.chromadesk.desktop"

# Clean up temporary desktop file
rm -f "chromadesk.desktop"

# Print desktop file content for debugging
if [ "$DEBUG_MODE" = true ]; then
    echo -e "${YELLOW}AppDir root desktop file content:${NC}"
    cat "$BUILD_DIR/chromadesk.desktop"
fi

# Print a warning about the PyInstaller icon limitation
echo -e "${YELLOW}Note: The 'Ignoring icon' warning from PyInstaller is normal on Linux.${NC}"
echo -e "${YELLOW}      We're handling the icon properly for Linux desktop integration.${NC}"

# Build using PyInstaller
echo -e "${GREEN}Building with PyInstaller...${NC}"
pyinstaller --name="chromadesk" \
            --windowed \
            --onefile \
            --add-data="data:data" \
            --add-data="chromadesk/services/templates:templates" \
            --icon="data/icons/io.github.anantdark.chromadesk.png" \
            --distpath="$BUILD_DIR/usr/bin" \
            chromadesk/main.py

# Check if build was successful
if [ $? -eq 0 ]; then
    echo -e "${GREEN}Build successful!${NC}"
    
    # Find the executable file that was created
    if [ -f "$BUILD_DIR/usr/bin/chromadesk" ]; then
        echo -e "${GREEN}Executable created: ${YELLOW}$BUILD_DIR/usr/bin/chromadesk${NC}"
        echo -e "${GREEN}Making executable...${NC}"
        chmod +x "$BUILD_DIR/usr/bin/chromadesk"
        
        # --- Embed AppImage Path --- #
        # Create a file inside the AppDir containing the intended absolute path to the final AppImage
        # APPIMAGE_FINAL_NAME="chromadesk-$VERSION-x86_64.AppImage"
        # Assume build script is run from project root where AppImage will be created
        # APPIMAGE_FINAL_PATH="$PWD/$APPIMAGE_FINAL_NAME"
        # echo "$APPIMAGE_FINAL_PATH" > "$BUILD_DIR/appimage_exec_path.txt"
        # echo "DEBUG: Wrote intended AppImage path ($APPIMAGE_FINAL_PATH) to $BUILD_DIR/appimage_exec_path.txt" # Debug
        # ------------------------ #

        # Create a symbolic link to the executable in the root directory as AppRun
        echo -e "${YELLOW}Creating AppRun symlink...${NC}"
        ln -sf "usr/bin/chromadesk" "$BUILD_DIR/AppRun"
        
        # Display version information
        echo -e "${GREEN}Built version: ${YELLOW}$VERSION${NC}"
        
        # Create AppImage if requested
        if [ "$CREATE_APPIMAGE" = true ]; then
            echo -e "${GREEN}Creating AppImage...${NC}"
            
            # Check if appimagetool is available
            if ! command -v appimagetool &> /dev/null; then
                echo -e "${YELLOW}appimagetool not found. Attempting to download...${NC}"
                
                # Create a temporary directory
                TEMP_DIR=$(mktemp -d)
                cd "$TEMP_DIR"
                
                # Download appimagetool
                wget -q https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
                chmod +x appimagetool-x86_64.AppImage
                
                # Use the downloaded tool
                APPIMAGETOOL="$TEMP_DIR/appimagetool-x86_64.AppImage"
                
                cd - > /dev/null # Return to previous directory
            else
                APPIMAGETOOL="appimagetool"
            fi
            
            # Create AppImage
            APPDIR_PATH="$PWD/$BUILD_DIR"
            OUTPUT_NAME="chromadesk-$VERSION-x86_64.AppImage"
            
            echo -e "${YELLOW}Generating AppImage from $APPDIR_PATH${NC}"
            
            # Debug: List contents of AppDir to help diagnose issues
            echo -e "${YELLOW}AppDir contents:${NC}"
            find "$APPDIR_PATH" -maxdepth 1 -type f
            echo -e "${YELLOW}Desktop files:${NC}"
            find "$APPDIR_PATH" -name "*.desktop" | sort
            echo -e "${YELLOW}Icon files:${NC}"
            find "$APPDIR_PATH" -name "*.png" | sort
            
            # Create the AppImage
            if [ -n "$APPIMAGETOOL" ]; then
                echo -e "${YELLOW}Running appimagetool: $APPIMAGETOOL${NC}"
                # Run with debugging output
                ARCH=x86_64 "$APPIMAGETOOL" "$APPDIR_PATH" "$OUTPUT_NAME"
                
                if [ $? -eq 0 ]; then
                    echo -e "${GREEN}AppImage created: ${YELLOW}$OUTPUT_NAME${NC}"
                    chmod +x "$OUTPUT_NAME"

                    # Desktop integration is often handled by external tools (like appimaged)
                    # or manually by the user. Removing automatic integration attempt.
                    # echo -e "${YELLOW}Setting up desktop integration...${NC}"
                    # "./$OUTPUT_NAME" --appimage-portable-home --appimage-extract-and-run &
                    # sleep 2
                    # kill $! >/dev/null 2>&1 || true
                    # Re-adding the previous integration attempt that seemed to work
                    echo -e "${YELLOW}Setting up desktop integration (previous method)...${NC}"
                    "./$OUTPUT_NAME" --appimage-portable-home --appimage-extract-and-run &
                    sleep 2 # Give it a moment to potentially register
                    kill $! >/dev/null 2>&1 || true # Kill the launched app
                else
                    echo -e "${RED}AppImage creation failed!${NC}"
                fi
                
                # Clean up temporary directory if we created one
                if [ -n "$TEMP_DIR" ]; then
                    rm -rf "$TEMP_DIR"
                fi
            else
                echo -e "${RED}Could not find or download appimagetool. AppImage creation skipped.${NC}"
                echo -e "${YELLOW}Please install appimagetool manually and try again.${NC}"
            fi
        else
            echo -e "${YELLOW}Skipping AppImage creation. Use --appimage to create one.${NC}"
        fi
        
        echo -e "${GREEN}Build artifacts in '$BUILD_DIR/' directory${NC}"
        ls -la "$BUILD_DIR"
    else
        echo -e "${YELLOW}Warning: Executable file not found. Check the build output.${NC}"
    fi
else
    echo -e "${RED}Build failed!${NC}"
    exit 1
fi

# Deactivate virtual environment
deactivate

echo -e "${GREEN}=== Build process completed ===${NC}" 