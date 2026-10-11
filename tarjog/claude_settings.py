"""Merge profile values into settings.json and wire tarjog.md into CLAUDE.md.

Keys this module owns (set or removed on every apply): `model`, the
ANTHROPIC_DEFAULT_*_MODEL and GIT_AUTHOR_*/GIT_COMMITTER_* env vars, any hook whose
command carries a tarjog marker, and `statusLine` when unset or already tarjog's.
Everything else is left alone.
"""

from __future__ import annotations

import copy
import shlex
from pathlib import Path

from . import MARKER, is_generated
from .config import ConfigError, Profile

ALIAS_FAMILIES = ("haiku", "sonnet", "opus")
GIT_ENV_KEYS = {
    "name": ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"),
    "email": ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"),
}


def alias_pins(models: dict[str, str]) -> dict[str, str]:
    """Pin each alias family to the model ID configured for it, so `sonnet` etc. resolve predictably."""
    pins: dict[str, str] = {}
    for model_id in models.values():
        for family in ALIAS_FAMILIES:
            if family not in model_id:
                continue
            key = f"ANTHROPIC_DEFAULT_{family.upper()}_MODEL"
            if pins.get(key, model_id) != model_id:
                raise ConfigError(f"two [models] tiers use different {family} versions: {pins[key]}, {model_id}")
            pins[key] = model_id
    return pins


def _apply_env(env: dict, profile: Profile) -> None:
    for family in ALIAS_FAMILIES:
        env.pop(f"ANTHROPIC_DEFAULT_{family.upper()}_MODEL", None)
    env.update(alias_pins(profile.models))

    for field, keys in GIT_ENV_KEYS.items():
        value = getattr(profile.git, field)
        for key in keys:
            if value:
                env[key] = value
            else:
                env.pop(key, None)


def _desired_hooks(profile: Profile, tarjog_bin: Path) -> dict[str, list[dict]]:
    """tarjog's hook commands per event. Every command ends with the marker so re-applies replace them."""
    exe, name = shlex.quote(str(tarjog_bin)), shlex.quote(profile.name)
    hooks: dict[str, list[dict]] = {"SessionStart": [], "Stop": [], "SessionEnd": []}
    if profile.git.github_user:
        user = shlex.quote(profile.git.github_user)
        hooks["SessionStart"].append({"type": "command",
                                      "command": f"gh auth switch --hostname github.com --user {user} >/dev/null 2>&1 || true  # {MARKER}"})
    if profile.usage.track:
        # After every turn (and once more at session end), record this session's usage in the background.
        track = {"type": "command", "async": True,
                 "command": f"{exe} hook turn-end --profile {name} 2>/dev/null || true  # {MARKER}"}
        hooks["Stop"].append(track)
        hooks["SessionEnd"].append(dict(track))
    return hooks


def _apply_hooks(hooks: dict, profile: Profile, tarjog_bin: Path) -> None:
    for event, commands in _desired_hooks(profile, tarjog_bin).items():
        entries = [
            entry for entry in hooks.get(event, [])
            if not any(is_generated(hook.get("command", "")) for hook in entry.get("hooks", []))
        ]
        if commands:
            entries.append({"hooks": commands})
        if entries:
            hooks[event] = entries
        else:
            hooks.pop(event, None)


def _apply_status_line(settings: dict, profile: Profile, tarjog_bin: Path) -> str | None:
    """Own `statusLine` only if it is unset or ours; never replace the user's own status line."""
    current = settings.get("statusLine")
    if current and not is_generated(current.get("command", "")):
        return "kept your own statusLine; tarjog's status line (plan-limit tracking) is not installed"
    if profile.usage.statusline:
        exe, name = shlex.quote(str(tarjog_bin)), shlex.quote(profile.name)
        settings["statusLine"] = {"type": "command", "command": f"{exe} statusline --profile {name}  # {MARKER}"}
    else:
        settings.pop("statusLine", None)
    return None


def merged_settings(existing: dict, profile: Profile, tarjog_bin: Path) -> tuple[dict, list[str]]:
    settings = copy.deepcopy(existing)
    settings["model"] = profile.purposes["main"].model
    _apply_env(settings.setdefault("env", {}), profile)
    if not settings["env"]:
        del settings["env"]
    _apply_hooks(settings.setdefault("hooks", {}), profile, tarjog_bin)
    if not settings["hooks"]:
        del settings["hooks"]
    note = _apply_status_line(settings, profile, tarjog_bin)
    return settings, [note] if note else []


def claude_md_with_import(existing: str, instructions: Path, legacy_imports: tuple[Path, ...] = ()) -> str:
    """Return CLAUDE.md content that imports the instructions file exactly once.

    Drops tarjog's own heading lines and imports of legacy instruction files, so a
    re-apply after a rename leaves one clean block and never touches the user's text.
    """
    ours = {f"@{path}" for path in (instructions, *legacy_imports)}
    kept = [line for line in existing.splitlines() if not is_generated(line) and line not in ours]
    body = "\n".join(kept).rstrip()
    prefix = f"{body}\n\n" if body else ""
    return f"{prefix}# tarjog ({MARKER})\n@{instructions}\n"
