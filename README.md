# tarjog

*tar* (তার) = wire, *jog* (যোগ) = connection, in Bangla.

tarjog wires Claude Code to your way of working: cost-aware model routing, a three-lens review of AI-written code, testing habits, respect for each project's existing architecture, and tracking of the tokens and cost you use while it's active. It all runs from one config file, works across your personal (Pro) and work (Team) accounts, and fits on top of any legacy repo without adding anything to that repo's history.

## Daily use: just ask

Open any project in the Claude Code app and say:

| You say… | What happens |
|---|---|
| "tarjog this repo" / "set up ~/work/foo" | **`tarjog` skill.** It learns the architecture, finds and verifies the test/lint commands, chooses per-project model routing, locates the business context, and keeps it all local |
| "review my changes" / "is this PR ok?" | **`review-ai`.** It runs system design, security and business-alignment checks against *this repo's* conventions |
| "learn this repo" | **`onboard-repo`.** It writes `.claude/project-profile.md` (stack, layout, conventions, known debt, how to test) |
| "switch to work" | **`switch-profile`.** It applies the work profile, then reminds you to `/login` and start a new session |
| "show my usage" / "what did this week cost?" | **`tarjog-usage`.** It shows tracked tokens and cost by model, agent and project in the chat |

During ordinary coding, Claude also:
- sends file searches to Haiku
- follows the project's conventions and keeps code modular (no god-file `agent.py` unless the repo already works that way or you ask)
- runs the tests related to each change

## Token and cost tracking

While tarjog is active, it records every session's token use per model and agent. Ask in Claude Code ("show my usage", "what did this week cost?", "which model costs the most?") or type `/tarjog-usage`, and the report appears in the chat:

- totals for the period (today / week / month / since tracking began)
- **by model**: responses, input, cache writes, cache reads, output, total tokens and cost
- by agent (main, Explore, reviewers), by project, and by account profile
- **routing drift**: an agent that ran on a different model than your profile routes it to
- your 5-hour and 7-day plan-limit percentages, when available

| What | Where it comes from | When it updates |
|---|---|---|
| Tokens per response, model, agent | The current session's own transcript (plus its subagents), read by an async **Stop / SessionEnd hook**. Copies of a parent session's messages are skipped | After every Claude turn, in the background (~0.1 s) |
| Ledger | `usage/sessions/<session>.json`, local and gitignored, one file per tracked session | Same |
| Prices | Anthropic's official pricing page, parsed into `config/prices.json` | When older than 7 days, or `bin/tarjog prices --refresh` |
| Plan limits | Claude Code's status line data (Pro/Max) | Whenever the status line refreshes (terminal sessions) |

**What these numbers mean:**
- Costs are *API-equivalent at list price*, the same calculation Claude Code uses for `/cost`. On Pro or Team you pay a flat fee, so use the dollars to compare models and agents, and treat the plan-limit percentage as your real budget.
- Only sessions that ran with tarjog applied are tracked; older history isn't scanned.
- The desktop app doesn't seem to run status lines, so plan-limit percentages come from terminal (`claude`) sessions.

## How it fits together

```
tarjog/ (this repo)                 the control panel: config, templates, CLI
   │  bin/tarjog apply --profile X
   ▼
~/.claude/                          global: agents, skills, tarjog.md, settings.json
   │  read by every Claude Code session, in every folder
   ▼
~/work/legacy-repo/.claude/         per project, local only (.git/info/exclude):
   project-profile.md                 how this repo works
   tarjog.toml                        optional overrides: models, business context, testing
   agents/*.md                        rendered only when tarjog.toml overrides a purpose
```

Legacy repos never get a submodule, a copied file or a commit. tarjog's per-project files sit in `.git/info/exclude`, a private ignore list on your machine only. Commit them if your team wants them.

## Setup

```bash
cp config/tarjog.example.toml config/tarjog.toml    # gitignored; holds your identities
bin/tarjog show --profile personal
bin/tarjog apply --profile personal --dry-run
bin/tarjog apply --profile personal
```

## Config: `config/tarjog.toml`

| Want to change… | Edit |
|---|---|
| A model version everywhere | `[models]` (tiers `fast` / `standard` / `deep`) |
| Which model and effort does what | `[purposes]`: `main`, `Explore`, and each reviewer |
| Turn a reviewer off (the built-in command covers that lens) | `enabled = false` |
| Where business intent lives | `[review] business_context`, a list of fallback paths |
| Testing behaviour | `[testing] run_on_setup` = ask / always / never; `after_changes` = related / all / off |
| Usage tracking | `[usage] track`, `statusline` |
| Account-specific settings | `[profiles.<name>]`: Claude config dir, GitHub user, commit name and email, any overrides |
| One project's settings | `<project>/.claude/tarjog.toml` (the same sections), then `bin/tarjog project <path>` |

Settings apply in layers: **global → profile → project**.

## Commands

```
bin/tarjog show    [--profile P]             resolved config
bin/tarjog apply   [--profile P] [--dry-run] wire a profile into Claude Code (global)
bin/tarjog project [PATH] [--dry-run]        wire one project (per-project agents, local excludes)
bin/tarjog usage   [--period today|week|month|all] [--offline]   tracked tokens and cost
bin/tarjog prices  [--refresh]               show or refresh model prices from Anthropic
```

With no `--profile`, commands use the last applied profile.

## Safety

- tarjog only overwrites files it generated (they carry a marker).
- It backs up `settings.json` and `CLAUDE.md` before changing them.
- In `settings.json` it owns only `model`, the `ANTHROPIC_DEFAULT_*_MODEL` and `GIT_*` env vars, its own hooks, and `statusLine` (only if you haven't set your own).
- Never put tokens in the config.
- `gh auth switch` (run at session start) changes the active `gh` account for your terminals too.

## Routing, in order of impact

1. Default to Sonnet. For hard problems, use `/model opus` or `opusplan` if your plan includes Opus.
2. `/clear` between unrelated tasks. Use `/effort low` for routine edits.
3. Searches go to the Haiku `Explore` override. The built-in Explore otherwise uses your main model.
4. Keep CLAUDE.md short, and disconnect MCP servers and connectors you don't need.
5. No third-party proxies: Pro and Team logins may only be used in Claude Code and claude.ai.

On the Team plan, Anthropic's managed Code Review (usage credits, tuned with `REVIEW.md`) can review every PR without using your plan's usage.

## Layout

```
bin/tarjog                    entry point
tarjog/                       config.py · render.py · claude_settings.py · git_local.py · writer.py · cli.py
tarjog/usage/                 pricing.py · scan.py · ledger.py · report.py · service.py · live.py (hooks + status line)
config/prices.json            model prices parsed from Anthropic's pricing page
config/tarjog.example.toml    config template
agents/*.md                   agent templates ({{model}}, {{effort}}, …)
skills/*/SKILL.md             tarjog, onboard-repo, review-ai, switch-profile, tarjog-usage
templates/tarjog.md           global instructions: routing, testing, modularity
templates/legacy_rules.md     baseline rules shared by every reviewer
templates/BUSINESS_CONTEXT.md per-repo business context template
```

## License

MIT. See [LICENSE](LICENSE).
