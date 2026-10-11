"""Load prices and the usage ledger and render the report; shared by the CLI and the skill."""

from __future__ import annotations

from pathlib import Path

from ..config import Profile
from . import ledger, pricing, report

PRICE_MAX_AGE_DAYS = 7


def data_dir(repo: Path) -> Path:
    return repo / "usage"


def prices_path(repo: Path) -> Path:
    return repo / "config" / "prices.json"


def refresh_prices(repo: Path) -> str:
    data = pricing.fetch()
    pricing.save(prices_path(repo), data)
    return f"prices refreshed: {len(data['models'])} models from {data['source']}"


def load_prices(repo: Path, allow_network: bool) -> tuple[pricing.PriceTable, str | None]:
    """Load the price table, refreshing it from Anthropic when stale and the network is allowed."""
    note = None
    path = prices_path(repo)
    if allow_network and (not path.exists() or pricing.PriceTable.load(path).age_days > PRICE_MAX_AGE_DAYS):
        try:
            note = refresh_prices(repo)
        except (OSError, pricing.PricingError) as error:
            note = f"price refresh failed ({error}); using the saved table"
    return pricing.PriceTable.load(path), note


def render(repo: Path, profile: Profile, period: str, allow_network: bool) -> str:
    prices, note = load_prices(repo, allow_network)
    markdown = report.build(ledger.load(data_dir(repo)), prices, profile, data_dir(repo), period)
    return f"_{note}_\n\n{markdown}" if note else markdown
