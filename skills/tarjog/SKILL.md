---
name: tarjog
description: Wire a project up to tarjog in one go — learn its architecture and conventions, find and verify its test/lint commands, pick per-project model routing, locate business context, and keep all of it local to the user. Use when the user says "tarjog", "tarjog this repo", "set up / wire up / prepare this project", "apply tarjog to <path>", or opens a project and asks to get it ready for work.
---

# tarjog: wire up a project

tarjog lives at `{{repo_dir}}`. Active profile: `{{profile}}`. Do every step without asking, except where a step says to ask.

## 1. Pick the project
- Use the path the user gave. Otherwise use the session's working directory.
- If that directory is the tarjog repo itself (`{{repo_dir}}`) and no path was given, ask which project to set up.
- Resolve the repo root with `git -C <path> rev-parse --show-toplevel`. If it isn't a git repo, continue and note that later.
- If the project isn't the session's working directory, use absolute paths throughout. In the final report, recommend opening a session in the project for day-to-day work.

## 2. Architecture and conventions
Run the `onboard-repo` skill on the project. If `.claude/project-profile.md` already exists, reuse it and refresh it only if the user asked. This gives you the stack, layout, conventions, known debt, test/lint commands and business sources.

## 3. Testing
From the profile's "How to run, test, lint" section:
- **Lint and type-check:** run them if the tools are installed. They are read-only. Use a 3-minute timeout and summarise the results in one line each.
- **Test suite:** the setting is `{{test_on_setup}}`.
  - `always`: run it with a 10-minute timeout.
  - `ask`: show the command and ask once before running it.
  - `never`: don't run it.

  Legacy test suites often need databases or env vars. If a run fails for setup reasons, record why in the profile's "How to run, test, lint" section, e.g. "needs Postgres on :5432". Don't try to fix the environment.
- If no test command was found, record that under Open questions.

## 4. Per-project routing
Decide whether this project needs model settings different from the global profile. Use what the survey found:
- **Sensitive areas** (auth, payments, billing, PII/health data, crypto, infra-as-code, public APIs): raise `security-reviewer` to `{ tier = "deep", effort = "high" }`.
- **Very large or tangled repos** (over ~200k lines of code, or several god files): raise `system-design-reviewer` effort to `"high"`.
- **Small, low-risk repos** (scripts, internal tools): no overrides.

If overrides are warranted, merge them into `<root>/.claude/tarjog.toml` under `[purposes]`, keeping any `[review]` section onboarding wrote. Then run:

```
{{repo_dir}}/bin/tarjog project <root>
```

Always run this command, even with no overrides. It writes project-level agents and keeps tarjog's files out of git through `.git/info/exclude`. If it reports a config error, show the error and stop.

## 5. Report
At most 12 lines, as a checklist:
- **Architecture:** stack and the top 3 conventions, `.claude/project-profile.md` written or reused
- **Testing:** lint, type-check and test commands with results (passed / failed / skipped, with the reason)
- **Routing:** the overrides applied and why, or "uses global profile `{{profile}}`"
- **Business context:** the sources found, or missing (offer to draft `docs/BUSINESS_CONTEXT.md`)
- **Kept local:** the files that `bin/tarjog project` excluded
- **Next:** open a session in the project and work normally; say "review my changes" to review.
