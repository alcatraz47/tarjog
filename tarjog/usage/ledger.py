"""tarjog's usage ledger: one JSON file per session tracked while tarjog is active.

usage/sessions/<session_id>.json = {session, profile, project, updated_at, rows: [Record rows]}
Each Stop hook rewrites the current session's file, so the ledger only ever holds sessions
that ran with tarjog enabled.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from .scan import Record


@dataclass(frozen=True)
class SessionEntry:
    session: str
    profile: str
    project: str
    updated_at: int
    records: list[Record]


def _sessions_dir(data_dir: Path) -> Path:
    return data_dir / "sessions"


def write_session(data_dir: Path, session_id: str, profile: str, project: str, records: list[Record]) -> None:
    folder = _sessions_dir(data_dir)
    folder.mkdir(parents=True, exist_ok=True)
    payload = {"session": session_id, "profile": profile, "project": project,
               "updated_at": int(time.time()), "rows": [r.to_row() for r in records]}
    tmp = folder / f".{session_id}.tmp"
    tmp.write_text(json.dumps(payload))
    tmp.replace(folder / f"{session_id}.json")


def load(data_dir: Path) -> list[SessionEntry]:
    """All tracked sessions, with each response counted once even if two ledger files hold it."""
    entries, seen = [], set()
    for path in sorted(_sessions_dir(data_dir).glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        records = []
        for row in data.get("rows", []):
            record = Record.from_row(row)
            if record.message_id not in seen:
                seen.add(record.message_id)
                records.append(record)
        entries.append(SessionEntry(data["session"], data.get("profile", "unknown"), data.get("project", "unknown"),
                                    data.get("updated_at", 0), records))
    return entries
