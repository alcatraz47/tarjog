# tarjog profile: {{profile}}

| Purpose | Model | Effort | Enabled |
|---|---|---|---|
{{purpose_table}}

- Searches across more than a few files go to the `Explore` agent. Work from the paths it returns instead of reading whole files here.
- Read files by line range when you know which lines matter, and don't re-read files already in context.
- Keep replies short: don't restate the plan or summarize diffs I can already see.
- For code review requests, use the `review-ai` skill. Business context is looked up in each repo at {{business_context}}, unless the repo's `.claude/tarjog.toml` overrides it.
- If the repo has `.claude/project-profile.md`, read it before making structural changes (new files, modules, dependencies) and follow its conventions.
- When I ask to set up, wire up or prepare a project ("tarjog this repo", "set up ~/work/foo"), use the `tarjog` skill. To only learn an unfamiliar repo, use `onboard-repo`. To switch account profiles or re-apply config, use `switch-profile`. For questions about token use, cost or plan limits, use `tarjog-usage`.
- Commit and push with the git identity and GitHub account this profile already set up. Don't change git config, `gh` auth or credentials yourself.

# Testing

- {{test_after_changes}}
- If the project profile has no test command, or the command fails for setup reasons (missing services, env vars), say so once and continue. Don't invent a test setup unasked.

# Modularity

- Split code by responsibility: entry point and orchestration, domain logic, model or LLM calls, prompts, tools, schemas, config, and I/O (DB, HTTP, files) each get their own module. Don't pile them into one file such as `agent.py`, `main.py` or `app.py`.
- Exceptions: the existing architecture already keeps this in a single file, or I explicitly ask for one. In those cases, follow the existing layout and don't restructure unasked.
- Before creating files, check how the repo is already organised and extend that layout instead of inventing a new one.
- Modular, not fragmented: no files holding a single function, and no abstraction layers or interfaces without a second real use.
- When a file you're editing would take on a second responsibility, put the new code in a new module and say so in one line.
