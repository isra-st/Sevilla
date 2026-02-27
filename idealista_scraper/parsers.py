"""Parse Idealista search and detail HTML. All selectors live in selectors.py."""
import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from parsel import Selector

from idealista_scraper.selectors import (
    CARD_CURRENCY,
    CARD_DESCRIPTION,
    CARD_DETAILS,
    CARD_DETAILS_ALT,
    CARD_IS_AD,
    CARD_LINK,
    CARD_LINK_FALLBACK,
    CARD_PRICE,
    CARD_SELLER_HREF,
    CARD_SELLER_TITLE,
    CARD_TAGS,
    CARD_TITLE,
    CARDS,
    CARDS_FALLBACK_ARTICLE,
    CARDS_FALLBACK_LINKS,
    DETAIL_DESCRIPTION,
    DETAIL_DESCRIPTION_ALT,
    DETAIL_DESCRIPTION_ALT2,
    DETAIL_DESCRIPTION_ALT3,
    DETAIL_DESCRIPTION_ALT4,
    DETAIL_DESCRIPTION_FALLBACK,
    DETAIL_FEATURE_HEADERS,
    DETAIL_FEATURE_HEADERS_ALT,
    DETAIL_FEATURE_HEADERS_ALT2,
    DETAIL_FEATURE_ITEMS,
    DETAIL_FEATURE_ITEMS_ALT,
    DETAIL_IMAGES_REGEX,
    DETAIL_IMAGES_REGEX_ALT,
    DETAIL_INFO_FEATURES,
    DETAIL_INFO_FEATURES_ALT,
    DETAIL_LOCATION,
    DETAIL_LOCATION_FALLBACK,
    DETAIL_PICTURE,
    DETAIL_PICTURE_ALT,
    DETAIL_PICTURE_ALT2,
    DETAIL_PICTURE_ALT3,
    DETAIL_PRICE_NODE,
    DETAIL_PRICE_SPAN,
    DETAIL_PROPERTY_FEATURE_ONE,
    DETAIL_PROPERTY_FEATURE_ONE_ALT,
    DETAIL_PROPERTY_FEATURE_THREE,
    DETAIL_PROPERTY_FEATURE_THREE_ALT,
    DETAIL_PROPERTY_FEATURE_TWO,
    DETAIL_PROPERTY_FEATURE_TWO_ALT,
    DETAIL_TITLE,
    DETAIL_TITLE_FALLBACK,
    DETAIL_UPDATED,
    DETAIL_UPDATED_ALT,
    DETAIL_UPDATED_ALT2,
    H1_TOTAL,
    TOTAL_REGEX,
)


def _normalize_price(price_text: str | None) -> int | None:
    if not price_text:
        return None
    digits = re.sub(r"[^\d]", "", price_text.strip())
    return int(digits) if digits else None


def _parse_rooms(s: str) -> int | None:
    if not s:
        return None
    s = s.strip()
    # "5 habitaciones", "2 hab.", "3 dormitorios", "4 beds"
    m = re.search(r"(\d+)\s*(?:hab\.?|habitacion(?:es)?|dormitorio(?:s)?|bed(?:s)?|room(?:s)?)", s, re.I)
    return int(m.group(1)) if m else None


def _parse_sq_meters(s: str) -> int | None:
    if not s:
        return None
    s = s.strip()
    # "311 m²", "69 m² construidos", "111 m² construidos, 84 m² útiles" -> take first number
    m = re.search(r"(\d+)\s*m²?", s, re.I)
    return int(m.group(1)) if m else None


def _extract_details_rooms_m2(detail_texts: list[str]) -> tuple[int | None, int | None]:
    rooms, sq_m = None, None
    for s in detail_texts:
        if not s:
            continue
        if rooms is None:
            rooms = _parse_rooms(s)
        if sq_m is None:
            sq_m = _parse_sq_meters(s)
    return rooms, sq_m


def _location_from_title(title: str) -> str:
    """Extract location from card title, e.g. 'Piso en San Vicente, Sevilla' -> 'San Vicente, Sevilla'."""
    if not title or not title.strip():
        return ""
    t = title.strip()
    # "Piso en X, Sevilla" or "Casa en Arenal - Museo - Tetuán, Sevilla" -> part after " en "
    if " en " in t:
        after_en = t.split(" en ", 1)[-1].strip()
        if after_en:
            return after_en
    # "X - Centro, Sevilla" -> part after last " - " often is location
    if " - " in t:
        return t.split(" - ", 1)[-1].strip()
    return ""


def _extract_description_from_script(html: str) -> str:
    """Try to extract property description from JSON inside script tags (Idealista sometimes embeds data)."""
    if not html:
        return ""
    # Match "adDescription":"...", "description":"..." or similar (handle escaped quotes)
    for pattern in (
        r'"adDescription"\s*:\s*"((?:[^"\\]|\\.)*)"',
        r'"description"\s*:\s*"((?:[^"\\]|\\.)*)"',
        r"'adDescription'\s*:\s*'((?:[^'\\]|\\.)*)'",
    ):
        match = re.search(pattern, html, re.DOTALL)
        if match:
            raw = match.group(1)
            try:
                return raw.encode().decode("unicode_escape")
            except Exception:
                return raw.replace("\\n", "\n").replace("\\/", "/")
    return ""


def _extract_updated_from_script(html: str) -> str:
    """Try to extract last-updated date from JSON in script tags."""
    if not html:
        return ""
    for pattern in (
        r'"lastUpdate"\s*:\s*"([^"]+)"',
        r'"updatedDate"\s*:\s*"([^"]+)"',
        r'"dateUpdated"\s*:\s*"([^"]+)"',
        r'"actualizado"\s*:\s*"([^"]+)"',
    ):
        match = re.search(pattern, html)
        if match:
            return match.group(1).strip()
    return ""


@dataclass
class ListingCard:
    """One listing from search results."""
    listing_type: str = "venta"
    title: str = ""
    link: str = ""
    price: int | None = None
    currency: str = "€"
    rooms: int | None = None
    sq_meters: int | None = None
    location: str = ""  # often only on detail; card may have in title
    description: str = ""
    tags: list[str] = field(default_factory=list)
    seller: str | None = None
    seller_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "listing_type": self.listing_type,
            "title": self.title,
            "link": self.link,
            "price": self.price,
            "currency": self.currency,
            "rooms": self.rooms,
            "sq_meters": self.sq_meters,
            "location": self.location,
            "description": self.description,
            "tags": self.tags,
            "seller": self.seller,
            "seller_url": self.seller_url,
        }


@dataclass
class DetailListing:
    """Full listing from detail page."""
    url: str = ""
    title: str = ""
    location: str = ""
    price: int | None = None
    currency: str = "€"
    description: str = ""
    updated: str = ""
    features: dict[str, list[str]] = field(default_factory=dict)
    images: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "location": self.location,
            "price": self.price,
            "currency": self.currency,
            "description": self.description,
            "updated": self.updated,
            "features": self.features,
            "images": self.images,
        }


def parse_search_page(
    html: str,
    base_url: str = "https://www.idealista.com",
) -> tuple[int, list[ListingCard]]:
    """
    Parse a search results page. Returns (total_count, list of listing cards).
    Skips ad cards (adv_txt). Link hrefs are normalized with base_url.
    """
    sel = Selector(text=html)
    total_count = 0
    raw = sel.css(H1_TOTAL).re(TOTAL_REGEX)
    if raw:
        total_count = int(re.sub(r"[^\d]", "", raw[0]) or "0")

    cards: list[ListingCard] = []
    for box in sel.xpath(CARDS):
        if box.xpath(CARD_IS_AD).get():
            continue
        title = (box.xpath(CARD_TITLE).get() or "").strip()
        href = (box.xpath(CARD_LINK).get() or box.xpath(CARD_LINK_FALLBACK).get() or "").strip()
        if not href:
            continue
        link = href if href.startswith("http") else (base_url.rstrip("/") + href)
        price_text = (box.xpath(CARD_PRICE).get() or "").strip()
        price = _normalize_price(price_text)
        currency = (box.xpath(CARD_CURRENCY).get() or "€").strip()
        detail_texts = [t.strip() for t in box.xpath(CARD_DETAILS).getall() if t]
        if not detail_texts:
            detail_texts = [t.strip() for t in box.xpath(CARD_DETAILS_ALT).getall() if t]
        rooms, sq_m = _extract_details_rooms_m2(detail_texts)
        location = _location_from_title(title)
        desc_node = box.xpath(CARD_DESCRIPTION).get()
        description = (desc_node or "").replace("\n", " ").strip()
        tags = [t.strip() for t in box.xpath(CARD_TAGS).getall() if t]
        seller = (box.xpath(CARD_SELLER_TITLE).get() or "").strip() or None
        seller_href = (box.xpath(CARD_SELLER_HREF).get() or "").strip()
        seller_url = (base_url.rstrip("/") + seller_href) if seller_href and not seller_href.startswith("http") else (seller_href or None)

        cards.append(
            ListingCard(
                title=title,
                link=link,
                price=price,
                currency=currency,
                rooms=rooms,
                sq_meters=sq_m,
                location=location,
                description=description,
                tags=tags,
                seller=seller,
                seller_url=seller_url,
            )
        )

    # Fallback if main selector returns 0 (site structure may have changed)
    if not cards:
        for box in sel.xpath(CARDS_FALLBACK_ARTICLE):
            if box.xpath(CARD_IS_AD).get():
                continue
            href = (box.xpath(CARD_LINK).get() or box.xpath(CARD_LINK_FALLBACK).get() or "").strip()
            if not href:
                continue
            link = href if href.startswith("http") else (base_url.rstrip("/") + href)
            title = (box.xpath(CARD_TITLE).get() or "").strip()
            price_text = (box.xpath(CARD_PRICE).get() or "").strip()
            price = _normalize_price(price_text)
            detail_texts = [t.strip() for t in box.xpath(CARD_DETAILS).getall() if t]
            if not detail_texts:
                detail_texts = [t.strip() for t in box.xpath(CARD_DETAILS_ALT).getall() if t]
            rooms, sq_m = _extract_details_rooms_m2(detail_texts)
            location = _location_from_title(title)
            cards.append(
                ListingCard(
                    title=title,
                    link=link,
                    price=price,
                    currency=(box.xpath(CARD_CURRENCY).get() or "€").strip(),
                    rooms=rooms,
                    sq_meters=sq_m,
                    location=location,
                    description=(box.xpath(CARD_DESCRIPTION).get() or "").replace("\n", " ").strip(),
                )
            )
    if not cards:
        seen_links: set[str] = set()
        for link_el in sel.xpath(CARDS_FALLBACK_LINKS):
            href = (link_el.xpath("@href").get() or "").strip()
            if not href or "/inmueble/" not in href:
                continue
            link = href if href.startswith("http") else (base_url.rstrip("/") + href)
            if link in seen_links:
                continue
            seen_links.add(link)
            title = (link_el.xpath("@title").get() or link_el.xpath("text()").get() or "").strip()
            cards.append(
                ListingCard(
                    link=link,
                    title=title or link,
                    location=_location_from_title(title or link),
                )
            )

    return total_count, cards


def looks_like_listing_page(html: str, base_url: str = "https://www.idealista.com") -> bool:
    """
    True if the HTML looks like a valid search listing page (has total count, listing cards,
    or /inmueble/ links). Avoids false-positive block when the page contains words like 'challenge'.
    """
    try:
        total_count, cards = parse_search_page(html, base_url=base_url)
        if total_count > 0 or len(cards) > 0:
            return True
    except Exception:
        pass
    # Fallback even when parse fails or returns empty: page has listing links or clear Idealista content
    if "/inmueble/" in html and "idealista.com" in html:
        return True
    if len(html) > 5000 and "idealista" in html.lower() and ("items-list" in html or "item-info-container" in html):
        return True
    return False


def parse_detail_page(html: str, url: str = "") -> DetailListing:
    """
    Parse a property detail page. Returns DetailListing.
    Uses .main-info__title, .info-features, .details-property, first picture; images from JS when present.
    """
    sel = Selector(text=html)
    css = lambda x: (sel.css(x).get() or "").strip()
    css_all = lambda x: [t.strip() for t in sel.css(x).getall() if t]

    title = css(DETAIL_TITLE) or css(DETAIL_TITLE_FALLBACK)
    location = css(DETAIL_LOCATION) or css(DETAIL_LOCATION_FALLBACK)
    price_node_text = (sel.css(DETAIL_PRICE_SPAN).get() or sel.css(DETAIL_PRICE_NODE).xpath("text()").get() or "").strip()
    price = _normalize_price(price_node_text)
    currency = (sel.css(DETAIL_PRICE_NODE).xpath("span/text()").get() or "€").strip()
    description = "\n".join(
        css_all(DETAIL_DESCRIPTION)
        or css_all(DETAIL_DESCRIPTION_FALLBACK)
        or css_all(DETAIL_DESCRIPTION_ALT)
        or css_all(DETAIL_DESCRIPTION_ALT2)
        or css_all(DETAIL_DESCRIPTION_ALT3)
        or css_all(DETAIL_DESCRIPTION_ALT4)
    ).strip()
    if not description:
        description = _extract_description_from_script(html)

    updated_raw = (
        sel.xpath(DETAIL_UPDATED).get()
        or sel.xpath(DETAIL_UPDATED_ALT).get()
        or ""
    )
    if not updated_raw:
        for node in sel.xpath(DETAIL_UPDATED_ALT2):
            t = (node.get() or "").strip()
            if t and ("Actualizado" in t or "updated" in t.lower()):
                updated_raw = t
                break
    updated = ""
    if updated_raw:
        if " on " in updated_raw:
            updated = updated_raw.split(" on ")[-1].strip()
        elif "Actualizado" in updated_raw or "actualizado" in updated_raw:
            updated = re.sub(r"^.*?(\d.*)$", r"\1", updated_raw).strip()
        else:
            updated = updated_raw.strip()
    if not updated:
        updated = _extract_updated_from_script(html)

    # Main features: .info-features span (1=sq m, 2=rooms, 3=feature)
    feature_spans = css_all(DETAIL_INFO_FEATURES) or css_all(DETAIL_INFO_FEATURES_ALT)
    rooms, sq_m = None, None
    if len(feature_spans) >= 1:
        sq_m = _parse_sq_meters(feature_spans[0])
    if len(feature_spans) >= 2:
        rooms = _parse_rooms(feature_spans[1])

    features: dict[str, list[str]] = {}
    header_selectors = [
        ("css", DETAIL_FEATURE_HEADERS),
        ("xpath", DETAIL_FEATURE_HEADERS_ALT),
        ("css", DETAIL_FEATURE_HEADERS_ALT2),
    ]
    for kind, selector in header_selectors:
        if kind == "css":
            headers = sel.css(selector)
        else:
            headers = sel.xpath(selector)
        for header in headers:
            label = (header.xpath("text()").get() or "").strip()
            if not label:
                continue
            items = header.xpath(DETAIL_FEATURE_ITEMS)
            if not items:
                items = header.xpath(DETAIL_FEATURE_ITEMS_ALT)
            texts = ["".join(node.xpath(".//text()").getall()).strip() for node in items]
            if texts and label not in features:
                features[label] = texts
        if features:
            break
    # Details property sections (feature-one, feature-two, feature-three) – full div text
    for key, selector, selector_alt in (
        ("details_property_one", DETAIL_PROPERTY_FEATURE_ONE, DETAIL_PROPERTY_FEATURE_ONE_ALT),
        ("details_property_two", DETAIL_PROPERTY_FEATURE_TWO, DETAIL_PROPERTY_FEATURE_TWO_ALT),
        ("details_property_three", DETAIL_PROPERTY_FEATURE_THREE, DETAIL_PROPERTY_FEATURE_THREE_ALT),
    ):
        for sel_desc in (selector + " ::text", selector_alt + " ::text"):
            parts = sel.css(sel_desc).getall()
            combined = " ".join(t.strip() for t in parts if t and t.strip()).strip()
            if combined:
                features[key] = [combined]
                break
    # Fallback: extract rooms and sq_m from any feature text (e.g. "5 habitaciones", "311 m²")
    for _label, items in features.items():
        for text in items:
            if not text:
                continue
            if rooms is None:
                rooms = _parse_rooms(text)
            if sq_m is None:
                sq_m = _parse_sq_meters(text)
            if rooms is not None and sq_m is not None:
                break
        if rooms is not None and sq_m is not None:
            break
    if len(feature_spans) >= 3 and feature_spans[2].strip():
        features["info_feature_3"] = [feature_spans[2].strip()]
    if rooms is not None:
        features["rooms"] = [str(rooms)]
    if sq_m is not None:
        features["sq_meters"] = [str(sq_m)]

    images: list[str] = []
    base = "https://www.idealista.com"
    if url and url.startswith("http"):
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
    for picture_sel in (DETAIL_PICTURE, DETAIL_PICTURE_ALT, DETAIL_PICTURE_ALT2, DETAIL_PICTURE_ALT3):
        first_img = (sel.css(picture_sel).get() or "").strip()
        if first_img:
            images.append(first_img if first_img.startswith("http") else (base + first_img))
            break
    for regex in (DETAIL_IMAGES_REGEX, DETAIL_IMAGES_REGEX_ALT):
        match = re.search(regex, html, re.DOTALL)
        if match:
            try:
                raw_json = match.group(1)
                raw_json = re.sub(r"(\w+):", r'"\1":', raw_json)
                arr = json.loads(raw_json)
                for item in arr:
                    if isinstance(item, dict) and "imageUrl" in item:
                        path = item["imageUrl"]
                        u = path if path.startswith("http") else (base + path)
                        if u not in images:
                            images.append(u)
                if images:
                    break
            except (json.JSONDecodeError, IndexError, KeyError):
                continue

    return DetailListing(
        url=url,
        title=title,
        location=location,
        price=price,
        currency=currency,
        description=description,
        updated=updated,
        features=features,
        images=images,
    )
