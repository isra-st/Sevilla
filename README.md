# Idealista Sevilla Scraper

Stealthy web scraper for [Idealista](https://www.idealista.com/venta-viviendas/sevilla-sevilla/) selling apartments in Sevilla. Uses **Playwright** or **Selenium + ChromeDriver** (one browser per run), with anti-detection (stealth/delays), testable parsers, and optional detail-page scraping.

## Setup

```bash
cd idealista-scraper
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
playwright install chromium   # only if using Playwright (default)
```

If you use **Selenium** (`USE_SELENIUM=true` in `.env`), you don’t need `playwright install`; Selenium 4 will download ChromeDriver automatically when you run the scraper.

## Config

Copy `.env.example` to `.env` and set:

- `IDEALISTA_BASE_URL` – default: Sevilla venta URL
- `DELAY_MIN`, `DELAY_MAX` – seconds between requests (default 8–20). Lower = faster, higher block risk.
- `MAX_PAGES` – max search pages to scrape (default 60)
- `HEADLESS=false` – run browser visible; can reduce blocking
- `SCRAPER_APPROACH` – which technique to use: `undetected` (best anti-detection), `selenium`, `playwright`, or `playwright_cdp`. Run `--test-approaches` to try each and see which works.
- `USE_SELENIUM=true` – use Selenium (same as `SCRAPER_APPROACH=selenium`).
- `CHROME_CDP_URL=http://localhost:9222` – **attach to your existing Chrome**. See “Use your own browser” below.
- `PAUSE_FOR_CAPTCHA=true` – after loading the first page, pause so you can **solve the DataDome captcha** in the browser; then press Enter to continue. Idealista often shows captcha on first visit; solving it once usually lets the rest of the session through (see [ScrapingBee’s Idealista tutorial](https://www.scrapingbee.com/blog/web-scraping-idealista/)).
- `PROXY_URL` – optional proxy (e.g. `http://user:pass@host:port`). For rotating residential proxies (e.g. [ScrapingBee](https://www.scrapingbee.com)) use their proxy URL; with Selenium you may need `selenium-wire` for authenticated proxies.

## Run

- **Listings only (fast):**  
  `python -m idealista_scraper.cli --max-pages 2 --output listings.json`

- **With detail pages (CSV, one row per listing):**  
  `python -m idealista_scraper.cli --max-pages 60 --fetch-details --output pisos_sevilla.csv`  
  Rows are written as they are scraped. The script retries failed pages/details and only stops if the **first page** fails after retries (block or network down). If it stops, run the same command again: it skips listings already in the CSV and appends only new ones. To **start from scratch** (ignore existing CSV and overwrite it), add `--no-resume`.

- **Live test (single page):**  
  `python -m idealista_scraper.cli --live-test`

- **Test all approaches (find one that works):**  
  `python -m idealista_scraper.cli --test-approaches`  
  Tries `undetected`, `selenium`, `playwright`, and `playwright_cdp` in turn and reports which got a valid listing page. Then set `SCRAPER_APPROACH=<name>` in `.env` for the one that passed.

## DataDome / captcha (Idealista blocks bots)

Idealista uses **DataDome** and often shows a captcha on the first visit. Options that work in practice:

1. **Pause and solve manually** – Set `PAUSE_FOR_CAPTCHA=true` in `.env`. Run the scraper (or `--test-approaches`); when the browser opens and loads the page, solve the captcha in the window, then press **Enter** in the terminal. The script continues and later requests in the same session usually don’t get captcha again.
2. **Your own Chrome** – Attach to Chrome started with `--remote-debugging-port=9222` (see below). Your existing session/cookies often avoid the captcha.
3. **Residential proxy** – Use a service that provides rotating residential IPs (e.g. ScrapingBee premium proxy) and set `PROXY_URL` to their endpoint.
4. **Visible browser** – `HEADLESS=false` sometimes helps.

This matches the approach described in [How to scrape data from Idealista (ScrapingBee)](https://www.scrapingbee.com/blog/web-scraping-idealista/): undetected_chromedriver + optional pause for captcha + optional proxy.

## Use your own browser (recommended to avoid blocks)

The script can **attach to your existing Chrome** so it uses your session, cookies and profile – Idealista sees a normal user. Do this when the live test fails or you get 403.

1. **Close Chrome completely** (all windows).
2. **Start Chrome with remote debugging** (PowerShell, or create a shortcut):
   ```powershell
   & "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
   ```
   On Mac/Linux: `google-chrome --remote-debugging-port=9222` (or your Chrome path).
3. In that Chrome window, **open Idealista** once (e.g. the Sevilla venta search) and confirm the list loads. Then leave that window open.
4. In `.env` set:
   ```
   USE_SELENIUM=true
   CHROME_CDP_URL=http://localhost:9222
   ```
5. Run: `python -m idealista_scraper.cli --live-test` then your full scrape. The script will **control this Chrome** (you’ll see new tabs open). It does not close your browser when finished.

If you prefer Playwright instead of Selenium, use the same steps but **do not** set `USE_SELENIUM` (or set it to `false`); only set `CHROME_CDP_URL=http://localhost:9222`. Playwright will connect to the same Chrome.

## Troubleshooting

**`ECONNREFUSED` on port 9222** – Chrome isn’t running with `--remote-debugging-port=9222`. Follow “Use your own browser” above (steps 1–2).

**403 (blocked)** – Idealista is blocking the automated browser. Use your own browser (see above). Otherwise try: `HEADLESS=false`, or `PROXY_URL`, or another network. Check with: `python -m idealista_scraper.cli --live-test`.

**"Exception ignored in: Chrome.__del__" / WinError 6** – Harmless on Windows when using undetected_chromedriver. You can ignore it; the scrape result is still valid.

**"ChromeDriver only supports Chrome version X / Current browser version is Y"** – The script will retry with your Chrome version (e.g. 145). If it still fails, update Chrome to the latest or set `SCRAPER_APPROACH=selenium` and use your browser with `CHROME_CDP_URL` (see above).

**"Se ha detectado un uso indebido. El acceso se ha bloqueado"** – Idealista has blocked the automated browser or your IP. Use **undetected** (script now pins ChromeDriver to your Chrome version so it doesn’t fall back to Selenium). If it still happens: wait a few hours, try from another network, or use a residential proxy (`PROXY_URL`). Opening Idealista in a normal browser still works; the block applies to the automated session.

## Tests

Uses saved HTML fixtures (no network). Add your own fixtures under `tests/fixtures/` if needed.

```bash
pytest tests/ -v
```

## CSV output (structured)

The CSV has a fixed column order and is safe to open in Excel (all text quoted). Columns: `title`, `link`, `price_eur`, `price_display`, `currency`, `rooms`, `sq_meters`, `location`, `tags`, `seller`, `seller_url`, `description`, `listing_type`, then detail fields (`detail_title`, `detail_location`, etc.). Prices appear as numbers in `price_eur` and readable in `price_display` (e.g. `1.700.000 €`).
