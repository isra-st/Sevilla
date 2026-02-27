"""Configuration from environment. Base URL, delays, proxy, max pages."""
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (parent of idealista_scraper)
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)

# Base URL for selling apartments in Sevilla
IDEALISTA_BASE_URL = os.getenv(
    "IDEALISTA_BASE_URL",
    "https://www.idealista.com/venta-viviendas/sevilla-sevilla/",
).rstrip("/")

# Delay between requests (seconds) - human-like 8-20
def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


DELAY_MIN = _int_env("DELAY_MIN", 8)
DELAY_MAX = _int_env("DELAY_MAX", 20)
MAX_PAGES = _int_env("MAX_PAGES", 60)

# Delay before each search page fetch (pages 2+). 0 = no delay. Set to 5-15 to reduce blocks.
PAGE_DELAY_SEC = _int_env("PAGE_DELAY_SEC", 0)

# Optional proxy URL (e.g. http://user:pass@host:port) for Playwright
PROXY_URL = os.getenv("PROXY_URL", "").strip() or None

# Connect to existing Chrome (e.g. http://localhost:9222) to use your session and avoid 403
CHROME_CDP_URL = os.getenv("CHROME_CDP_URL", "").strip() or None

# Run browser visible (false) to reduce headless detection; default true
def _bool_env(name: str, default: bool) -> bool:
    v = os.getenv(name, "").strip().lower()
    if v in ("1", "true", "yes"):
        return True
    if v in ("0", "false", "no"):
        return False
    return default


HEADLESS = _bool_env("HEADLESS", True)

# Use Selenium + ChromeDriver instead of Playwright (no CDP, no Node; ChromeDriver auto-downloaded)
USE_SELENIUM = _bool_env("USE_SELENIUM", False)

# Scraper approach (overrides default when set). Use --test-approaches to find one that works.
# - undetected: undetected_chromedriver (patched ChromeDriver, best anti-detection)
# - selenium: standard Selenium + ChromeDriver (optional CDP attach)
# - playwright: Playwright + stealth
# - playwright_cdp: Playwright attaching to your Chrome (--remote-debugging-port=9222)
SCRAPER_APPROACH = (os.getenv("SCRAPER_APPROACH", "").strip().lower() or None)

# Pause after first page load so you can solve DataDome captcha in the browser (see ScrapingBee tutorial)
PAUSE_FOR_CAPTCHA = _bool_env("PAUSE_FOR_CAPTCHA", False)

# Idealista domain for normalizing links
IDEALISTA_DOMAIN = "https://www.idealista.com"

# Last real pagination page; pagina-61.htm and above redirect to page 1
IDEALISTA_MAX_PAGE = 60
