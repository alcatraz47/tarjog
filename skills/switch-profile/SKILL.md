---
name: switch-profile
description: Switch Claude Code routing between account profiles (e.g. personal Pro and work Team), or re-apply the tarjog config after it was edited. Use when the user says things like "switch to work / personal", "use the <name> profile", "I'm on my Team account now", "apply my tarjog config", or after they changed models, purposes, business-context paths or git identity in tarjog.toml.
---

# switch-profile

The tarjog repo is at `{{repo_dir}}`. The profile currently applied is `{{profile}}`.

1. **Pick the profile.** Use the name the user gave. If they described an account instead ("my Team account"), list the profiles with `grep -E '^\[profiles\.[^].]+\]' {{repo_dir}}/config/tarjog.toml` and pick the obvious match. Ask only if it's genuinely ambiguous.
2. **Preview:** `{{repo_dir}}/bin/tarjog apply --profile <name> --dry-run`. If it reports a config error, show it and stop.
3. **Apply:** `{{repo_dir}}/bin/tarjog apply --profile <name>`.
4. **Report** the lines that start with `write`, `remove` or `skip` (leave out `same`), then tell the user in one or two lines:
   - Agents and settings load when a session starts, so the change takes effect in a **new session**.
   - If the Claude account is different, run `/login` with that account first.
   - The GitHub account switches automatically at the start of the next session.

Never edit `tarjog.toml`, git config or `gh` auth yourself, unless the user asks for that specific change.
