"""Render agent, skill and instruction templates for a resolved Profile."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import MARKER
from .config import ConfigError, Profile

PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")
REVIEWER_LENSES = {
    "system-design-reviewer": ("system design", "/code-review"),
    "security-reviewer": ("security", "/security-review"),
    "business-alignment-reviewer": ("business alignment", None),
}
AFTER_CHANGES_RULES = {
    "related": "After changing code, run the narrowest tests that cover the change, plus lint/type-check on the touched files, using the commands in the project profile. Report failures; never skip them silently.",
    "all": "After changing code, run the project's full test suite plus lint/type-check, using the commands in the project profile. Report failures; never skip them silently.",
    "off": "Don't run tests after changes unless I ask.",
}
# Instruction files written under earlier names; removed on apply if we generated them.
LEGACY_INSTRUCTION_FILES = ("routing.md",)


@dataclass(frozen=True)
class FileOutput:
    """A file to write (content set) or remove (content None)."""

    path: Path
    content: str | None


def _substitute(text: str, values: dict[str, str], source: Path) -> str:
    def replace(match: re.Match) -> str:
        key = match.group(1)
        if key not in values:
            raise ConfigError(f"{source}: unknown placeholder {{{{{key}}}}}")
        return values[key]

    return PLACEHOLDER.sub(replace, text)


def _stamp(text: str) -> str:
    """Add the ownership marker after the frontmatter so Claude Code still parses it."""
    note = f"<!-- {MARKER}; edit the tarjog template, not this file -->\n"
    if text.startswith("---\n"):
        end = text.index("\n---\n", 4) + len("\n---\n")
        return text[:end] + note + text[end:]
    return note + text


def _common_values(repo: Path, profile: Profile) -> dict[str, str]:
    return {
        "business_context": ", ".join(f"`{path}`" for path in profile.business_context),
        "repo_dir": str(repo),
        "legacy_rules": (repo / "templates" / "legacy_rules.md").read_text().strip(),
        "config_dir": str(profile.claude_config_dir),
        "profile": profile.name,
        "test_on_setup": profile.testing.run_on_setup,
        "test_after_changes": AFTER_CHANGES_RULES[profile.testing.after_changes],
    }


def render_agents(
    repo: Path, profile: Profile, agents_dir: Path | None = None, only: set[str] | None = None
) -> list[FileOutput]:
    """Render every agent template. With `only`, agents outside that set are removed if we wrote them."""
    agents_dir = agents_dir or profile.claude_config_dir / "agents"
    outputs = []
    for template in sorted((repo / "agents").glob("*.md")):
        purpose = profile.purposes.get(template.stem)
        if purpose is None:
            raise ConfigError(f"agents/{template.name} has no matching entry in [purposes]")
        target = agents_dir / template.name
        if not purpose.enabled or (only is not None and template.stem not in only):
            outputs.append(FileOutput(target, None))
            continue
        values = _common_values(repo, profile) | {"model": purpose.model, "effort": purpose.effort or "medium"}
        outputs.append(FileOutput(target, _stamp(_substitute(template.read_text(), values, template))))
    return outputs


def _review_values(profile: Profile) -> dict[str, str]:
    enabled, fallbacks = [], []
    for agent, (lens, builtin) in REVIEWER_LENSES.items():
        purpose = profile.purposes.get(agent)
        if purpose and purpose.enabled:
            enabled.append(f"`{agent}`")
        elif builtin:
            fallbacks.append(f"- {lens}: no custom agent — run `{builtin}` instead and include its findings.")
        else:
            fallbacks.append(f"- {lens}: disabled in config — say so in the report.")
    return {
        "review_agents": ", ".join(enabled) or "none",
        "review_fallbacks": "\n".join(fallbacks) or "- none: all lenses have agents.",
    }


def render_skills(repo: Path, profile: Profile) -> list[FileOutput]:
    outputs = []
    values = _common_values(repo, profile) | _review_values(profile)
    for template in sorted((repo / "skills").glob("*/SKILL.md")):
        target = profile.claude_config_dir / "skills" / template.parent.name / "SKILL.md"
        outputs.append(FileOutput(target, _stamp(_substitute(template.read_text(), values, template))))
    return outputs


def render_instructions(repo: Path, profile: Profile) -> list[FileOutput]:
    template = repo / "templates" / "tarjog.md"
    lines = [f"| {p.name} | `{p.model}` | {p.effort or '-'} | {'on' if p.enabled else 'off'} |"
             for p in profile.purposes.values()]
    values = _common_values(repo, profile) | {"purpose_table": "\n".join(lines)}
    target = profile.claude_config_dir / "tarjog.md"
    legacy = [FileOutput(profile.claude_config_dir / name, None) for name in LEGACY_INSTRUCTION_FILES]
    return [FileOutput(target, _stamp(_substitute(template.read_text(), values, template))), *legacy]
