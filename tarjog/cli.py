"""tarjog command line.

  tarjog show    [--profile P]              print the resolved config
  tarjog apply   [--profile P] [--dry-run]  wire the profile into Claude Code (global)
  tarjog project PATH [--dry-run]           wire one project: per-project agents + local git excludes
  tarjog usage   [--period P] [--offline]   tokens and cost per model, agent, project, account (tracked sessions)
  tarjog prices  [--refresh]                show or refresh model prices from Anthropic's pricing page
  tarjog hook turn-end | statusline         called by Claude Code (reads its JSON on stdin)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from . import claude_settings, git_local, render, writer
from .config import PROJECT_CONFIG, ConfigError, Profile, load_profile, read_project_overrides
from .usage import live, pricing, report, service

REPO = Path(__file__).resolve().parent.parent
TARJOG_BIN = REPO / "bin" / "tarjog"
ACTIVE_PROFILE_FILE = REPO / "config" / ".active-profile"
LEGACY_INSTRUCTION_IMPORTS = ("routing.md",)
PROJECT_LOCAL_FILES = [str(PROJECT_CONFIG), ".claude/project-profile.md"]


def _active_profile_name() -> str | None:
    if not ACTIVE_PROFILE_FILE.exists():
        return None
    return ACTIVE_PROFILE_FILE.read_text().strip() or None


def _show(profile: Profile) -> None:
    print(f"profile            {profile.name}")
    print(f"claude_config_dir  {profile.claude_config_dir}")
    print(f"business_context   {', '.join(profile.business_context)}")
    print(f"testing            on setup: {profile.testing.run_on_setup}, after changes: {profile.testing.after_changes}")
    print(f"github_user        {profile.git.github_user or '-'}")
    print(f"git author         {profile.git.name or '-'} <{profile.git.email or '-'}>")
    print(f"usage tracking     track: {profile.usage.track}, status line: {profile.usage.statusline}")
    print("\npurpose                         model                 effort   enabled")
    for p in profile.purposes.values():
        print(f"{p.name:<31} {p.model:<21} {p.effort or '-':<8} {p.enabled}")
    print("\nalias pins:", json.dumps(claude_settings.alias_pins(profile.models)))


def _print_log(log: list[str], dry_run: bool) -> None:
    print("\n".join(line for line in log if not line.startswith("absent")))
    if dry_run:
        print("\n(dry run — nothing written)")


def _apply(profile: Profile, dry_run: bool, remember: bool) -> None:
    config_dir = profile.claude_config_dir
    outputs = [
        *render.render_agents(REPO, profile),
        *render.render_skills(REPO, profile),
        *render.render_instructions(REPO, profile),
    ]
    log = [writer.apply_output(output, dry_run) for output in outputs]

    settings_path = config_dir / "settings.json"
    existing = json.loads(settings_path.read_text()) if settings_path.exists() else {}
    settings, notes = claude_settings.merged_settings(existing, profile, TARJOG_BIN)
    log += writer.write_json(settings_path, settings, dry_run)
    log += [f"note   {note}" for note in notes]

    claude_md = config_dir / "CLAUDE.md"
    current = claude_md.read_text() if claude_md.exists() else ""
    legacy = tuple(config_dir / name for name in LEGACY_INSTRUCTION_IMPORTS)
    log += writer.write_text(claude_md, claude_settings.claude_md_with_import(current, config_dir / "tarjog.md", legacy), dry_run)

    _print_log(log, dry_run)
    if not dry_run:
        if remember:
            ACTIVE_PROFILE_FILE.write_text(profile.name + "\n")
        print(f"\nApplied profile '{profile.name}'. Start a new Claude Code session to pick it up.")


def _project(config_path: Path, profile_name: str | None, path: Path, dry_run: bool) -> None:
    root = git_local.repo_root(path) or path
    base = load_profile(config_path, profile_name)
    effective = load_profile(config_path, profile_name, read_project_overrides(root))

    # Project agents override same-named global ones; only write those whose settings differ.
    differing = {name for name, purpose in effective.purposes.items() if base.purposes.get(name) != purpose}
    for name in sorted(differing):
        if not effective.purposes[name].enabled:
            print(f"note   {name}: disabling per project isn't supported (the global agent still loads); "
                  "set enabled = false in the profile instead")
    overridden = {name for name in differing if effective.purposes[name].enabled}

    outputs = render.render_agents(REPO, effective, agents_dir=root / ".claude" / "agents", only=overridden)
    log = [writer.apply_output(output, dry_run) for output in outputs]

    local_files = PROJECT_LOCAL_FILES + [f".claude/agents/{name}.md" for name in sorted(overridden)]
    if git_local.repo_root(root):
        log += git_local.exclude_locally(root, local_files, dry_run)
    else:
        log.append(f"note   {root} is not a git repo; nothing to exclude")

    print(f"project {root} (profile '{effective.name}')")
    print(f"overrides: {', '.join(sorted(overridden)) or 'none, uses the global profile'}")
    _print_log(log, dry_run)


def _prices(refresh: bool) -> None:
    if refresh:
        print(service.refresh_prices(REPO))
    table = pricing.PriceTable.load(service.prices_path(REPO))
    print(f"fetched {table.age_days:.1f} days ago from {table.data.get('source')}\n")
    print(f"{'model':<20} {'input':>7} {'write5m':>8} {'write1h':>8} {'read':>6} {'output':>7}   $/MTok")
    for model, entry in sorted(table.models.items()):
        r = entry["base"]
        print(f"{model:<20} {r['input']:>7} {r['cache_write_5m']:>8} {r['cache_write_1h']:>8} {r['cache_read']:>6} {r['output']:>7}")


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--profile", help="profile name (default: last applied, else default_profile)")
    common.add_argument("--config", type=Path, default=REPO / "config" / "tarjog.toml")

    parser = argparse.ArgumentParser(prog="tarjog", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("show", parents=[common], help="print the resolved config")
    apply = commands.add_parser("apply", parents=[common], help="wire the profile into Claude Code")
    apply.add_argument("--target", type=Path, help="override claude_config_dir (for testing)")
    apply.add_argument("--dry-run", action="store_true")
    project = commands.add_parser("project", parents=[common], help="wire one project")
    project.add_argument("path", nargs="?", type=Path, help="project path (default: current directory)")
    project.add_argument("--dry-run", action="store_true")
    usage = commands.add_parser("usage", parents=[common], help="token and cost report for tracked sessions")
    usage.add_argument("--period", choices=list(report.PERIODS), default="all", help="default: all tracked usage")
    usage.add_argument("--offline", action="store_true", help="don't refresh prices from the network")
    prices = commands.add_parser("prices", help="show or refresh the model price table")
    prices.add_argument("--refresh", action="store_true")
    hook = commands.add_parser("hook", parents=[common], help="Claude Code hook entry point")
    hook.add_argument("event", choices=["turn-end"])
    commands.add_parser("statusline", parents=[common], help="Claude Code status line entry point")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    profile_name = getattr(args, "profile", None) or _active_profile_name()

    try:
        if args.command == "prices":
            _prices(args.refresh)
        elif args.command == "hook":
            live.on_turn_end(service.data_dir(REPO), profile_name or "unknown")
        elif args.command == "statusline":
            print(live.status_line(service.data_dir(REPO), profile_name or "unknown"))
        elif args.command == "project":
            _project(args.config, profile_name, (args.path or Path.cwd()).expanduser().resolve(), args.dry_run)
        else:
            profile = load_profile(args.config, profile_name)
            if args.command == "show":
                _show(profile)
            elif args.command == "usage":
                print(service.render(REPO, profile, args.period, allow_network=not args.offline))
            else:
                if args.target:
                    profile = replace(profile, claude_config_dir=args.target.expanduser().resolve())
                _apply(profile, args.dry_run, remember=args.target is None)
    except (ConfigError, pricing.PricingError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
