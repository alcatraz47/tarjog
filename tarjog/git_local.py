"""Keep tarjog's per-project files out of a repo's history via .git/info/exclude."""

from __future__ import annotations

import subprocess
from pathlib import Path

EXCLUDE_HEADER = "# tarjog: local-only project files"


def _git(project: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(project), *args], capture_output=True, text=True)


def repo_root(path: Path) -> Path | None:
    result = _git(path, "rev-parse", "--show-toplevel")
    return Path(result.stdout.strip()) if result.returncode == 0 else None


def _is_tracked(root: Path, rel_path: str) -> bool:
    return _git(root, "ls-files", "--error-unmatch", rel_path).returncode == 0


def exclude_locally(root: Path, rel_paths: list[str], dry_run: bool) -> list[str]:
    """Add untracked paths to .git/info/exclude. Tracked files are left alone: the team chose to commit them."""
    exclude_file = Path(_git(root, "rev-parse", "--git-path", "info/exclude").stdout.strip())
    if not exclude_file.is_absolute():
        exclude_file = root / exclude_file
    existing = exclude_file.read_text().splitlines() if exclude_file.exists() else []

    to_add = [p for p in rel_paths if f"/{p}" not in existing and not _is_tracked(root, p)]
    log = [f"keep   {p} (tracked in git; left as is)" for p in rel_paths if _is_tracked(root, p)]
    if not to_add:
        return log
    if not dry_run:
        lines = existing + ([EXCLUDE_HEADER] if EXCLUDE_HEADER not in existing else []) + [f"/{p}" for p in to_add]
        exclude_file.parent.mkdir(parents=True, exist_ok=True)
        exclude_file.write_text("\n".join(lines) + "\n")
    return log + [f"ignore /{p} (in {exclude_file}, local only)" for p in to_add]
