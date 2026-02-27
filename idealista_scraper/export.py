"""Export listings to JSON/CSV with optional schema validation."""
import csv
import json
import re
from pathlib import Path
from typing import Any

try:
    from pydantic import BaseModel, Field
    PYDANTIC = True
except ImportError:
    PYDANTIC = False

# Canonical column order: key fields first, then detail. Same for new file and append.
CSV_COLUMNS = [
    "title",
    "link",
    "price_eur",
    "price_display",
    "currency",
    "rooms",
    "sq_meters",
    "location",
    "tags",
    "seller",
    "seller_url",
    "description",
    "listing_type",
    "detail_title",
    "detail_location",
    "detail_price",
    "detail_description",
    "detail_updated",
    "detail_features",
    "detail_images",
]


def _safe_str(v: Any) -> str:
    """One-line string, no newlines (keeps CSV columns aligned)."""
    if v is None:
        return ""
    s = str(v).strip()
    return re.sub(r"[\r\n]+", " ", s)


def _flatten_for_csv(record: dict[str, Any]) -> dict[str, Any]:
    """Build one row with canonical columns. Adds price_eur/price_display, flattens detail."""
    out: dict[str, str] = {col: "" for col in CSV_COLUMNS}

    # Card fields
    price = record.get("price")
    if price is not None and not isinstance(price, int):
        try:
            price = int(price)
        except (TypeError, ValueError):
            price = None
    out["price_eur"] = str(price) if price is not None else ""
    out["currency"] = _safe_str(record.get("currency") or "€")
    if price is not None:
        out["price_display"] = f"{price:,.0f} {out['currency']}".replace(",", ".")
    out["title"] = _safe_str(record.get("title"))
    out["link"] = _safe_str(record.get("link"))
    out["rooms"] = str(record.get("rooms")) if record.get("rooms") is not None else ""
    out["sq_meters"] = str(record.get("sq_meters")) if record.get("sq_meters") is not None else ""
    out["location"] = _safe_str(record.get("location"))
    detail = record.get("detail")  # used for backfill and detail columns
    if isinstance(detail, dict):
        feats = detail.get("features") or {}
        if not out["rooms"] and feats.get("rooms"):
            try:
                out["rooms"] = str(feats["rooms"][0]) if feats["rooms"] else ""
            except (IndexError, TypeError):
                pass
        if not out["sq_meters"] and feats.get("sq_meters"):
            try:
                out["sq_meters"] = str(feats["sq_meters"][0]) if feats["sq_meters"] else ""
            except (IndexError, TypeError):
                pass
        if not out["location"] and detail.get("location"):
            out["location"] = _safe_str(detail["location"])
    tags = record.get("tags")
    out["tags"] = "; ".join(str(t) for t in tags) if isinstance(tags, list) else _safe_str(tags)
    out["seller"] = _safe_str(record.get("seller"))
    out["seller_url"] = _safe_str(record.get("seller_url"))
    out["description"] = _safe_str(record.get("description"))
    out["listing_type"] = _safe_str(record.get("listing_type") or "venta")

    # Detail fields (detail already fetched above for backfill)
    if isinstance(detail, dict):
        out["detail_title"] = _safe_str(detail.get("title"))
        out["detail_location"] = _safe_str(detail.get("location"))
        dp = detail.get("price")
        out["detail_price"] = str(dp) if dp is not None else ""
        out["detail_description"] = _safe_str(detail.get("description"))
        out["detail_updated"] = _safe_str(detail.get("updated"))
        if isinstance(detail.get("features"), dict):
            out["detail_features"] = json.dumps(detail["features"], ensure_ascii=False)
        if isinstance(detail.get("images"), list):
            out["detail_images"] = "; ".join(str(u) for u in detail["images"])
    return out


def export_json(data: list[dict[str, Any]], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def export_csv(data: list[dict[str, Any]], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not data:
        return
    flat = [_flatten_for_csv(d) for d in data]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=CSV_COLUMNS, extrasaction="ignore", quoting=csv.QUOTE_NONNUMERIC
        )
        w.writeheader()
        w.writerows(flat)


# Canonical listing URL: same listing can appear as /inmueble/123/, /ca/inmueble/123/, /en/inmueble/123/
CANONICAL_LISTING_URL = "https://www.idealista.com/inmueble/"


def normalize_listing_link(url: str) -> str:
    """Return canonical form https://www.idealista.com/inmueble/{id}/ so ca/en/fr variants dedupe to one."""
    if not url or "idealista" not in url.lower() or "/inmueble/" not in url:
        return url.strip()
    m = re.search(r"/inmueble/(\d+)/?", url)
    if m:
        return f"{CANONICAL_LISTING_URL}{m.group(1)}/"
    return url.strip()


def get_existing_links_from_csv(path: str | Path) -> set[str]:
    """Read an existing CSV and return the set of canonical listing links (for resume). Dedupes by listing ID."""
    path = Path(path)
    if not path.exists():
        return set()
    links: set[str] = set()
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            link = row.get("link", "").strip()
            if link:
                links.add(normalize_listing_link(link))
    return links


def write_csv_header(path: str | Path) -> None:
    """Write only the CSV header row (for starting a fresh file before appending rows)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=CSV_COLUMNS, extrasaction="ignore", quoting=csv.QUOTE_NONNUMERIC
        )
        w.writeheader()
        f.flush()


def append_csv_row(record: dict[str, Any], path: str | Path) -> None:
    """Append a single flattened record to a CSV (creates file with header if new)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    flat = _flatten_for_csv(record)
    row = {k: flat.get(k, "") for k in CSV_COLUMNS}
    write_header = not path.exists() or path.stat().st_size == 0
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=CSV_COLUMNS, extrasaction="ignore", quoting=csv.QUOTE_NONNUMERIC
        )
        if write_header:
            w.writeheader()
        w.writerow(row)
        f.flush()


if PYDANTIC:

    class ListingCardSchema(BaseModel):
        listing_type: str = "venta"
        title: str = ""
        link: str = ""
        price: int | None = None
        currency: str = "€"
        rooms: int | None = None
        sq_meters: int | None = None
        location: str = ""
        description: str = ""
        tags: list[str] = Field(default_factory=list)
        seller: str | None = None
        seller_url: str | None = None

    def validate_schema(record: dict[str, Any]) -> dict[str, Any]:
        """Validate and coerce one record; raise if invalid."""
        return ListingCardSchema.model_validate(record).model_dump()

else:

    def validate_schema(record: dict[str, Any]) -> dict[str, Any]:
        return record
