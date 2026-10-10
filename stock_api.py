"""Fetch and validate current Blox Fruits dealer stock from a public JSON API."""

from __future__ import annotations

import json
import math
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit


DEFAULT_STOCK_API_URL = "https://bloxyvalues.com/api/stock"
STOCK_SOURCE_URL = "https://bloxyvalues.com/stock"


class StockApiError(Exception):
    """Raised when the provider cannot supply verifiable stock data."""


@dataclass(frozen=True)
class FruitStock:
    name: str
    beli: int
    robux: int


@dataclass(frozen=True)
class StockSnapshot:
    normal: tuple[FruitStock, ...]
    mirage: tuple[FruitStock, ...]
    last_updated: datetime | None


def _parse_price(value: Any, fruit_name: str, currency: str) -> int:
    if isinstance(value, bool) or value is None:
        raise StockApiError(
            f"The API omitted the {currency} price for {fruit_name}."
        )

    try:
        price = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        raise StockApiError(
            f"The API returned an invalid {currency} price for {fruit_name}."
        ) from None

    if not price.is_finite() or price <= 0 or price != price.to_integral_value():
        raise StockApiError(
            f"The API returned an invalid {currency} price for {fruit_name}."
        )

    return int(price)


def _parse_fruit_list(value: Any, stock_name: str) -> tuple[FruitStock, ...]:
    if not isinstance(value, list) or not value:
        raise StockApiError(f"The API did not return a verified {stock_name} stock list.")

    fruits: list[FruitStock] = []
    for item in value:
        if not isinstance(item, dict):
            raise StockApiError(f"The API returned an invalid item in {stock_name} stock.")

        raw_name = item.get("name")
        name = raw_name.strip() if isinstance(raw_name, str) else ""
        if not name:
            raise StockApiError(f"The API returned an item without a fruit name in {stock_name} stock.")

        fruits.append(
            FruitStock(
                name=name,
                beli=_parse_price(item.get("beli"), name, "Beli"),
                robux=_parse_price(item.get("robux"), name, "Robux"),
            )
        )

    return tuple(fruits)


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, bool) or value is None:
        return None

    try:
        if isinstance(value, (int, float)):
            if not math.isfinite(value) or value <= 0:
                return None
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)

        if isinstance(value, str) and value.strip():
            text = value.strip()
            if text.isdigit():
                return datetime.fromtimestamp(int(text) / 1000, tz=timezone.utc)
            if text.endswith("Z"):
                text = f"{text[:-1]}+00:00"
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None

    return None


def parse_stock_payload(payload: Any) -> StockSnapshot:
    """Validate the documented Bloxy Values API response without using fallback data."""
    if not isinstance(payload, dict):
        raise StockApiError("The public stock API returned an invalid response.")

    if payload.get("error"):
        raise StockApiError("The public stock API reported a data error.")

    normal = _parse_fruit_list(payload.get("normalStock"), "Normal")
    mirage = _parse_fruit_list(payload.get("mirageStock"), "Mirage")

    return StockSnapshot(
        normal=normal,
        mirage=mirage,
        last_updated=_parse_timestamp(payload.get("lastUpdated")),
    )


def fetch_stock(
    api_url: str = DEFAULT_STOCK_API_URL,
    timeout_seconds: float = 15,
) -> StockSnapshot:
    """Fetch a fresh response from the configured HTTPS stock API."""
    parsed_url = urlsplit(api_url)
    if parsed_url.scheme != "https" or not parsed_url.netloc:
        raise StockApiError("The stock API URL must be a valid HTTPS URL.")

    request = urllib.request.Request(
        api_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "BloxFruitsStockTelegramBot/1.0",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw_body = response.read()
    except urllib.error.HTTPError as error:
        raise StockApiError(
            f"The public stock API returned HTTP {error.code}."
        ) from None
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError):
        raise StockApiError("The public stock API could not be reached.") from None

    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
        raise StockApiError("The public stock API returned invalid JSON.") from None

    return parse_stock_payload(payload)
