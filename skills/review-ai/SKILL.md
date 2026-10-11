---
name: review-ai
description: Three-lens review of AI-generated code — system design, security, business alignment — judged against this repo's own conventions. Use whenever the user asks to review, check, audit or sanity-check changes, a diff, branch, PR or files ("review my changes", "is this PR ok", "check what the AI wrote"), not only when they type /review-ai. Args - [lite|deep] [target] -- <task goal>.
---

# /review-ai

Usage: `/review-ai [lite|deep] [target] -- <what this change is supposed to achieve>`

- No mode given (the usual case when the user just asks for a review): choose `lite` for under ~300 changed lines with no auth, payment, migration or dependency changes. Otherwise choose `deep`. State which you picked in one line.
- `lite`: one pass in this session covering every lens. Cheapest option, for small diffs (under ~300 changed lines).
- `deep`: run the review agents in parallel: {{review_agents}}. Costs roughly one context read per agent. Use it for large or risky changes (auth, payments, data migrations, new dependencies).
- `target`: defaults to uncommitted changes vs HEAD. Can also be a branch (`main...feature`), a PR number (`gh pr diff`), or a path.

Lenses without a custom agent (profile `{{profile}}`):
{{review_fallbacks}}

## Steps

0. **Know the repo.** If `.claude/project-profile.md` doesn't exist, run the `onboard-repo` skill first and tell the user in one line that you did. This happens once per repo and makes reviews of legacy code fair.
1. **Get the goal.** Use the text after `--`. If there is none, check the PR description (`gh pr view --json title,body`). Failing that, ask the user one question for it. Never derive the goal from the code itself.
2. **Get the diff.** Run `git diff --stat` first, then fetch the full diff. If it is over ~1500 lines, list the files and ask which to focus on rather than reading everything.
3. **Find the business context.** Use the repo's `.claude/tarjog.toml` `[review] business_context` list if present. Otherwise use the first of {{business_context}} that exists. In `lite` mode read it here, at most ~300 lines. In `deep` mode pass the path to the agents instead. If none exists, say so in the report.
4. **Review.**
   - `lite`: apply the checklists in the agent files under `{{config_dir}}/agents/` (the reviewer agents listed above) yourself, using the output formats they define. Read those files only if their contents aren't already in context.
   - `deep`: launch the agents in one message, in parallel. Give each one the goal, the diff command (not the diff text, which keeps this context small) and the business-context path. Don't re-review what they return.
   - For the lenses listed above without a custom agent, run the named built-in command.
5. **Synthesize**, in this order:
   - **Verdict**: ship / ship after fixes / rework, in one line with the reason.
   - **Must fix before merge**: blockers, critical/high security issues, and missing acceptance criteria. Deduplicate across lenses.
   - The lens sections, as returned.
   - **Questions for the product owner**, if any.

Keep the final report under ~60 lines. Every finding must cite `file:line`; drop any that can't.
