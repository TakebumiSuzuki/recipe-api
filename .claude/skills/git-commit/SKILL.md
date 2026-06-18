---
name: git-commit
description: Stage and commit changes to git with a reviewed, Conventional-Commits message generated from the actual diff. Use this whenever the user wants to commit, save, or check in changes — phrasings like "commit this", "commit these changes", "save my work to git", "add and commit", "コミットして", even when they don't name the skill. Always shows the staged files and the proposed message for confirmation before committing, warns before committing to main/master, scans for secrets and debug code, and never pushes.
---

# Git Commit

Stage and commit changes with a message generated from the **real diff**, written in
English using Conventional Commits. The one rule that must never break:

> **Show the user the staged files and the full proposed commit message, and wait for
> them to confirm, before running `git commit`.**

## Preflight — gather ground truth (run all, in order)

Never describe the changes from memory. Read what actually changed first:

1. `git status` — what is modified / staged / untracked.
2. `git diff` **and** `git diff --staged` — the actual content of the changes. Note that
   `git diff` does NOT show the contents of untracked (new) files; open those files
   directly (or `git add -N <path>` first) so new code is reviewed too.
3. `git branch --show-current` — which branch you are on.

If `git status` shows nothing to commit, stop and tell the user; there is nothing to do.

## Step 1 — Branch check

If the current branch is `main` or `master` (or another branch you can tell is shared or
protected, e.g. a release branch), **warn the user and wait for their answer** before going
further: commit here anyway, or create a branch first? Do not proceed to staging until they
reply, and do not silently commit to a protected branch.

## Step 2 — Decide what to stage (be deliberate)

- Stage only the files that belong in this commit. Do **NOT** reflexively
  `git add -A` / `git add .` — look at the list first.
- If the wrong files are already staged (from the preflight), unstage them with
  `git restore --staged <paths>`.
- If the changes span unrelated concerns, propose splitting them into separate commits
  (one logical change per commit).
- Scan the diff and file list for things that must not be committed: secrets / API keys /
  `.env` files, large binaries or build artifacts, and leftover debug code (`console.log`,
  `print`, commented-out blocks, `TODO: remove`). If you find any, **stop, flag it, and let
  the user resolve it** (remove the secret, add to `.gitignore`, etc.), then re-run the
  preflight checks before continuing. Do not stage flagged content.

Then stage the intended files with `git add <paths>`.

## Step 3 — Compose the message (Conventional Commits + clean subject/body rules)

Write the message in **English**, in this shape:

```
<type>(<optional scope>): <imperative summary>

<body: explain WHAT changed and WHY, not how>

<optional footer, e.g. Refs: #123  or  BREAKING CHANGE: ...>
```

`type` is one of: `feat` (new feature), `fix` (bug fix), `docs`, `style` (formatting only),
`refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`.

Subject-line rules: **imperative mood** (`Add`, `Fix`, `Update` — not `Added` / `Fixes`),
**≤ 50 characters**, capitalized, **no trailing period**. Separate subject and body with one
blank line, and wrap the body at ~72 characters. Omit the body for a trivial one-line change.

Append this trailer as the last line of the message:

```
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

Full example:

```
feat(auth): add password reset endpoint

Send a reset token by email and expire it after 30 minutes.

Refs: #123
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

## Step 4 — Confirmation gate (do not skip)

In a single message, show the user:

- the list of files that will be committed (the staged set), and
- the full proposed commit message.

Then ask whether to commit with this content. **Do not run `git commit` until the user
confirms.** If they want changes, revise the message or the staged set and ask again.

## Step 5 — Commit, then stop

Commit with a HEREDOC so the multi-line message and trailer are preserved exactly:

```bash
git commit -m "$(cat <<'EOF'
feat(auth): add password reset endpoint

Send a reset token by email and expire it after 30 minutes.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

After committing, report the result: short hash, subject line, and branch.

**Stop there — do NOT `git push`.** Pushing is a separate, explicit action; this skill
ends at the commit. If a pre-commit hook fails or rewrites files, report what happened and
let the user decide — do not loop retrying.

---

**Reminder:** the message comes from the real diff, and `git commit` runs only after the
user has confirmed the staged files and the message.
