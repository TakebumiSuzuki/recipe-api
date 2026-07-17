---
name: verify-web
description: >-
  Verify a web app change by driving the real browser UI end-to-end and observing what a
  user would see — not by calling the API directly, and not by running the test suite. Use
  when verifying, checking, or confirming that a web / frontend / full-stack change works
  from the user's perspective: login, forms, uploads, navigation, list/detail views,
  rendering. Trigger after editing UI components, pages, routes, or handlers that a browser
  reaches, even when the user doesn't say "verify". Web apps with a browser UI only — not
  CLI tools, libraries, or API-only backends with no UI (those have no UI surface to drive).
---

# Verify a web app from the UI

**Verification here means driving the running app in a real browser and observing what a
user sees.** You start the app, open it in a browser with Playwright, reach the changed
behavior by clicking and typing like a user, and capture what happens. That capture is the
evidence.

**Two hard rules, stated once up front and again at the end:**

1. **Drive the browser, not the API.** If a user reaches the change by clicking a button,
   verify by clicking that button — do **not** `curl`/`fetch` the API underneath and call
   it done. The seam between the UI and the API is exactly where the interesting bugs live,
   and the API-only path skips it.
2. **Don't run the test suite as your verification.** Running `npm test` / the E2E suite
   proves you can run CI, not that this change works. Reading a test to learn what a flow
   should do is fine; then go drive the flow in the browser.

---

## Step 1 — Find the change

Establish exactly what you're verifying before touching the app.

```bash
git diff @{u}.. --stat        # committed range vs upstream (if set)
git diff origin/HEAD... --stat # no upstream: committed vs base
git diff HEAD --stat          # uncommitted work
```

Run whichever one matches your situation. Then **read the actual hunks** of the web-facing
files — not just `--stat` and filenames (redirect a large diff to a file and read it) — so
you know **which screens, routes, and interactions** the change touches. The diff is ground
truth; any PR/description is a claim about it — if they disagree, that's a finding.

If nothing here is a browser-reachable change (pure backend/config/docs with no UI effect),
report **SKIP — no UI surface** and stop. Don't invent a flow to drive.

## Step 2 — Get the app running (gate)

You need the dev server(s) up before you can drive anything. **Prefer a project skill that
already starts this app; otherwise figure out how to start it yourself.** Check, in order:

- **An existing skill that launches this app**, if one is available to you — whatever it's
  named (match on what it *does*, not the name). If there is one, use it **only to bring the
  app up**, then return here for Step 3 onward. Its job is to start the app, not to replace
  this skill's observation protocol (Step 4).
- `README` / `README.md` / `CONTRIBUTING.md` — look for a "getting started" / "development"
  section.
- `package.json` `scripts` (`dev`, `start`, `serve`), and for monorepos the root scripts
  (`turbo dev`, `pnpm -r dev`, workspace scripts).
- `docker-compose.yml`, `Makefile`, `Procfile`, `.env.example`.

For a full-stack app, this usually means starting **both** the backend and the frontend dev
server (plus any DB the flow needs). Many repos boot everything with one command — prefer
that.

**Do NOT proceed to Step 3 until the app actually responds in a browser.** Confirm the page
loads (navigate to it, get a 200 / rendered DOM) before driving.

**Only if you cannot determine how to start it** after checking the sources above, ask the
user with `AskUserQuestion` — e.g. "How do I start the dev server, and on what URL?" Ask
once, with what you already found, rather than guessing and failing silently.

## Step 3 — Drive it through the browser

**Auth needed to reach the change?** Look for test credentials the repo already ships in
seed scripts, E2E specs, or the README, or use a dev bypass / injectable session cookie.
Only if none exists, ask the user once with `AskUserQuestion`; never guess passwords. If
still blocked, report **BLOCKED**.

Use `playwright-cli` to open a real browser at the app's URL and take the **smallest path
that makes the changed behavior execute** — through the UI. Run headless (no display
needed); capture screenshots as you go.

`playwright-cli` records console messages and
network requests automatically from page load, and you read them back in Step 4 (item 5)
with its `console` / `requests` commands. Two things follow: drive the whole flow in **one
session**, and **don't `--clear`** the console/network buffer mid-flow, or you lose what
fired during load and navigation. Timing and screenshots you *do* take actively, so start
them from the **first load**, before you interact.

- Changed a page/component? Navigate to it and interact.
- Changed a form/handler? Fill and submit it through the form.
- Changed error handling? Trigger the error from the UI.
- Change lives deep (e.g. login → profile → photo upload)? You may set up prerequisite
  state the fast way (seed a user, deep-link a URL, reuse an auth cookie) to *reach* the
  page — but the **changed interaction itself must go through the UI**, not a direct API
  call.

## Step 4 — Observation protocol (the core of this skill)

Reaching the change is not the job — **observing it well is.** Most of this needs no vision
(read the DOM, network, console, clock); only visual-correctness needs a screenshot.

Apply the rows that fit the change — some are conditional (item 2 needs a failure to exist;
item 7 needs a default/sort to have changed). **In the report, every row below gets a line
or an explicit `N/A — <why>`**, so nothing is silently skipped.

| # | Observe | How (no vision unless noted) |
|---|---|---|
| 1 | **Timing / perceived speed** | Record a timestamp before the action and after the result appears (or `waitForResponse`); report the elapsed ms. Flag if a common action feels slow. Note: single dev-env sample, not a benchmark. |
| 2 | **Error message quality** | Trigger a failure, read the error text from the DOM: is it specific ("File exceeds 10 MB") or useless ("Error")? Does it appear where the user looks? Is a raw stack trace leaking? |
| 3 | **Silent failure** | After any "success" indication, **reload / re-navigate and confirm the change actually persisted.** A green toast whose data vanishes on reload is a bug the happy path hides. |
| 4 | **Feedback / state visibility** | Does a loading indicator (spinner/disabled button) exist in the DOM during the wait? Is there a confirmation after success, or silence? |
| 5 | **Console & network** | Read `playwright-cli`'s `console` and `requests` (auto-captured from page load) for warnings, errors, and failed network requests that fired during the flow — even ones unrelated to the change. Don't `--clear` before you've read them. |
| 6 | **Visual correctness** (needs screenshot) | Screenshot the key states — before / after / empty / error (and a narrow viewport **if the change touches layout**). Look for layout breakage, overflow/overlap, wrong image aspect ratio, broken empty-state. |
| 7 | **Default sanity** | Is the default value / sort order / initial selection reasonable for the common case? |
| 8 | **Claim vs behavior** | Does what you observe match what the diff/PR claims? A mismatch is a finding. |

**Animation / motion quality is a blind spot — do not fake a verdict on it.** A screenshot
is one frame; you cannot reliably judge whether a transition is janky or "moves oddly." If
motion matters to the change, report it as **needs human review**.

## Step 5 — Push on it (probe)

The happy path passing is the first half. **A happy-path-only run is not a PASS — at least
one off-happy-path probe is required before you may report PASS.** Probe *around* the change,
at the same UI surface:

- Empty/invalid input, oversized upload, wrong file type, submit twice fast, double-click.
- Do the action twice; do it with stale state; open two tabs and act in both.
- Trigger the adjacent errors the change *didn't* touch — did the refactor cover them too?

A probe that finds nothing is still worth a line: it tells the author what was covered.

## Step 6 — Report

Post this inline as the final message.

```
## Verify-web: <one-line what changed>

**Verdict:** PASS | FAIL | BLOCKED | SKIP

**Claim:** <your read of the diff and/or the stated PR claim; note any mismatch>

**How run:** <how you started the app — command + URL; note if you had to ask the user>

### Steps
Each step: one thing you did in the browser and what you observed.
1. ✅/❌/⚠️/🔍 <action in the UI> → <observed> <evidence: DOM text, timing ms, console line>
   (🔍 = a probe off the happy path. Include at least one.)

**Screenshot:** <the one frame a reviewer looks at — attach or reference the path>

### Findings
Lead with ⚠️ for anything worth interrupting the reviewer. Include the un-assertable
observations — perceived slowness, unhelpful errors, confusing flow, visual oddness, claim
mismatch, pre-existing breakage. Lower the bar: "would I mention this if the author were
sitting next to me?" Each probe gets a line even when it held.

### Suggested regression tests (optional)
For findings that are reproducible with a clear expected outcome (Step 4 #2/#3, or a bug the
probe surfaced), note the E2E test worth adding — one line each. These are the parts that
*can* be locked in; the Findings above are the parts that can't.
```

**Verdicts:**
- PASS = you drove it in the browser and it works at the UI.
- FAIL = you drove it and it doesn't, or it breaks something adjacent, or claim and diff disagree.
- BLOCKED = couldn't get the app up / couldn't reach an observable state (say exactly where it stopped).
- SKIP = no browser-reachable change. When in doubt, FAIL with the raw capture attached — a false PASS ships a broken screen.

---

**Remember the two rules:** drive the **browser**, not the API; and the goal is
**observation**, not a green test run.
