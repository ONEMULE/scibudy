from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime, timezone
import math
from typing import Any


TOKEN_RE = re.compile(r"[a-z0-9]+")


def now_utc_iso() -> str:
    return datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat()


def normalize_whitespace(value: str | None) -> str | None:
    if value is None:
        return None
    compact = " ".join(value.split())
    return compact or None


def canonical_doi(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    cleaned = re.sub(r"^https?://(dx\.)?doi\.org/", "", cleaned, flags=re.IGNORECASE)
    return cleaned.lower() or None


def normalize_title(value: str | None) -> str | None:
    if not value:
        return None
    text = normalize_whitespace(value)
    if not text:
        return None
    return re.sub(r"\s+", " ", text).strip().lower()


def slugify(value: str | None, *, max_length: int = 80) -> str:
    if not value:
        return "item"
    compact = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    compact = re.sub(r"-{2,}", "-", compact)
    return (compact[:max_length] or "item").rstrip("-")


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def year_from_any(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"(19|20)\d{2}", value)
    if not match:
        return None
    return int(match.group(0))


def safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def first_non_empty(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                return cleaned
            continue
        return value
    return None


def pick_url(value: Any) -> str | None:
    if isinstance(value, str):
        return value or None
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                url = item.get("url") or item.get("URL")
                if url:
                    return str(url)
            elif isinstance(item, str) and item:
                return item
    if isinstance(value, dict):
        url = value.get("url") or value.get("URL")
        if url:
            return str(url)
    return None


def extract_authors_from_names(items: Iterable[Any]) -> list[str]:
    authors: list[str] = []
    for item in items:
        if isinstance(item, str):
            name = normalize_whitespace(item)
        elif isinstance(item, dict):
            name = normalize_whitespace(
                first_non_empty(
                    item.get("name"),
                    " ".join(
                        part
                        for part in [item.get("given"), item.get("family")]
                        if isinstance(part, str) and part.strip()
                    ),
                    item.get("author", {}).get("display_name") if isinstance(item.get("author"), dict) else None,
                )
            )
        else:
            name = None
        if name:
            authors.append(name)
    return authors


def parse_date_parts(parts: Any) -> str | None:
    if not parts:
        return None
    raw = parts[0] if isinstance(parts, list) and parts and isinstance(parts[0], list) else parts
    if not isinstance(raw, list) or not raw:
        return None
    year = safe_int(raw[0])
    month = safe_int(raw[1]) if len(raw) > 1 else 1
    day = safe_int(raw[2]) if len(raw) > 2 else 1
    if not year:
        return None
    month = min(max(month or 1, 1), 12)
    day = min(max(day or 1, 1), 28)
    return f"{year:04d}-{month:02d}-{day:02d}"


def openalex_abstract(index: dict[str, list[int]] | None) -> str | None:
    if not index:
        return None
    positions: dict[int, str] = {}
    for word, indexes in index.items():
        for idx in indexes:
            positions[idx] = word
    if not positions:
        return None
    text = " ".join(word for _, word in sorted(positions.items()))
    return normalize_whitespace(text)


def completeness_score(result: Any) -> float:
    score = 0.0
    for attr in [
        "title",
        "abstract",
        "doi",
        "pmid",
        "landing_url",
        "pdf_url",
        "journal",
        "publisher",
        "published_date",
    ]:
        if getattr(result, attr, None):
            score += 1.0
    score += min(len(getattr(result, "authors", []) or []), 5) * 0.25
    if getattr(result, "citation_count", None):
        score += min(math.log1p(result.citation_count), 5.0)
    return score
