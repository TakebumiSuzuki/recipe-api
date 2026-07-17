---
name: git-commit
description: Stage and commit changes to git with a reviewed, Conventional-Commits message generated from the actual diff. Use this whenever the user wants to commit, save, or check in changes — phrasings like "commit this", "commit these changes", "save my work to git", "add and commit", even when they don't name the skill.
allowed-tools: Bash(git status:*), Bash(git diff:*), Bash(git branch:*), Bash(git add:*), Bash(git commit:*)
---

# Git Commit

Stage and commit changes with a message generated from the **real diff**, written in
English using Conventional Commits. The one rule that must never break:

> **Show the user the files to be staged and the full proposed commit message, and wait
> for them to confirm, before running `git add` or `git commit`.**

## Preflight — ground truth

- Status (modified / staged / untracked): !`git status`
- Unstaged changes: !`git diff`
- Staged changes: !`git diff --staged`
- Current branch: !`git branch --show-current`

Note that `git diff` does NOT show the contents of untracked (new) files — open those
files directly so new code is reviewed too.

If the status above shows nothing to commit, stop and tell the user; there is nothing to do.

## Step 1 — Safety scan (what must never be staged)

Scan the diff and file list for anything that must not enter history: secrets (API keys,
`.env`, private-key files), large binaries or build artifacts, merge conflict markers, and
generated dirs that should be gitignored (`node_modules/`, `venv/`, etc.).

- Found something → **stop**, flag it to the user, and let them resolve it (remove the
  secret, add to `.gitignore`, etc.). Re-run the preflight checks, then continue.
  Do not stage flagged content.
- Found nothing → continue to Step 2.

## Step 2 — Decide what to stage

Be deliberate about scope — do **NOT** reflexively `git add -A` / `git add .`. Look at
the list first, then run these checks:

1. Files already staged that are unrelated to this commit → unstage with
   `git restore --staged <paths>`.
2. Unstaged/untracked changes that could plausibly belong → assess **related** (same
   feature, dependency, or scope) vs. **separate concern**, then ask the user with
   `AskUserQuestion` (your assessment first, labeled `(Recommended)`):
   - **Include them all** — stage everything, one commit.
   - **Split — separate concern** — leave out now, handle later.
   - **Only what's already staged** — commit the current staged set as-is.
3. Nothing unstaged, or the user already told you the scope (e.g. "commit everything",
   "just the staged files") → skip the question, follow their instruction directly.

## Step 3 — Compose the message (Conventional Commits + clean subject/body rules)

Write the message in **English** as `type(optional scope): imperative summary`, a blank
line, then a body, then an optional footer.

- **Type**: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`,
  `chore`, `revert`.
- **Subject**: imperative mood, ≤ 50 characters, capitalized, no trailing period.
- **Body**: explain WHAT changed and WHY — not HOW. Wrap at ~72 characters. Omit for a
  trivial one-line change.
- **Footer** (optional): e.g. `Refs: #123` or `BREAKING CHANGE: ...`.

Example:

```
feat(auth): add password reset endpoint

Send a reset token by email and expire it after 30 minutes.

Refs: #123
```

## Step 4 — Confirmation gate (do not skip)

This is the single human gate — nothing has been staged yet. In one message, show the
user:

- the current branch, and
- the list of files that will be staged and committed, and
- the full proposed commit message.

- Branch is `main` / `master` or another shared/protected branch (e.g. a release branch)
  → flag it here and offer to create a branch first instead of committing to it.

Then ask whether to commit with this content.

- User confirms → proceed to Step 5. **Do not run `git commit` before this.**
- User wants changes (different branch, revised message, different file set) → adjust
  and show this gate again.

## Step 5 — Stage, commit, then stop

Stage the confirmed files with `git add <paths>`. Then commit with a HEREDOC so the
multi-line message is preserved exactly:

```bash
git commit -m "$(cat <<'EOF'
<subject>

<body>
EOF
)"
```

After committing, report the result: short hash, subject line, and branch.

**Stop there — do NOT `git push`.** Pushing is a separate, explicit action; this skill
ends at the commit. If a pre-commit hook fails or rewrites files, report what happened and
let the user decide — do not loop retrying.

---

**Reminder:** the message comes from the real diff, and `git commit` runs only after the
user has confirmed the file list and the message.
