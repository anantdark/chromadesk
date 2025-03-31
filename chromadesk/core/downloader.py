# chromadesk/chromadesk/core/downloader.py
import io
import logging
from pathlib import Path

import requests
from PIL import Image  # Using Pillow for validation

logger = logging.getLogger()


def download_image(url: str, save_path: Path) -> bool:
    """
    Downloads an image from a URL and saves it to the specified path.
    Validates that the downloaded content is a valid JPG or PNG image.

    Args:
        url (str): The URL of the image to download.
        save_path (Path): The full path (including filename) where the image should be saved.

    Returns:
        bool: True if download and validation are successful, False otherwise.
    """
    logger.info(f"Attempting to download image from {url} to {save_path}")

    try:
        # Ensure the parent directory exists
        save_path.parent.mkdir(parents=True, exist_ok=True)

        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.0.0 Safari/537.36"
        }
        # Use stream=True to avoid loading the whole image into memory at once
        response = requests.get(
            url, headers=headers, stream=True, timeout=30
        )  # 30 sec timeout for download
        response.raise_for_status()

        # Check content type (optional but good practice)
        content_type = response.headers.get("content-type", "").lower()
        if not content_type.startswith("image/"):
            logger.warning(
                f"URL {url} did not return an image content-type (got: {content_type}). Proceeding with validation."
            )
            # Don't fail here, rely on Pillow validation

        # Read content into memory for validation BEFORE writing to disk
        image_bytes = response.content  # Read all content now stream=True is handled
        if not image_bytes:
            logger.error(f"Downloaded zero bytes from {url}")
            return False

        # Validate using Pillow
        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                img.verify()  # Verify image data integrity
                # Check format after verification
                if img.format not in ("JPEG", "PNG"):
                    logger.error(
                        f"Downloaded image format is not JPEG or PNG (format: {img.format}) from {url}"
                    )
                    return False
                logger.info(f"Image validated successfully (Format: {img.format})")

        except (IOError, SyntaxError, Image.UnidentifiedImageError) as img_err:
            logger.error(
                f"Downloaded content from {url} is not a valid image or is corrupted: {img_err}"
            )
            return False

        # Write the validated image bytes to the file
        with open(save_path, "wb") as f:
            f.write(image_bytes)

        logger.info(f"Successfully downloaded and saved image to {save_path}")
        return True

    except requests.exceptions.Timeout:
        logger.error(f"Timeout occurred while downloading image from {url}")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error downloading image from {url}: {e}")
        return False
    except OSError as e:
        logger.error(f"Error saving image to {save_path}: {e}")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred during image download: {e}")
        return False


# Example Usage (can be tested independently)
if __name__ == "__main__":
    print("Testing Image Downloader...")
    # Ensure Pillow is installed: pip install Pillow

    from datetime import date

    from .history import (ensure_wallpaper_dir,  # Import history functions
                          get_wallpaper_dir)

    # --- TEMPORARY MODIFICATION FOR TESTING HISTORY ---
    # Ensure the actual wallpaper directory exists
    ensure_wallpaper_dir()
    # Set download_dir to the actual wallpaper directory
    download_dir = get_wallpaper_dir()

    # Use the Bing image URL fetched previously
    test_image_url_jpg = "https://www.bing.com/th?id=OHR.CarrizoBloom_EN-US2504669059_1920x1080.jpg&rf=LaDigue_1920x1080.jpg&pid=hp"  # Example JPG

    # Create a filename like bing_YYYYMMDD.jpg
    today_str = date.today().strftime("%Y%m%d")
    test_save_path_jpg = download_dir / f"bing_{today_str}.jpg"
    # --- END OF TEMPORARY MODIFICATION ---

    # (Keep the rest of the test code as is, or comment out the PNG/invalid tests for now)

    print(f"\n--- Testing Valid JPG ({test_image_url_jpg}) ---")
    print(f"--- Saving to real wallpaper dir: {test_save_path_jpg} ---")  # Added info
    success_jpg = download_image(test_image_url_jpg, test_save_path_jpg)
    print(f"Download Success: {success_jpg}")
    if success_jpg:
        print(f"Check file: {test_save_path_jpg.resolve()}")

    # ... (rest of tests can be commented out if desired using ''' or # ) ...

    # print(f"\nCleanup: You can delete the '{download_dir}' directory.") # Comment this out too
