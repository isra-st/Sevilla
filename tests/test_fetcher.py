"""Tests for fetcher (block detection, no real network in tests)."""
import pytest

from idealista_scraper.fetcher import is_blocked_page


def test_is_blocked_page_empty():
    assert is_blocked_page("") is True
    assert is_blocked_page("x" * 100) is True  # too short


def test_is_blocked_page_indicators():
    assert is_blocked_page("x" * 1000 + "Please enable JS and something") is True
    assert is_blocked_page("x" * 1000 + "enable JavaScript") is True
    assert is_blocked_page("x" * 1000 + "DataDome block") is True
    assert is_blocked_page("x" * 1000 + "CAPTCHA required") is True


def test_is_not_blocked_listing():
    html = "x" * 1000 + "<h1 id='h1-container'>Venta de viviendas: 500</h1><section class='items-list'>"
    assert is_blocked_page(html) is False
