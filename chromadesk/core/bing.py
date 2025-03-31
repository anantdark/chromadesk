# chromadesk/chromadesk/core/bing.py
import json
import logging
from urllib.parse import urljoin

import requests

# Use the same logger configured in config.py
logger = logging.getLogger()

BING_BASE_URL = "https://www.bing.com"
# Reference: https://github.com/binghp/binghp.github.io/blob/main/src/api/common.js
# Available markets can be found via https://www.bing.com/account/general (Region/Language settings)
# Common ones: en-US, en-GB, en-CA, en-AU, de-DE, fr-FR, ja-JP, zh-CN
BING_API_URL = (
    "https://www.bing.com/HPImageArchive.aspx?format=js&idx=0&n=1&mkt={region}"
)


def fetch_bing_wallpaper_info(region="en-US"):
    """
    Fetches wallpaper metadata from the Bing HPImageArchive API.

    Args:
        region (str): The market region (e.g., 'en-US', 'de-DE').

    Returns:
        dict: A dictionary containing 'url', 'date' (YYYYMMDD), 'copyright',
              'title', and 'full_url' on success, or None on failure.
    """
    url = BING_API_URL.format(region=region)
    logger.info(f"Fetching Bing wallpaper info for region {region} from {url}")

    try:
        # Add a user-agent to potentially avoid blocking
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)  # 10 second timeout
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)

        data = response.json()

        if not data or "images" not in data or not data["images"]:
            logger.error("No images found in Bing API response.")
            return None

        image_data = data["images"][0]

        # Construct full URL
        image_url = image_data.get("url")
        if not image_url:
            logger.error("No 'url' field found in Bing image data.")
            return None
        full_image_url = urljoin(
            BING_BASE_URL, image_url
        )  # Handles relative URLs correctly

        # Extract other useful info
        result = {
            "url": image_url,  # Sometimes useful to have the relative one too
            "full_url": full_image_url,
            "date": image_data.get("startdate", ""),  # YYYYMMDD format
            "copyright": image_data.get("copyright", "N/A"),
            "title": image_data.get("title", "N/A"),
        }
        logger.info(
            f"Successfully fetched Bing info: Date={result['date']}, Title={result['title']}"
        )
        return result

    except requests.exceptions.RequestException as e:
        logger.error(f"Network error fetching Bing data: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding Bing API JSON response: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred during Bing fetch: {e}")
        return None


# Example Usage (can be tested independently)
if __name__ == "__main__":
    print("Testing Bing API fetch...")

    # Test default region
    print("\n--- Testing Default Region (en-US) ---")
    info_us = fetch_bing_wallpaper_info()
    if info_us:
        print(f"Date: {info_us['date']}")
        print(f"Title: {info_us['title']}")
        print(f"Copyright: {info_us['copyright']}")
        print(f"URL: {info_us['full_url']}")
    else:
        print("Failed to fetch info for en-US.")

    # Test another region
    print("\n--- Testing Another Region (en-IN) ---")
    info_de = fetch_bing_wallpaper_info(region="en-IN")
    if info_de:
        print(f"Date: {info_de['date']}")
        print(f"Title: {info_de['title']}")
        print(f"Copyright: {info_de['copyright']}")
        print(f"URL: {info_de['full_url']}")
    else:
        print("Failed to fetch info for de-DE.")

    # Test invalid region (expect failure)
    print("\n--- Testing Invalid Region (xx-XX) ---")
    info_xx = fetch_bing_wallpaper_info(region="xx-XX")
    if not info_xx:
        print("Correctly failed to fetch info for invalid region xx-XX.")
    else:
        print("ERROR: Fetch succeeded for invalid region xx-XX!")
        print(info_xx)
