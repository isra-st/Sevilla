"""
Orchestrator: fetch search pages with pagination, optional detail fetch, dedupe by link.
Supports resume (skip already-seen URLs) and incremental callback for each record.
Uses retries: only stops on first-page failure (block/network). Other pages/detail: retry then continue.
When not using ScrapFly, reuses one Playwright browser for the whole run (faster).
"""
import asyncio
import logging
import math
import random
from typing import Any, Callable, Optional

from idealista_scraper.approaches import is_selenium_like, resolve_approach
from idealista_scraper.config import (
    CHROME_CDP_URL,
    IDEALISTA_BASE_URL,
    IDEALISTA_DOMAIN,
    IDEALISTA_MAX_PAGE,
    HEADLESS,
    MAX_PAGES,
    PAGE_DELAY_SEC,
    PAUSE_FOR_CAPTCHA,
    PROXY_URL,
)
from urllib.parse import urlparse
from idealista_scraper.export import normalize_listing_link
from idealista_scraper.fetcher import fetch_html_with_retry, is_blocked_page
from idealista_scraper.parsers import (
    ListingCard,
    looks_like_listing_page,
    parse_detail_page,
    parse_search_page,
)


async def _run_with_fetcher(
    base_url: str,
    max_pages: int,
    fetch_details: bool,
    already_seen: set[str],
    on_record: Optional[Callable[[dict[str, Any]], None]],
    fetch_kwargs: dict[str, Any],
    on_restart_browser: Optional[Callable[[], Any]] = None,
) -> list[dict[str, Any]]:
    """Core run logic; fetch_kwargs are passed to every fetch_html_with_retry (e.g. page=page)."""
    log = logging.getLogger(__name__)
    all_cards: list[ListingCard] = []
    total_count = 0
    total_pages = 1

    # Page 1: long 200 = likely real content; block pages are usually short
    first_fetch_kwargs = {**fetch_kwargs, "pause_for_captcha": PAUSE_FOR_CAPTCHA}
    html, status = await fetch_html_with_retry(base_url + "/", **first_fetch_kwargs)
    long_ok = status == 200 and len(html) >= 12_000
    blocked = (
        status != 200
        or (not long_ok and is_blocked_page(html) and not looks_like_listing_page(html))
    )
    if blocked:
        raise RuntimeError(
            f"First page failed (status={status}) or blocked after retries. "
            "Idealista is blocking the request. Try: set HEADLESS=false in .env, use PROXY_URL (residential proxy), "
            "or run from another network. Run --live-test to verify."
        )
    total_count, page_cards = parse_search_page(html, base_url=IDEALISTA_DOMAIN)
    all_cards.extend(page_cards)
    log.info("Page 1: %s cards (total_count=%s)", len(page_cards), total_count)
    # Idealista shows "30" in the h1 on page 1 sometimes; use parsed total only when > 30.
    # Otherwise always try up to IDEALISTA_MAX_PAGE (60); pages 61+ redirect to page 1.
    if total_count > 30:
        total_pages = min(IDEALISTA_MAX_PAGE, max(1, math.ceil(total_count / 30)), max_pages)
    else:
        total_pages = min(IDEALISTA_MAX_PAGE, max_pages)
    first_page_first_link = (page_cards[0].link if page_cards else None)

    # When resuming (already_seen non-empty), start from the page after the last full page of 30
    # e.g. 238 existing -> start at page 8 so we don't re-fetch pages 2-7
    start_page = 1
    if already_seen and total_pages > 1:
        start_page = min(total_pages, (len(already_seen) // 30) + 1)
        if start_page > 1:
            log.info("Resuming from page %s (%s listings already in output).", start_page, len(already_seen))

    results: list[dict[str, Any]] = []
    processed_links: set[str] = set()

    def _dedupe_unique(cards: list[ListingCard]) -> list[ListingCard]:
        seen_links: set[str] = set()
        out: list[ListingCard] = []
        for c in cards:
            canonical = normalize_listing_link(c.link) if c.link else ""
            if not canonical or canonical in already_seen or canonical in seen_links:
                continue
            seen_links.add(canonical)
            out.append(c)
        return out

    async def _process_cards(cards_to_process: list[ListingCard]) -> None:
        for idx, card in enumerate(cards_to_process, 1):
            canonical_link = normalize_listing_link(card.link)
            if canonical_link in processed_links:
                continue
            processed_links.add(canonical_link)
            # Prefer canonical URL for fetch so we get consistent (Spanish) content
            fetch_url = canonical_link if canonical_link else card.link
            log.info("Fetching detail: %s", fetch_url[:70])
            html, status = await fetch_html_with_retry(
                fetch_url, delay_before=10, **fetch_kwargs
            )
            # Only skip detail when the request failed (non-200). Always parse when status=200 so we
            # extract whatever we can (block pages often still have JSON or partial HTML we can use).
            if status != 200:
                log.warning("Detail failed for %s (status=%s), saving card only.", fetch_url[:60], status)
                d = {**card.to_dict(), "link": canonical_link}
                if on_record:
                    on_record(d)
                results.append(d)
                continue
            detail = parse_detail_page(html, url=fetch_url)
            merged = {**card.to_dict(), "link": canonical_link, "detail": detail.to_dict()}
            detail_d = detail.to_dict()
            feats = (detail_d.get("features") or {})
            if feats.get("rooms"):
                try:
                    merged["rooms"] = int(feats["rooms"][0]) if feats["rooms"] else merged.get("rooms")
                except (ValueError, IndexError, TypeError):
                    pass
            if feats.get("sq_meters"):
                try:
                    merged["sq_meters"] = int(feats["sq_meters"][0]) if feats["sq_meters"] else merged.get("sq_meters")
                except (ValueError, IndexError, TypeError):
                    pass
            if detail_d.get("location"):
                merged["location"] = detail_d["location"]
            if on_record:
                on_record(merged)
            results.append(merged)

    if not fetch_details:
        unique_cards = _dedupe_unique(all_cards)
        for c in unique_cards:
            d = {**c.to_dict(), "link": normalize_listing_link(c.link)}
            if on_record:
                on_record(d)
            results.append(d)
        return results

    # Process page 1 cards only if we're not resuming from a later page
    if start_page <= 1:
        unique_so_far = _dedupe_unique(all_cards)
        to_process = [c for c in unique_so_far if normalize_listing_link(c.link) not in processed_links]
        if to_process:
            log.info("Processing %s listings from page 1 (fetching details and writing).", len(to_process))
            await _process_cards(to_process)

    # Pages 2..N (or start_page..N when resuming): optional delay, fetch, parse-first, retry once if blocked
    PAGE_BLOCK_RETRY_BACKOFF_SEC = 60
    CONSECUTIVE_BLOCKED_BEFORE_STOP = 2  # stop pagination after this many blocked pages (saves time)
    consecutive_blocked = 0
    for page_num in range(2, total_pages + 1):
        if page_num < start_page:
            continue  # skip already-done pages when resuming
        if PAGE_DELAY_SEC > 0:
            await asyncio.sleep(PAGE_DELAY_SEC)
        url = f"{base_url}/pagina-{page_num}.htm"
        html, status = await fetch_html_with_retry(url, **fetch_kwargs)
        if status != 200:
            log.warning("Page %s failed (status=%s), skipping.", page_num, status)
            consecutive_blocked = 0
            continue
        _, page_cards = parse_search_page(html, base_url=IDEALISTA_DOMAIN)
        if not page_cards and is_blocked_page(html):
            # Close browser and start fresh, then wait before retry (often unblocks)
            if on_restart_browser:
                try:
                    await asyncio.to_thread(on_restart_browser)
                    log.info("Restarted browser; waiting %ss before retry.", PAGE_BLOCK_RETRY_BACKOFF_SEC)
                except Exception as e:
                    log.warning("Browser restart failed: %s", e)
            else:
                log.info("Page %s looks blocked (0 cards), retrying once after %ss.", page_num, PAGE_BLOCK_RETRY_BACKOFF_SEC)
            await asyncio.sleep(PAGE_BLOCK_RETRY_BACKOFF_SEC)
            html, status = await fetch_html_with_retry(url, **fetch_kwargs)
            if status != 200:
                log.warning("Page %s failed on retry (status=%s), skipping.", page_num, status)
                consecutive_blocked = 0
                continue
            _, page_cards = parse_search_page(html, base_url=IDEALISTA_DOMAIN)
            if not page_cards and is_blocked_page(html):
                consecutive_blocked += 1
                log.warning(
                    "Page %s failed (status=200). Idealista has blocked access (this is a full block, not a captcha to solve).",
                    page_num,
                )
                if consecutive_blocked >= CONSECUTIVE_BLOCKED_BEFORE_STOP:
                    log.warning(
                        "Stopping pagination after %s consecutive blocked pages. To continue: use PROXY_URL (e.g. residential proxy), try a different network, or set HEADLESS=false and run in smaller batches.",
                        CONSECUTIVE_BLOCKED_BEFORE_STOP,
                    )
                    break
                continue
        if not page_cards:
            log.warning("Page %s returned 0 cards, skipping (continuing to next page).", page_num)
            continue
        consecutive_blocked = 0  # success: reset so we only stop after consecutive blocks
        log.info("Page %s: %s cards", page_num, len(page_cards))
        if first_page_first_link and page_cards[0].link == first_page_first_link:
            log.info("Page %s is duplicate of page 1 (redirect), stopping pagination.", page_num)
            break
        all_cards.extend(page_cards)
        unique_so_far = _dedupe_unique(all_cards)
        to_process = [c for c in unique_so_far if normalize_listing_link(c.link) not in processed_links]
        if to_process:
            log.info("Processing %s new listings from page %s (fetching details and writing).", len(to_process), page_num)
            await _process_cards(to_process)

    log.info("Done: %s total records written.", len(results))
    return results


async def run(
    base_url: str = IDEALISTA_BASE_URL,
    max_pages: Optional[int] = None,
    fetch_details: bool = False,
    seen_urls: Optional[set[str]] = None,
    on_record: Optional[Callable[[dict[str, Any]], None]] = None,
) -> list[dict[str, Any]]:
    """
    Scrape listing cards from search pages, optionally fetch each detail page.
    Deduplicates by link. If seen_urls is provided, skips cards whose link is in that set (resume).
    If on_record is provided, calls it with each record as soon as it is ready (incremental write).
    Reuses one Playwright browser for the whole run.
    Returns list of dicts (card to_dict, merged with detail if fetch_details) for this run.
    """
    max_pages = max_pages if max_pages is not None else MAX_PAGES
    base_url = base_url.rstrip("/")
    already_seen = seen_urls or set()

    approach = resolve_approach()

    if is_selenium_like(approach):
        import sys
        import threading
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options

        # When pausing for captcha, browser must be visible
        headless = HEADLESS and not PAUSE_FOR_CAPTCHA

        driver_lock = threading.Lock()
        driver = None
        attached = False
        if approach == "undetected":
            try:
                import re
                import undetected_chromedriver as uc
                # Avoid "OSError: [WinError 6] The handle is invalid" in Chrome.__del__ on Windows
                _uc_chrome_del = getattr(uc.Chrome, "__del__", None)
                if _uc_chrome_del and not getattr(uc.Chrome, "_safe_del_patched", False):
                    def _safe_del(self):
                        try:
                            _uc_chrome_del(self)
                        except OSError:
                            pass
                    uc.Chrome.__del__ = _safe_del
                    uc.Chrome._safe_del_patched = True
                driver = uc.Chrome(headless=headless, use_subprocess=True)
            except ImportError:
                print("undetected_chromedriver not installed. Run: pip install undetected-chromedriver", file=sys.stderr)
                approach = "selenium"
            except Exception as e:
                err = str(e)
                match = re.search(r"Current browser version is (\d+)", err, re.I)
                if match and ("version" in err.lower() or "chromedriver" in err.lower()):
                    try:
                        version_main = int(match.group(1))
                        driver = uc.Chrome(headless=headless, use_subprocess=True, version_main=version_main)
                    except Exception:
                        print(f"undetected_chromedriver failed: {e}. Falling back to Selenium.", file=sys.stderr)
                        approach = "selenium"
                else:
                    print(f"undetected_chromedriver failed: {e}. Falling back to Selenium.", file=sys.stderr)
                    approach = "selenium"

        if driver is None:
            opts = Options()
            if CHROME_CDP_URL:
                parsed = urlparse(CHROME_CDP_URL)
                host = parsed.hostname or "127.0.0.1"
                port = parsed.port or 9222
                addr = f"{host}:{port}"
                opts.add_experimental_option("debuggerAddress", addr)
                try:
                    driver = webdriver.Chrome(options=opts)
                    attached = True
                except Exception as e:
                    err = str(e).lower()
                    if "cannot connect" in err or "not reachable" in err or "session not created" in err:
                        print(
                            f"Could not connect to Chrome at {addr}. Starting a new browser instead.\n"
                            "To use your own Chrome: close it, then start with chrome.exe --remote-debugging-port=9222",
                            file=sys.stderr,
                        )
                        opts = Options()
                        opts.add_argument("--disable-blink-features=AutomationControlled")
                        opts.add_argument("--disable-infobars")
                        opts.add_argument("--no-first-run")
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
                opts.add_argument("--no-first-run")
                if headless:
                    opts.add_argument("--headless=new")
                opts.add_argument(
                    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                )
                if PROXY_URL:
                    opts.add_argument(f"--proxy-server={PROXY_URL}")
                driver = webdriver.Chrome(options=opts)

        fetch_kwargs = {"driver": driver, "approach": approach, "driver_lock": driver_lock}

        def _make_new_driver() -> Any:
            """Create a fresh Chrome driver (no CDP attach) for restart-after-block."""
            opts = Options()
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_argument("--disable-infobars")
            opts.add_argument("--no-first-run")
            if headless:
                opts.add_argument("--headless=new")
            opts.add_argument(
                "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            )
            if PROXY_URL:
                opts.add_argument(f"--proxy-server={PROXY_URL}")
            return webdriver.Chrome(options=opts)

        def restart_browser_sync() -> None:
            nonlocal driver
            if driver is not None:
                try:
                    driver.quit()
                except (OSError, Exception):
                    pass
                driver = None
            driver = _make_new_driver()
            fetch_kwargs["driver"] = driver

        try:
            return await _run_with_fetcher(
                base_url,
                max_pages,
                fetch_details,
                already_seen,
                on_record,
                fetch_kwargs,
                on_restart_browser=restart_browser_sync,
            )
        finally:
            if not attached and driver is not None:
                try:
                    driver.quit()
                except OSError:
                    pass
                except Exception:
                    logging.getLogger(__name__).debug("Driver quit failed", exc_info=True)
                driver = None

    # Playwright path (playwright or playwright_cdp)
    from playwright.async_api import async_playwright

    try:
        from playwright_stealth import stealth_async
    except ImportError:
        stealth_async = None

    async with async_playwright() as p:
        if approach == "playwright_cdp" and CHROME_CDP_URL:
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
            browser = await p.chromium.launch(headless=HEADLESS)
            viewports = (
                {"width": 1920, "height": 1080},
                {"width": 1536, "height": 864},
                {"width": 1440, "height": 900},
                {"width": 1366, "height": 768},
            )
            ctx_opts: dict = {
                "viewport": random.choice(viewports),
                "user_agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                ),
            }
            if PROXY_URL:
                ctx_opts["proxy"] = {"server": PROXY_URL}
            context = await browser.new_context(**ctx_opts)
            page = await context.new_page()
            if stealth_async:
                await stealth_async(page)
        try:
            return await _run_with_fetcher(
                base_url,
                max_pages,
                fetch_details,
                already_seen,
                on_record,
                {"page": page},
            )
        finally:
            await browser.close()
