# Fixtures for Idealista scraper tests

- `search_page.html` – One search result page (Sevilla venta). Used by `parse_search_page` tests.
- `detail_page.html` – One property detail page. Used by `parse_detail_page` tests.

These are minimal HTML snippets that match the selectors in `idealista_scraper/selectors.py`. For more realistic tests, replace with real HTML saved from a browser (Save Page As) after visiting:

- Search: https://www.idealista.com/venta-viviendas/sevilla-sevilla/
- Detail: any listing link from the search results.
