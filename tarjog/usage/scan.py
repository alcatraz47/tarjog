"""Read one Claude Code session's transcripts into deduplicated per-response usage records.

A session's transcript is <claude_config_dir>/projects/<key>/<session>.jsonl, and its subagents
write to <session>/subagents/agent-*.jsonl (+ .meta.json naming the agent type). A response is
written once per streamed content block, so records are deduplicated by message id. A forked or
resumed session copies its parent's messages under the parent's sessionId; those are skipped so
only work done in this session is counted.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from pathlib import Path

from .pricing import Usage

WORKTREE_MARKER = "/.claude/worktrees/"


@dataclass(frozen=True)
class Record:
    message_id: str
    timestamp: str  # ISO 8601, UTC
    session: str
    project: str
    model: str
    agent: str  # "main", or the subagent type (Explore, security-reviewer, …)
    effort: str | None
    usage: Usage
    geo: str | None
    speed: str | None

    def to_row(self) -> list:
        u = self.usage
        return [self.message_id, self.timestamp, self.session, self.project, self.model, self.agent,
                self.effort, u.input, u.cache_write_5m, u.cache_write_1h, u.cache_read, u.output, self.geo, self.speed]

    @classmethod
    def from_row(cls, row: list) -> "Record":
        return cls(*row[:7], Usage(*row[7:12]), row[12], row[13])


def project_of(cwd: str) -> str:
    """Collapse worktrees onto their repository so one project isn't split across many paths."""
    return cwd.split(WORKTREE_MARKER, 1)[0] if cwd else "unknown"


def _usage_of(raw: dict) -> Usage:
    split = raw.get("cache_creation") or {}
    write_total = raw.get("cache_creation_input_tokens", 0) or 0
    write_1h = split.get("ephemeral_1h_input_tokens", 0) or 0
    write_5m = split.get("ephemeral_5m_input_tokens", write_total - write_1h) or 0
    return Usage(
        input=raw.get("input_tokens", 0) or 0,
        cache_write_5m=write_5m,
        cache_write_1h=write_1h,
        cache_read=raw.get("cache_read_input_tokens", 0) or 0,
        output=raw.get("output_tokens", 0) or 0,
    )


def _subagent_type(path: Path) -> str | None:
    try:
        return json.loads(path.with_suffix(".meta.json").read_text()).get("agentType")
    except (OSError, ValueError):
        return None


def _parse_file(path: Path, session_id: str, agent: str | None) -> list[Record]:
    records: dict[str, Record] = {}
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            message = entry.get("message")
            if entry.get("type") != "assistant" or not isinstance(message, dict) or not message.get("usage"):
                continue
            if entry.get("sessionId", session_id) != session_id:
                continue  # copied from the parent of a forked/resumed session
            model = message.get("model") or ""
            if not model or model.startswith("<"):  # "<synthetic>" error placeholders
                continue
            message_id = message.get("id") or entry.get("requestId") or entry.get("uuid")
            raw = message["usage"]
            record = Record(
                message_id=message_id,
                timestamp=entry.get("timestamp", ""),
                session=session_id,
                project="",
                model=model,
                agent=agent or (entry.get("attributionAgent") or "subagent" if entry.get("isSidechain") else "main"),
                effort=entry.get("effort"),
                usage=_usage_of(raw),
                geo=raw.get("inference_geo"),
                speed=raw.get("speed"),
            )
            previous = records.get(message_id)
            if previous is None or record.usage.output >= previous.usage.output:
                records[message_id] = record  # later stream chunks carry the final output count
    return list(records.values())


def parse_session(transcript_path: Path, session_id: str, project: str) -> list[Record]:
    """All usage records for one session: the main transcript plus its subagents."""
    files: list[tuple[Path, str | None]] = [(transcript_path, None)] if transcript_path.exists() else []
    subagents_dir = transcript_path.with_suffix("") / "subagents"
    files += [(path, _subagent_type(path) or "subagent") for path in sorted(subagents_dir.glob("agent-*.jsonl"))]
    records = [replace(r, project=project) for path, agent in files for r in _parse_file(path, session_id, agent)]
    return records
