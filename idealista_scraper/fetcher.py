"""Fetch HTML from Idealista: Playwright or Selenium (stealth + delays + scroll)."""
import asyncio
import random
import time
from typing import Any, Optional

from idealista_scraper.config import (
    CHROME_CDP_URL,
    DELAY_MAX,
    DELAY_MIN,
    HEADLESS,
    PROXY_URL,
    USE_SELENIUM,
)
from idealista_scraper.approaches import is_selenium_like, resolve_approach


def _random_delay(min_sec: float = None, max_sec: float = None) -> float:
    min_sec = min_sec if min_sec is not None else DELAY_MIN
    max_sec = max_sec if max_sec is not None else DELAY_MAX
    return random.uniform(min_sec, max_sec)


def _dismiss_idealista_cookie_banner_selenium(driver: Any) -> None:
    """If Idealista cookie banner is visible, click 'Aceptar y continuar'. No-op if not found."""
    if not driver or "idealista" not in (driver.current_url or ""):
        return
    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait
        time.sleep(2)  # let banner render
        wait = WebDriverWait(driver, 5)
        # Try common selectors for the accept button (text in Spanish)
        selectors = [
            "//button[contains(., 'Aceptar')]",
            "//*[@role='button' and contains(., 'Aceptar')]",
            "//a[contains(., 'Aceptar')]",
            "//button[contains(., 'continuar')]",
        ]
        for xpath in selectors:
            try:
                btn = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
                if btn and btn.is_displayed():
                    btn.click()
                    time.sleep(1)
                    return
            except Exception:
                continue
    except Exception:
        pass


async def _dismiss_idealista_cookie_banner_playwright(page: Any, url: str = "") -> None:
    """If Idealista cookie banner is visible, click 'Aceptar y continuar'. No-op if not found."""
    try:
        if "idealista" not in url and "idealista" not in (page.url if hasattr(page, "url") else ""):
            return
        await asyncio.sleep(2)  # let banner render
        selectors = [
            "button:has-text('Aceptar')",
            "button:has-text('continuar')",
            "[role='button']:has-text('Aceptar')",
            "a:has-text('Aceptar y continuar')",
        ]
        for sel in selectors:
            try:
                loc = page.locator(sel)
                if await loc.count() > 0:
                    first = loc.first
                    if await first.is_visible():
                        await first.click()
                        await asyncio.sleep(1)
                        return
            except Exception:
                continue
    except Exception:
        pass


# Common viewports (human-like variation)
_VIEWPORTS = (
    {"width": 1920, "height": 1080},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
)


async def _human_scroll_playwright(page: Any) -> None:
    """Scroll down in 2–4 steps with small pauses (human-like)."""
    total = await page.evaluate("document.body.scrollHeight")
    step = max(400, total // random.randint(2, 4))
    pos = 0
    while pos < total:
        pos = min(pos + step, total)
        await page.evaluate(f"window.scrollTo({{ top: {pos}, behavior: 'smooth' }})")
        await asyncio.sleep(random.uniform(0.3, 0.9))


async def fetch_html_with_page(
    page: Any,
    url: str,
    *,
    delay_before: Optional[float] = None,
    scroll: bool = True,
    pause_for_captcha: bool = False,
) -> tuple[str, int]:
    """
    Fetch URL using an existing Playwright page. Applies delay then page.goto.
    Does not launch or close the browser. Returns (html, status_code).
    """
    delay = _random_delay(delay_before or DELAY_MIN, delay_before or DELAY_MAX)
    await asyncio.sleep(delay)
    resp = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    status = resp.status if resp else 0
    if "idealista" in url:
        await _dismiss_idealista_cookie_banner_playwright(page, url)
    if pause_for_captcha:
        import sys
        print("Waiting 60 seconds before continuing...", file=sys.stderr, flush=True)
        await asyncio.sleep(60)
    if scroll and status == 200:
        await asyncio.sleep(random.uniform(2.5, 5.5))
        await _human_scroll_playwright(page)
    html = await page.content()
    return html, status


def _human_scroll(driver: Any) -> None:
    """Scroll down in 2–4 steps with small pauses (human-like)."""
    try:
        total = driver.execute_script("return document.body.scrollHeight")
        step = max(400, total // random.randint(2, 4))
        pos = 0
        while pos < total:
            pos = min(pos + step, total)
            driver.execute_script(f"window.scrollTo({{ top: {pos}, behavior: 'smooth' }})")
            time.sleep(random.uniform(0.3, 0.9))
    except Exception:
        driver.execute_script(
            "window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' })"
        )
        time.sleep(random.uniform(1, 2))


def _fetch_html_selenium_sync(
    driver: Any,
    url: str,
    *,
    delay_before: Optional[float] = None,
    scroll: bool = True,
    approach: Optional[str] = None,
    pause_for_captcha: bool = False,
    driver_lock: Optional[Any] = None,
) -> tuple[str, int]:
    """
    Sync: use Selenium (or undetected_chromedriver) to load url and return (page_source, 200).
    If driver is None, creates or attaches to Chrome, then quits when own_driver.
    When driver_lock is provided and driver is not None, holds the lock for the whole fetch
    (Selenium drivers are not thread-safe; asyncio.to_thread may run each call in a different thread).
    """
    import sys
    from urllib.parse import urlparse
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    own_driver = driver is None
    attached_to_user_chrome = False
    approach = approach or resolve_approach()

    # When pausing for captcha, browser must be visible so the user can solve it
    headless = HEADLESS and not pause_for_captcha

    if own_driver:
        if approach == "undetected":
            try:
                import re
                import undetected_chromedriver as uc
                driver = uc.Chrome(headless=headless, use_subprocess=True)
            except ImportError:
                print("undetected_chromedriver not installed. Run: pip install undetected-chromedriver", file=sys.stderr)
                approach = "selenium"
            except Exception as e:
                err = str(e)
                err_lower = err.lower()
                # Retry with version_main if error says "Current browser version is X"
                match = re.search(r"Current browser version is (\d+)", err, re.I)
                if match and ("version" in err_lower or "chromedriver" in err_lower):
                    try:
                        version_main = int(match.group(1))
                        driver = uc.Chrome(headless=headless, use_subprocess=True, version_main=version_main)
                    except Exception:
                        print(f"undetected_chromedriver failed: {e}. Falling back to standard Selenium.", file=sys.stderr)
                        approach = "selenium"
                else:
                    if "version" in err_lower or "chromedriver" in err_lower:
                        print(f"undetected_chromedriver failed: {e}. Falling back to standard Selenium.", file=sys.stderr)
                    approach = "selenium"

        if own_driver and driver is None:
            opts = Options()
            if CHROME_CDP_URL:
                parsed = urlparse(CHROME_CDP_URL)
                addr = f"{parsed.hostname or '127.0.0.1'}:{parsed.port or 9222}"
                opts.add_experimental_option("debuggerAddress", addr)
                try:
                    driver = webdriver.Chrome(options=opts)
                    attached_to_user_chrome = True
                except Exception as e:
                    err = str(e).lower()
                    if "cannot connect" in err or "not reachable" in err or "session not created" in err:
                        print(
                            f"Could not connect to Chrome at {addr}. Starting a new browser instead.\n"
                            "To use your own Chrome (recommended to avoid blocks):\n"
                            "  1. Close Chrome, then start it with: chrome.exe --remote-debugging-port=9222\n"
                            "  2. Leave that window open and run this again.",
                            file=sys.stderr,
                        )
                        opts = Options()
                        opts.add_argument("--disable-blink-features=AutomationControlled")
                        opts.add_argument("--disable-infobars")
                        if headless:
                            opts.add_argument("--headless=new")
                        opts.add_argument(
                            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                        )
                        if PROXY_URL:
                            opts.add_argument(f"--proxy-server={PROXY_URL}")
                        driver = webdriver.Chrome(options=opts)
                    else:
                        raise
            else:
                opts.add_argument("--disable-blink-features=AutomationControlled")
                opts.add_argument("--disable-infobars")
                if headless:
                    opts.add_argument("--headless=new")
                opts.add_argument(
                    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                )
                if PROXY_URL:
                    opts.add_argument(f"--proxy-server={PROXY_URL}")
                driver = webdriver.Chrome(options=opts)

    def _do_fetch() -> tuple[str, int]:
        delay = _random_delay(delay_before or DELAY_MIN, delay_before or DELAY_MAX)
        time.sleep(delay)
        driver.get(url)
        if "idealista" in url:
            _dismiss_idealista_cookie_banner_selenium(driver)
        if pause_for_captcha:
            time.sleep(6)  # give page time to appear
            import sys
            print("Waiting 60 seconds before continuing...", file=sys.stderr, flush=True)
            time.sleep(60)
        else:
            time.sleep(random.uniform(2.5, 5.5))
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.support.ui import WebDriverWait
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/inmueble/']"))
            )
        except Exception:
            pass
        time.sleep(random.uniform(0.8, 2.2))
        if scroll:
            _human_scroll(driver)
        html = driver.page_source or ""
        return (html, 200)

    try:
        if driver_lock is not None and driver is not None:
            with driver_lock:
                return _do_fetch()
        return _do_fetch()
    finally:
        if own_driver and not attached_to_user_chrome and driver is not None:
            try:
                driver.quit()
            except (OSError, Exception):
                pass


async def fetch_html_playwright(
    url: str,
    *,
    headless: bool = True,
    delay_before: Optional[float] = None,
    scroll: bool = True,
    connect_cdp: Optional[bool] = None,
    pause_for_captcha: bool = False,
) -> tuple[str, int]:
    """
    Fetch URL with Playwright + stealth. When connect_cdp is True, connect to CHROME_CDP_URL;
    when False, always launch. When None, connect if CHROME_CDP_URL is set.
    """
    from playwright.async_api import async_playwright

    try:
        from playwright_stealth import stealth_async
    except ImportError:
        stealth_async = None

    use_cdp = connect_cdp if connect_cdp is not None else bool(CHROME_CDP_URL)
    delay = _random_delay(delay_before or DELAY_MIN, delay_before or DELAY_MAX)
    await asyncio.sleep(delay)

    async with async_playwright() as p:
        if use_cdp and CHROME_CDP_URL:
            try:
                browser = await p.chromium.connect_over_cdp(CHROME_CDP_URL)
            except Exception as e:
                raise RuntimeError(
                    f"Could not connect to Chrome at {CHROME_CDP_URL}. "
                    "Start Chrome with: chrome.exe --remote-debugging-port=9222 "
                    "(leave it open), then run this again. Error: " + str(e)
                ) from e
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = await context.new_page()
        else:
            headless = HEADLESS and not pause_for_captcha
            browser = await p.chromium.launch(headless=headless)
            ctx_opts: dict = {
                "viewport": {"width": 1920, "height": 1080},
                "user_agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            }
            if PROXY_URL:
                ctx_opts["proxy"] = {"server": PROXY_URL}
            context = await browser.new_context(**ctx_opts)
            page = await context.new_page()
            if stealth_async:
                await stealth_async(page)
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            status = resp.status if resp else 0
            if pause_for_captcha:
                await asyncio.sleep(6)
                import sys
                print("Waiting 60 seconds before continuing...", file=sys.stderr, flush=True)
                await asyncio.sleep(60)
            if scroll and status == 200:
                await asyncio.sleep(random.uniform(2, 5))
                await page.evaluate(
                    "window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' })"
                )
                await asyncio.sleep(random.uniform(1, 3))
            html = await page.content()
        finally:
            await browser.close()
    return html, status


async def fetch_html(url: str, **kwargs) -> tuple[str, int]:
    """
    Fetch URL with the resolved approach (undetected, selenium, playwright, playwright_cdp).
    When page is provided, uses that page. When driver is provided, uses that driver.
    Returns (html, status_code).
    """
    # Copy so we don't mutate the caller's dict (orchestrator reuses the same kwargs every fetch)
    kwargs = dict(kwargs)
    page = kwargs.pop("page", None)
    driver = kwargs.pop("driver", None)
    approach = kwargs.pop("approach", None) or resolve_approach()
    pause_for_captcha = kwargs.pop("pause_for_captcha", False)
    driver_lock = kwargs.pop("driver_lock", None)
    extra = {
        "approach": approach,
        "pause_for_captcha": pause_for_captcha,
        "driver_lock": driver_lock,
    }

    if driver is not None:
        return await asyncio.to_thread(
            _fetch_html_selenium_sync, driver, url, **{**kwargs, **extra}
        )
    if is_selenium_like(approach) and page is None:
        return await asyncio.to_thread(
            _fetch_html_selenium_sync, None, url, **{**kwargs, **extra}
        )
    if page is not None:
        return await fetch_html_with_page(page, url, **{**kwargs, "pause_for_captcha": pause_for_captcha})
    if approach == "playwright_cdp" and CHROME_CDP_URL:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            try:
                browser = await p.chromium.connect_over_cdp(CHROME_CDP_URL)
            except Exception:
                return await fetch_html_playwright(url, connect_cdp=False, **{**kwargs, "pause_for_captcha": pause_for_captcha})
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = await context.new_page()
            try:
                return await fetch_html_with_page(page, url, **{**kwargs, "pause_for_captcha": pause_for_captcha})
            finally:
                await browser.close()
    # When testing "playwright" we must launch, not connect (even if CHROME_CDP_URL is set)
    use_cdp = approach != "playwright" and bool(CHROME_CDP_URL)
    return await fetch_html_playwright(url, connect_cdp=use_cdp, **{**kwargs, "pause_for_captcha": pause_for_captcha})


async def fetch_html_with_retry(
    url: str,
    max_retries: int = 3,
    backoff_sec: tuple[float, ...] = (10, 30, 60),
    **kwargs,
) -> tuple[str, int]:
    """
    Fetch URL with retries. Returns (html, status_code). Never raises:
    after all retries returns last (html, status) or ("", 0) on repeated errors.
    """
    last_result: tuple[str, int] = ("", 0)
    for attempt in range(max_retries):
        try:
            html, status = await fetch_html(url, **kwargs)
            last_result = (html, status)
            if status == 200:
                return (html, status)
        except Exception:
            last_result = ("", 0)
        if attempt < max_retries - 1:
            wait = backoff_sec[attempt] if attempt < len(backoff_sec) else backoff_sec[-1]
            await asyncio.sleep(wait)
    return last_result


def is_blocked_page(html: str) -> bool:
    """True if response looks like DataDome/block page (enable JS, hard block, etc.)."""
    if not html or len(html) < 500:
        return True
    block_indicators = [
        "Please enable JS",
        "enable JavaScript",
        "disable any ad blocker",
        "datadome",
        "bloqueado",
        "blocked",
        "captcha",
        # Avoid "challenge" alone – too broad; use phrases that indicate a block page
        "captcha challenge",
        "security challenge",
        "please complete the challenge",
        # Idealista hard block (full block, not a solvable captcha)
        "se ha detectado un uso indebido",
        "el acceso se ha bloqueado",
        "uso indebido",
    ]
    lower = html.lower()
    return any(ind.lower() in lower for ind in block_indicators)
