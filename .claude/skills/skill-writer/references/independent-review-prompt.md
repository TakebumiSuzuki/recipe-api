# Independent review — subagent instructions

This file is your complete task. Read it fully and follow it; do not skim it. The agent
that spawned you has given you two values: the **path to the SKILL.md** under review and
its **one-line purpose**. Use those below.

Read the SKILL.md at the given path, plus any files it points to under `references/` and
`scripts/`.

This is a skill that *you* — an AI agent — will be made to follow, not a human. Read it as
the agent that has to execute it end to end, knowing your own tendencies (skimming files
you're told to read in full, head-previewing long files, feeling "informed enough" and
moving on).

Report specific, located problems only: quote the line, give the category, explain in one
sentence. Categories:

- **redundant/verbose** — says it twice, or wordy.
- **unclear/ambiguous** — a first-timer couldn't tell what to do.
- **contradictory** — two instructions can't both hold.
- **logical holes** — a step assumes something never established, or a case falls through.
- **would-skip** — a step or instruction you predict you'd skip, skim, or only partially
  follow in a real run. Name the line and why (e.g. "told to read X in full, but I'd just
  head it").

Do not rewrite, do not praise, do not list strengths. If a category has nothing, say so.
