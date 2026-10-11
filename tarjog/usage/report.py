"""Turn tarjog's usage ledger into a compact markdown report, sized to read inside Claude Code."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from ..config import Profile
from .ledger import SessionEntry
from .pricing import PriceTable
from .scan import Record

PERIODS = {"today": 1, "week": 7, "month": 30, "all": None}


@dataclass
class Bucket:
    responses: int = 0
    input: int = 0
    cache_write: int = 0
    cache_read: int = 0
    output: int = 0
    cost: float = 0.0
    unpriced: int = 0
    models: set = field(default_factory=set)

    def add(self, record: Record, cost: float | None) -> None:
        u = record.usage
        self.responses += 1
        self.input += u.input
        self.cache_write += u.cache_write_5m + u.cache_write_1h
        self.cache_read += u.cache_read
        self.output += u.output
        self.models.add(record.model)
        if cost is None:
            self.unpriced += 1
        else:
            self.cost += cost

    @property
    def tokens(self) -> int:
        return self.input + self.cache_write + self.cache_read + self.output


HEADERS = ["Responses", "Input", "Cache write", "Cache read", "Output", "Tokens", "Cost*"]


def _tok(n: int) -> str:
    for unit, size in (("B", 1e9), ("M", 1e6), ("k", 1e3)):
        if n >= size:
            return f"{n / size:.1f}{unit}"
    return str(n)


def _usd(value: float) -> str:
    return f"${value:,.2f}" if value >= 0.01 or value == 0 else f"${value:.4f}"


def _row(label: str, b: Bucket) -> list[str]:
    return [label, str(b.responses), _tok(b.input), _tok(b.cache_write), _tok(b.cache_read), _tok(b.output),
            _tok(b.tokens), _usd(b.cost) + (" †" if b.unpriced else "")]


def _table(first: str, rows: list[list[str]]) -> str:
    if not rows:
        return "_Nothing tracked in this period._\n"
    lines = ["| " + " | ".join([first, *HEADERS]) + " |", "|" + "---|" * (len(HEADERS) + 1)]
    return "\n".join(lines + ["| " + " | ".join(row) + " |" for row in rows]) + "\n"


def _local(timestamp: str) -> datetime | None:
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return None


def _limits_line(data_dir: Path) -> str | None:
    try:
        snapshot = json.loads((data_dir / "limits.json").read_text())
    except (OSError, ValueError):
        return None
    parts = []
    for window, label in (("five_hour", "5-hour"), ("seven_day", "7-day")):
        data = snapshot.get("rate_limits", {}).get(window)
        if data:
            resets = f", resets {datetime.fromtimestamp(data['resets_at']):%a %H:%M}" if data.get("resets_at") else ""
            parts.append(f"{label} {data.get('used_percentage', 0):.0f}%{resets}")
    taken = datetime.fromtimestamp(snapshot.get("captured_at", 0))
    return f"**Plan limits** ({snapshot.get('profile', '?')}, as of {taken:%d %b %H:%M}): " + " · ".join(parts) if parts else None


def _group(rows: list[tuple[Record, float | None, SessionEntry]], key) -> list[tuple[str, Bucket]]:
    groups: dict[str, Bucket] = defaultdict(Bucket)
    for record, cost, entry in rows:
        groups[key(record, entry)].add(record, cost)
    return sorted(groups.items(), key=lambda kv: -kv[1].cost)


def build(entries: list[SessionEntry], prices: PriceTable, profile: Profile, data_dir: Path, period: str = "all") -> str:
    if not entries:
        return ("No usage tracked yet. tarjog records each session after every Claude turn once the profile is applied "
                "(`bin/tarjog apply`); start a new session and ask again.")
    now = datetime.now().astimezone()
    days = PERIODS[period]
    start = (now.date() - timedelta(days=days - 1)) if days else None

    rows = []
    for entry in entries:
        for record in entry.records:
            when = _local(record.timestamp)
            if when is not None and (start is None or when.date() >= start):
                rows.append((record, prices.cost(record.model, record.usage, record.geo, record.speed), entry))

    first = min((_local(r.timestamp) for e in entries for r in e.records if _local(r.timestamp)), default=now)
    label = {"today": "Today", "week": "Last 7 days", "month": "Last 30 days", "all": f"Since tracking began ({first:%d %b %Y})"}[period]
    totals = defaultdict(Bucket)
    for record, cost, _ in rows:
        totals[label].add(record, cost)
    total = totals[label]

    home = str(Path.home())
    by_model = _group(rows, lambda r, e: r.model)
    by_agent = _group(rows, lambda r, e: r.agent)
    by_project = _group(rows, lambda r, e: e.project.replace(home, "~"))
    by_profile = _group(rows, lambda r, e: e.profile)

    sessions = len({e.session for _, _, e in rows})
    out = [f"## tarjog usage — {label}\n",
           f"{sessions} session{'s' if sessions != 1 else ''} · {_tok(total.tokens)} tokens · **{_usd(total.cost)}** API-equivalent\n"]
    limits = _limits_line(data_dir)
    if limits:
        out.append(limits + "\n")
    out += ["### By model\n", _table("Model", [_row(k, b) for k, b in by_model]),
            "### By agent\n", _table("Agent", [_row(k, b) for k, b in by_agent])]

    drift = []
    for agent, bucket in by_agent:
        purpose = profile.purposes.get(agent)
        if purpose and purpose.enabled and bucket.models - {purpose.model}:
            drift.append(f"- `{agent}` ran on {', '.join(sorted(bucket.models - {purpose.model}))}; "
                         f"profile `{profile.name}` routes it to `{purpose.model}`.")
    if drift:
        out += ["Routing drift (sessions started before the last apply, or a manual `/model` switch):\n", *drift, ""]
    if len(by_project) > 1:
        out += ["### By project\n", _table("Project", [_row(k, b) for k, b in by_project[:8]])]
    if len(by_profile) > 1:
        out += ["### By account profile\n", _table("Profile", [_row(k, b) for k, b in by_profile])]

    unpriced = sorted({r.model for r, c, _ in rows if c is None})
    out.append("\\* Cost is API-equivalent at Anthropic list price "
               f"(prices from {datetime.fromtimestamp(prices.data.get('fetched_at', 0)):%d %b %Y}). "
               "On Pro or Team you pay a flat fee, so compare with it rather than read it as a bill.")
    if unpriced:
        out.append(f"† Not in the price table yet ({', '.join(unpriced)}): run `bin/tarjog prices --refresh`.")
    return "\n".join(out) + "\n"
