"""
CLI: run scraper, export to JSON/CSV, or run single-URL live test.
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

from idealista_scraper.config import IDEALISTA_BASE_URL, MAX_PAGES, PAUSE_FOR_CAPTCHA
from idealista_scraper.export import (
    append_csv_row,
    export_csv,
    export_json,
    get_existing_links_from_csv,
    validate_schema,
    write_csv_header,
)
from idealista_scraper.approaches import APPROACHES
from idealista_scraper.fetcher import fetch_html, is_blocked_page
from idealista_scraper.parsers import looks_like_listing_page
from idealista_scraper.orchestrator import run


def _main() -> None:
    parser = argparse.ArgumentParser(description="Idealista Sevilla selling apartments scraper")
    parser.add_argument(
        "--base-url",
        default=IDEALISTA_BASE_URL,
        help="Base search URL (default: Sevilla venta)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help=f"Max search pages to scrape (default: env MAX_PAGES or {MAX_PAGES})",
    )
    parser.add_argument(
        "--fetch-details",
        action="store_true",
        help="Fetch each listing detail page (slower)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Output path (JSON or CSV by extension). If omitted, print JSON to stdout.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate each record with Pydantic schema before export",
    )
    parser.add_argument(
        "--live-test",
        action="store_true",
        help="Fetch a single page and check for block (no full scrape)",
    )
    parser.add_argument(
        "--test-approaches",
        action="store_true",
        help="Try each scraper approach (undetected, selenium, playwright, playwright_cdp) and report which works",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="For CSV output: ignore existing file and start from scratch (overwrites output file)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show progress (page and detail counts)",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.live_test:
        asyncio.run(_live_test(args.base_url))
        return

    if args.test_approaches:
        asyncio.run(_test_approaches(args.base_url))
        return

    path = Path(args.output) if args.output else None
    use_csv_incremental = path is not None and path.suffix.lower() == ".csv"

    if use_csv_incremental:
        # Resolve path so we always write to the same file (cwd-independent)
        path = path.resolve()
        # Resume: skip listings already in the CSV (unless --no-resume)
        if args.no_resume:
            existing_links = set()
            write_csv_header(path)  # start fresh: header only, rows appended as we go
            print("Starting from scratch (--no-resume): output file cleared, writing rows as they are ready.", file=sys.stderr)
        else:
            existing_links = get_existing_links_from_csv(path)
            if existing_links:
                print(f"Resuming: skipping {len(existing_links)} listings already in {path}", file=sys.stderr)

        _records_written = [0]  # use list so closure can mutate

        def on_record(record: dict) -> None:
            r = validate_schema(record) if args.validate else record
            try:
                append_csv_row(r, path)
                _records_written[0] += 1
                if args.verbose and _records_written[0] <= 3:
                    print(f"  Wrote record {_records_written[0]} to {path.name}", file=sys.stderr)
            except Exception as e:
                print(f"Error writing record to CSV: {e}", file=sys.stderr)
                raise

        data = asyncio.run(
            run(
                base_url=args.base_url,
                max_pages=args.max_pages,
                fetch_details=args.fetch_details,
                seen_urls=existing_links,
                on_record=on_record,
            )
        )

        print(f"Wrote {len(data)} records to {path}", file=sys.stderr)
        if len(data) == 0 and args.fetch_details:
            print(
                "Tip: run with -v to see page and detail counts (e.g. whether any cards were parsed).",
                file=sys.stderr,
            )
    else:
        data = asyncio.run(
            run(
                base_url=args.base_url,
                max_pages=args.max_pages,
                fetch_details=args.fetch_details,
            )
        )
        if args.validate:
            try:
                data = [validate_schema(r) for r in data]
            except Exception as e:
                print(f"Validation error: {e}", file=sys.stderr)
                sys.exit(1)
        if args.output:
            path = Path(args.output)
            if path.suffix.lower() == ".csv":
                export_csv(data, path)
            else:
                export_json(data, path)
            print(f"Wrote {len(data)} records to {path}", file=sys.stderr)
        else:
            import json
            print(json.dumps(data, indent=2, ensure_ascii=False))


# Long 200 response is likely real content; block pages are usually short
_MIN_HTML_LENGTH_NOT_BLOCKED = 12_000


async def _test_approaches(base_url: str) -> None:
    """Try each scraper approach and report which one(s) get a valid listing page."""
    url = base_url.rstrip("/") + "/"
    print(f"Testing scraper approaches on {url}", file=sys.stderr)
    if PAUSE_FOR_CAPTCHA:
        print("PAUSE_FOR_CAPTCHA is set: you will be prompted to solve captcha on the first approach.", file=sys.stderr)
    print("", file=sys.stderr)

    results = []
    for i, approach in enumerate(APPROACHES):
        pause = PAUSE_FOR_CAPTCHA and (i == 0)
        try:
            html, status = await fetch_html(url, approach=approach, pause_for_captcha=pause)
        except Exception as e:
            print(f"  {approach}: ERROR – {e}", file=sys.stderr)
            results.append((approach, False, "error", 0))
            continue
        long_ok = status == 200 and len(html) >= _MIN_HTML_LENGTH_NOT_BLOCKED
        looks_ok = looks_like_listing_page(html)
        blocked = is_blocked_page(html) and not looks_ok
        ok = status == 200 and (long_ok or not blocked)
        results.append((approach, ok, status, len(html)))
        status_str = "OK" if ok else "FAIL"
        print(f"  {approach}: {status_str} (status={status}, len={len(html)}, blocked={blocked})", file=sys.stderr)

    print("", file=sys.stderr)
    passed = [a for a, ok, _, _ in results if ok]
    if passed:
        print(f"Working approach(es): {', '.join(passed)}", file=sys.stderr)
        print(f"Set in .env: SCRAPER_APPROACH={passed[0]}", file=sys.stderr)
    else:
        print(
            "No approach succeeded. Idealista uses DataDome and often shows captcha on first visit.\n"
            "Try: 1) PAUSE_FOR_CAPTCHA=true in .env, then run again and solve the captcha when prompted.\n"
            "     2) HEADLESS=false 3) Your Chrome with --remote-debugging-port=9222 4) PROXY_URL (e.g. ScrapingBee).",
            file=sys.stderr,
        )
        sys.exit(1)


async def _live_test(base_url: str) -> None:
    url = base_url.rstrip("/") + "/"
    print(f"Live test: fetching {url} ...", file=sys.stderr)
    html, status = await fetch_html(url, pause_for_captcha=PAUSE_FOR_CAPTCHA)
    # Treat long 200 response as success (real listing pages are large)
    long_ok = status == 200 and len(html) >= _MIN_HTML_LENGTH_NOT_BLOCKED
    blocked = (
        not long_ok
        and status == 200
        and is_blocked_page(html)
        and not looks_like_listing_page(html)
    )
    if status == 200 and (long_ok or not blocked):
        print("OK: Got 200 and content looks like listing (not blocked).", file=sys.stderr)
    else:
        print(
            f"FAIL: status={status}, blocked={blocked}. "
            "Try: set HEADLESS=false in .env, or use your Chrome: close it, then start with "
            "chrome.exe --remote-debugging-port=9222 and run again.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    _main()
