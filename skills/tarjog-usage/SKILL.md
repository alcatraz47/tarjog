---
name: tarjog-usage
description: Show the tokens and API-equivalent cost tarjog has tracked, broken down by model, agent, project and account profile, plus plan-limit percentages, right here in Claude Code. Use when the user asks "show my usage", "how many tokens have I used", "what did this cost", "usage today / this week", "which model costs the most", "am I near my limit", or "refresh model prices".
---

# tarjog-usage

tarjog records every session it's active in: after each Claude turn, a background hook saves that session's tokens per model and agent to its local ledger.

1. **Pick the period from the question:** `today`, `week`, `month`, or `all` (the default, meaning everything since tracking began). If the user asked to refresh prices, run `{{repo_dir}}/bin/tarjog prices --refresh` first.
2. **Run:** `{{repo_dir}}/bin/tarjog usage --period <period>`. Prices refresh automatically from Anthropic's pricing page once they're more than 7 days old.
3. **Show the output to the user as is.** It's already formatted markdown. Leave out any table that doesn't relate to the question. If they asked something specific ("which model costs the most?"), answer it in one line above the tables.
4. **Add one or two lines of insight** only if the numbers show something clear, such as one model driving most of the cost, routing drift, or a plan limit above 80%.

The output already notes that costs are API-equivalent at list price, not a bill on Pro or Team. Don't repeat that caveat.
