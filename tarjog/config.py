"""Load tarjog.toml, layer profile and project overrides, and resolve a validated Profile."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

VALID_EFFORTS = {"low", "medium", "high", "xhigh", "max"}
OVERRIDABLE_SECTIONS = ("models", "purposes", "review", "testing")
TEST_ON_SETUP = {"ask", "always", "never"}
TEST_AFTER_CHANGES = {"related", "all", "off"}
PROJECT_CONFIG = Path(".claude") / "tarjog.toml"


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Purpose:
    name: str
    model: str
    effort: str | None  # None = not set; agents fall back to medium
    enabled: bool


@dataclass(frozen=True)
class GitIdentity:
    github_user: str | None
    name: str | None
    email: str | None


@dataclass(frozen=True)
class Testing:
    run_on_setup: str
    after_changes: str


@dataclass(frozen=True)
class UsageSettings:
    track: bool  # async Stop/SessionEnd hooks record each session's usage in tarjog's ledger
    statusline: bool  # status line with plan-limit %, which also snapshots limits for the report


@dataclass(frozen=True)
class Profile:
    name: str
    claude_config_dir: Path
    models: dict[str, str]
    purposes: dict[str, Purpose]
    business_context: tuple[str, ...]
    testing: Testing
    usage: UsageSettings
    git: GitIdentity


def _merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _blank_to_none(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _as_paths(value: str | list[str]) -> tuple[str, ...]:
    paths = (value,) if isinstance(value, str) else tuple(value)
    if not paths or not all(isinstance(p, str) and p.strip() for p in paths):
        raise ConfigError("[review] business_context must be a path or a non-empty list of paths")
    return paths


def _choice(section: dict, key: str, allowed: set[str], default: str) -> str:
    value = section.get(key, default)
    if value not in allowed:
        raise ConfigError(f"[testing] {key} must be one of {sorted(allowed)}, got '{value}'")
    return value


def _resolve_purposes(specs: dict, models: dict[str, str]) -> dict[str, Purpose]:
    purposes = {}
    for name, spec in specs.items():
        tier = spec.get("tier")
        if tier not in models:
            raise ConfigError(f"purpose '{name}': tier '{tier}' is not defined in [models]")
        effort = spec.get("effort")
        if effort is not None and effort not in VALID_EFFORTS:
            raise ConfigError(f"purpose '{name}': effort must be one of {sorted(VALID_EFFORTS)}")
        purposes[name] = Purpose(name, models[tier], effort, bool(spec.get("enabled", True)))
    if "main" not in purposes:
        raise ConfigError("[purposes] must define 'main' (the session default model)")
    return purposes


def read_project_overrides(project_dir: Path) -> dict:
    """Return the [models]/[purposes]/[review]/[testing] overrides in <project>/.claude/tarjog.toml."""
    path = project_dir / PROJECT_CONFIG
    if not path.exists():
        return {}
    raw = tomllib.loads(path.read_text())
    unknown = set(raw) - set(OVERRIDABLE_SECTIONS)
    if unknown:
        raise ConfigError(f"{path}: unknown sections {sorted(unknown)}; allowed: {list(OVERRIDABLE_SECTIONS)}")
    return raw


def load_profile(config_path: Path, profile_name: str | None, project_overrides: dict | None = None) -> Profile:
    if not config_path.exists():
        raise ConfigError(f"{config_path} not found — copy config/tarjog.example.toml to it first")
    raw = tomllib.loads(config_path.read_text())

    profiles = raw.get("profiles", {})
    name = profile_name or raw.get("default_profile")
    if name not in profiles:
        raise ConfigError(f"profile '{name}' not found; available: {', '.join(profiles) or 'none'}")
    profile_raw = profiles[name]

    sections = {key: raw.get(key, {}) for key in OVERRIDABLE_SECTIONS}
    for layer in (profile_raw, project_overrides or {}):
        sections = _merge(sections, {key: layer.get(key, {}) for key in OVERRIDABLE_SECTIONS})
    models = sections["models"]
    git_raw = profile_raw.get("git", {})
    usage_raw = _merge(raw.get("usage", {}), profile_raw.get("usage", {}))  # global + profile, not per project

    return Profile(
        name=name,
        claude_config_dir=Path(profile_raw.get("claude_config_dir", "~/.claude")).expanduser(),
        models=models,
        purposes=_resolve_purposes(sections["purposes"], models),
        business_context=_as_paths(sections["review"].get("business_context", "docs/BUSINESS_CONTEXT.md")),
        testing=Testing(
            run_on_setup=_choice(sections["testing"], "run_on_setup", TEST_ON_SETUP, "ask"),
            after_changes=_choice(sections["testing"], "after_changes", TEST_AFTER_CHANGES, "related"),
        ),
        usage=UsageSettings(
            track=bool(usage_raw.get("track", True)),
            statusline=bool(usage_raw.get("statusline", True)),
        ),
        git=GitIdentity(
            github_user=_blank_to_none(git_raw.get("github_user")),
            name=_blank_to_none(git_raw.get("name")),
            email=_blank_to_none(git_raw.get("email")),
        ),
    )
