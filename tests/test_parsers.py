"""Unit tests for parsers using saved HTML fixtures (no network)."""
from pathlib import Path

import pytest

from idealista_scraper.parsers import (
    DetailListing,
    ListingCard,
    parse_detail_page,
    parse_search_page,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_parse_search_page_fixture():
    html = (FIXTURES_DIR / "search_page.html").read_text(encoding="utf-8")
    total, cards = parse_search_page(html, base_url="https://www.idealista.com")
    assert total == 1234
    assert len(cards) == 2  # third article is ad, skipped
    c0 = cards[0]
    assert "Sierpes" in c0.title
    assert c0.link.startswith("https://www.idealista.com") and "94156485" in c0.link
    assert c0.price == 185_000
    assert c0.currency == "€"
    assert c0.rooms == 3
    assert c0.sq_meters == 85
    assert "Terrace" in c0.tags
    assert c0.seller == "Agency One"
    c1 = cards[1]
    assert c1.price == 320_000
    assert c1.rooms == 4
    assert c1.sq_meters == 120


def test_parse_search_page_schema():
    html = (FIXTURES_DIR / "search_page.html").read_text(encoding="utf-8")
    _, cards = parse_search_page(html)
    for card in cards:
        d = card.to_dict()
        assert "title" in d and "link" in d and "price" in d
        assert "idealista.com" in d["link"]
        assert isinstance(d.get("price"), (int, type(None)))
        assert isinstance(d.get("tags"), list)


def test_parse_detail_page_fixture():
    html = (FIXTURES_DIR / "detail_page.html").read_text(encoding="utf-8")
    url = "https://www.idealista.com/inmueble/94156485/"
    detail = parse_detail_page(html, url=url)
    assert isinstance(detail, DetailListing)
    assert "Sierpes" in detail.title
    assert "Centro" in detail.location
    assert detail.price == 185_000
    assert "Bright apartment" in detail.description
    assert "January" in detail.updated or "2025" in detail.updated
    assert "Basic features" in detail.features
    assert "85 m² built" in detail.features["Basic features"]
    assert "3 bedrooms" in detail.features["Basic features"]
    assert len(detail.images) >= 1
    assert any("foto" in i for i in detail.images)


def test_parse_detail_page_schema():
    html = (FIXTURES_DIR / "detail_page.html").read_text(encoding="utf-8")
    detail = parse_detail_page(html, url="https://www.idealista.com/inmueble/1/")
    d = detail.to_dict()
    assert "url" in d and "title" in d and "price" in d
    assert "features" in d and isinstance(d["features"], dict)
    assert "images" in d and isinstance(d["images"], list)
