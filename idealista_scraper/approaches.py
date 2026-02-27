"""
Scraper approaches: multiple techniques to fetch pages and bypass blocking.
Use SCRAPER_APPROACH in .env or --test-approaches to try each and see which works.
"""
from typing import List, Optional

from idealista_scraper.config import CHROME_CDP_URL, SCRAPER_APPROACH, USE_SELENIUM

# All approaches we can test (order = suggested try order)
APPROACHES: List[str] = [
    "undetected",   # undetected_chromedriver – patched ChromeDriver, best anti-detection
    "selenium",     # Selenium + ChromeDriver (optional CDP = your browser)
    "playwright",  # Playwright + stealth
    "playwright_cdp",  # Playwright attaching to your Chrome (--remote-debugging-port=9222)
]


def resolve_approach(override: Optional[str] = None) -> str:
    """
    Resolve which approach to use. Precedence: override > SCRAPER_APPROACH > USE_SELENIUM > default.
    Returns one of APPROACHES.
    """
    if override and override.lower() in APPROACHES:
        return override.lower()
    if SCRAPER_APPROACH and SCRAPER_APPROACH in APPROACHES:
        return SCRAPER_APPROACH
    if USE_SELENIUM:
        return "selenium"
    if CHROME_CDP_URL:
        return "playwright_cdp"
    return "playwright"  # default; set SCRAPER_APPROACH=undetected to try best anti-detection


def is_selenium_like(approach: str) -> bool:
    """True if this approach uses a Selenium WebDriver (selenium or undetected)."""
    return approach in ("selenium", "undetected")


def is_playwright_like(approach: str) -> bool:
    """True if this approach uses Playwright."""
    return approach in ("playwright", "playwright_cdp")
