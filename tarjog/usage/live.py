"""Real-time entry points called by Claude Code: the Stop/SessionEnd hook and the status line.

Each reads Claude Code's JSON from stdin, must never fail loudly (a broken hook or status
line would disturb every session), and must stay fast.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from . import ledger, scan

LIMIT_WINDOWS = ("five_hour", "seven_day")


def _stdin_json() -> dict:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return {}


def on_turn_end(data_dir: Path, profile: str) -> None:
    """Record the current session's token usage (main + subagents) into tarjog's ledger."""
    event = _stdin_json()
    session_id, transcript = event.get("session_id"), event.get("transcript_path")
    if not session_id or not transcript:
        return
    existing = data_dir / "sessions" / f"{session_id}.json"
    try:  # keep the project the session started in, even if it later moved into a scratchpad
        project = json.loads(existing.read_text())["project"]
    except (OSError, ValueError, KeyError):
        project = scan.project_of(event.get("cwd", ""))
    records = scan.parse_session(Path(transcript), session_id, project)
    if records:
        ledger.write_session(data_dir, session_id, profile, project, records)


def _save_limits(data_dir: Path, event: dict, profile: str) -> None:
    limits = {w: event["rate_limits"][w] for w in LIMIT_WINDOWS if w in (event.get("rate_limits") or {})}
    if not limits:
        return
    path = data_dir / "limits.json"
    try:
        previous = json.loads(path.read_text()).get("rate_limits")
    except (OSError, ValueError):
        previous = None
    if previous == limits:
        return
    data_dir.mkdir(parents=True, exist_ok=True)
    snapshot = {"rate_limits": limits, "captured_at": int(time.time()), "profile": profile}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(snapshot))
    tmp.replace(path)


def status_line(data_dir: Path, profile: str) -> str:
    """One line: model · context % · session cost · plan limits. Also snapshots plan limits for the report."""
    event = _stdin_json()
    _save_limits(data_dir, event, profile)
    parts = [(event.get("model") or {}).get("display_name", "?")]
    context = (event.get("context_window") or {}).get("used_percentage")
    if context is not None:
        parts.append(f"ctx {context:.0f}%")
    cost = (event.get("cost") or {}).get("total_cost_usd")
    if cost is not None:
        parts.append(f"session ≈${cost:.2f}")
    limits = event.get("rate_limits") or {}
    for window, label in (("five_hour", "5h"), ("seven_day", "7d")):
        if window in limits:
            parts.append(f"{label} {limits[window].get('used_percentage', 0):.0f}%")
    parts.append(f"tarjog:{profile}")
    return " · ".join(parts)
