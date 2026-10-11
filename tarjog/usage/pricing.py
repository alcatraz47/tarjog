"""Model price table: parsed from Anthropic's pricing page, cached in config/prices.json."""

from __future__ import annotations

import json
import re
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

PRICING_URL = "https://platform.claude.com/docs/en/about-claude/pricing.md"
MTOK = 1_000_000
US_GEO_MULTIPLIER = 1.1  # inference_geo = "us" on Claude 4.6+ models
_PRICE = re.compile(r"\$([\d.]+)\s*/\s*MTok")
_TIER = re.compile(r"\(for prompts (up to|over) ([\d,]+) tokens\)")
_DATE_SUFFIX = re.compile(r"-\d{8}$")
_COLUMNS = ("input", "cache_write_5m", "cache_write_1h", "cache_read", "output")


class PricingError(Exception):
    pass


@dataclass(frozen=True)
class Usage:
    input: int
    cache_write_5m: int
    cache_write_1h: int
    cache_read: int
    output: int

    @property
    def prompt_tokens(self) -> int:
        return self.input + self.cache_write_5m + self.cache_write_1h + self.cache_read


def model_key(name: str) -> str:
    """'Claude Opus 5.5' -> 'claude-opus-5-5'; 'claude-sonnet-4-5-20250929' -> 'claude-sonnet-4-5'."""
    name = re.sub(r"\(.*", "", name).strip().lower()
    return _DATE_SUFFIX.sub("", re.sub(r"[\s.]+", "-", name))


def _cell_prices(cells: list[str]) -> list[float] | None:
    values = [_PRICE.search(cell) for cell in cells]
    return [float(m.group(1)) for m in values] if all(values) else None


def parse_pricing_markdown(text: str) -> dict:
    """Extract the main model table (5 price columns) and the fast-mode table (input/output)."""
    models: dict[str, dict] = {}
    fast: dict[str, dict] = {}
    section = ""
    for line in text.splitlines():
        if line.startswith("#"):
            section = line.lstrip("#").strip().lower()
            continue
        if not line.startswith("| Claude"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        prices = _cell_prices(cells[1:])
        if prices is None:
            continue
        if len(prices) == 5 and section == "model pricing":
            entry = dict(zip(_COLUMNS, prices))
            tier = _TIER.search(cells[0])
            key = model_key(cells[0])
            if tier:
                limit = int(tier.group(2).replace(",", ""))
                bucket = "base" if tier.group(1) == "up to" else "long"
                models.setdefault(key, {})[bucket] = entry
                models[key]["long_context_threshold"] = limit
            else:
                models.setdefault(key, {})["base"] = entry
        elif len(prices) == 2 and section == "fast mode pricing":
            for name in cells[0].split(" / "):
                fast[model_key(name)] = {"input": prices[0], "output": prices[1]}
    if not models:
        raise PricingError("no model rows found — the pricing page format may have changed")
    return {"models": models, "fast": fast}


def fetch(timeout: float = 15) -> dict:
    request = urllib.request.Request(PRICING_URL, headers={"User-Agent": "tarjog"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        table = parse_pricing_markdown(response.read().decode("utf-8"))
    return table | {"source": PRICING_URL, "fetched_at": int(time.time())}


class PriceTable:
    def __init__(self, data: dict):
        self.data = data
        self.models: dict[str, dict] = data["models"]
        self.fast: dict[str, dict] = data.get("fast", {})

    @classmethod
    def load(cls, path: Path) -> "PriceTable":
        if not path.exists():
            raise PricingError(f"{path} missing — run `bin/tarjog prices --refresh`")
        return cls(json.loads(path.read_text()))

    @property
    def age_days(self) -> float:
        return (time.time() - self.data.get("fetched_at", 0)) / 86400

    def rates(self, model: str, prompt_tokens: int) -> dict[str, float] | None:
        entry = self.models.get(model_key(model))
        if entry is None:
            return None
        threshold = entry.get("long_context_threshold")
        if threshold and prompt_tokens > threshold and "long" in entry:
            return entry["long"]
        return entry["base"]

    def cost(self, model: str, usage: Usage, geo: str | None = None, speed: str | None = None) -> float | None:
        """API-equivalent USD cost of one response at list price, or None for an unknown model."""
        rates = self.rates(model, usage.prompt_tokens)
        if rates is None:
            return None
        multiplier = US_GEO_MULTIPLIER if geo == "us" else 1.0
        fast = self.fast.get(model_key(model)) if speed == "fast" else None
        if fast:  # fast mode scales every category by the same premium as base input
            multiplier *= fast["input"] / rates["input"]
        total = sum(getattr(usage, column) * rates[column] for column in _COLUMNS)
        return total / MTOK * multiplier


def save(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
