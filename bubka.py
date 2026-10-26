
from bs4 import BeautifulSoup
import requests
import os
import time
from urllib.parse import urljoin, urlparse

TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
TELEGRAM_THREAD_ID = os.environ.get("TELEGRAM_THREAD_ID")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# Example: https://www.idol-culture.jp/geinou/228792/
NEWS_URL = os.environ.get(
    "NEWS_URL",
    "https://www.idol-culture.jp/geinou/228792/"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
}

session = requests.Session()
session.headers.update(HEADERS)


def remove_all_params(url):
    """Remove query parameters from an image URL."""
    parsed = urlparse(url)
    return parsed._replace(query="", fragment="").geturl()


def get_article_images():
    """
    Fetch a Bubka article and extract image URLs.

    Uses common WordPress/article image markup and srcset attributes.
    """
    response = session.get(NEWS_URL, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")
    image_urls = []
    seen = set()

    # Prefer the article content rather than the entire page.
    article = (
        soup.find("article")
        or soup.find("div", class_="article")
        or soup.find("main")
        or soup
    )

    for img in article.find_all("img"):
        candidates = []

        # srcset can contain higher-resolution versions.
        srcset = img.get("srcset", "")
        if srcset:
            for item in srcset.split(","):
                parts = item.strip().split()
                if parts:
                    candidates.append(parts[0])

        # Lazy-loaded images are common on Japanese websites.
        for attr in (
            "data-src",
            "data-original",
            "data-lazy-src",
            "src",
        ):
            value = img.get(attr)
            if value:
                candidates.append(value)

        if not candidates:
            continue

        # Prefer the last srcset candidate, which is often the largest.
        src = candidates[0]
        if srcset:
            src = candidates[len(srcset.split(",")) - 1]

        img_url = urljoin(NEWS_URL, src)
        parsed = urlparse(img_url)

        if parsed.scheme not in ("http", "https"):
            continue

        path_lower = parsed.path.lower()

        # Filter obvious non-article images.
        if any(
            word in path_lower
            for word in (
                "logo",
                "icon",
                "avatar",
                "banner",
                "advert",
                "tracking",
            )
        ):
            continue

        if not any(
            path_lower.endswith(ext)
            for ext in (
                ".jpg", ".jpeg", ".png", ".webp", ".gif",
                ".avif",
            )
        ):
            continue

        img_url = remove_all_params(img_url)

        if img_url not in seen:
            seen.add(img_url)
            image_urls.append(img_url)

    print("Article:", NEWS_URL)
    print("Total images:", len(image_urls))

    return image_urls


def telegram_request(method, payload, files=None):
    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/{method}"
    )

    if TELEGRAM_THREAD_ID:
        payload["message_thread_id"] = int(TELEGRAM_THREAD_ID)

    response = requests.post(
        url,
        data=payload,
        files=files,
        timeout=60,
    )
    response.raise_for_status()

    result = response.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegram API error: {result}")

    return result


def send_telegram_message(caption):
    telegram_request(
        "sendMessage",
        {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": caption,
            "parse_mode": "HTML",
        },
    )
    time.sleep(1)


def send_telegram_file_link(caption, file_link):
    """Send an image URL as a Telegram document."""
    max_retries = 5

    for attempt in range(max_retries):
        try:
            telegram_request(
                "sendDocument",
                {
                    "chat_id": TELEGRAM_CHAT_ID,
                    "caption": caption,
                    "document": file_link,
                },
            )
            time.sleep(2)
            return True

        except Exception as exc:
            print(f"sendDocument attempt {attempt + 1}: {exc}")
            if attempt < max_retries - 1:
                time.sleep(5)

    return False


# =========================
# MAIN FLOW
# =========================

if not TELEGRAM_CHAT_ID or not TELEGRAM_BOT_TOKEN:
    raise RuntimeError(
        "Set TELEGRAM_CHAT_ID and TELEGRAM_BOT_TOKEN."
    )

picture_url_list = get_article_images()

if not picture_url_list:
    raise RuntimeError(
        "No article images found. Inspect the HTML and update "
        "the image selectors."
    )

send_telegram_message(NEWS_URL)

for i, picture_url in enumerate(picture_url_list):
    print(f"Sending {i + 1}/{len(picture_url_list)}: {picture_url}")

    success = send_telegram_file_link(
        f"{i + 1}/{len(picture_url_list)}",
        picture_url,
    )

    if not success:
        print("Failed:", picture_url)
