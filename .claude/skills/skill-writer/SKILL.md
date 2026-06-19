---
name: skill-writer
description: Write high-quality Claude skills — author a new skill from scratch or improve how an existing skill is written. Use this whenever the user wants to create a skill, draft or rewrite a SKILL.md, turn a workflow or set of instructions into a reusable skill, or fix a skill that is not being followed reliably (steps get skipped, instructions ignored, too rigid, or too vague). Covers picking the skill type, writing the description so it triggers, structuring with progressive disclosure, and applying concrete prompt-writing techniques (gates, checklists, batch-reads, few-shot examples). Use it even when the user just says "make a skill for X" without mentioning SKILL.md.
---

# Skill Writer

A skill for **authoring skills well** — writing a new `SKILL.md` or improving the
writing of an existing one so the model that reads it actually does the right thing.

The whole job is captured in seven steps. Keep them in mind; the rest of this file
just expands each one.

1. **Capture intent** — what should the skill do, when should it fire, what comes out.
2. **Type it** — workflow, judgment, or knowledge. The type decides how to write it.
3. **Research** — pull exact names/specs from primary sources, not memory.
4. **Description & file structure** — write the description first (it controls
   triggering), then choose how to split the files.
5. **Write the body** — shape it to the type, applying the writing techniques below
   (the core of this skill).
6. **Review with fresh eyes** — re-read the draft cold and run the final checklist.
7. **Get an independent read** — have a subagent critique the draft cold; you decide
   what to act on.

Be flexible about where the user is. If they already have a draft, jump to step 4–7.
If they just want to "vibe," skip the ceremony.

## Talking to the user

People who write skills range from career engineers to a parent who just learned what
a terminal is. Read the cues. Plain words like "the part that decides when this runs"
beat jargon like "the trigger heuristic" unless the user clearly speaks that language.
Define a term in a half-sentence when in doubt. This costs you nothing and saves them.

---

## Step 1 — Capture intent

Before writing anything, get clear answers to:

1. **What should this skill let the model do?** The capability, in one sentence.
2. **What's the expected output?** A file? A code change? A formatted answer? A decision?
3. **How should it be invoked?** This matters and is easy to skip — ask it explicitly:
   - **Auto-trigger**: the model should reach for this skill on its own whenever a
     matching request appears. This is the default for most skills and means the
     description must work hard (see step 4) to get picked up.
   - **Explicit only**: the skill should fire *only* when the user deliberately runs it
     (e.g. types its slash command), never automatically. Choose this for skills that
     are expensive, opinionated, or that the user wants to stay in control of.

If the current conversation already contains the workflow the user wants to capture
("turn this into a skill"), mine it first — the tools used, the order of steps, the
corrections the user made — and confirm the gaps rather than re-interviewing from zero.

---

## Step 2 — Type the skill (lightweight)

Spend one breath classifying the skill, because the type decides which writing
techniques in step 5 you reach for. Getting this wrong is the most common failure:
forcing a rigid step-list onto something that needs judgment, or writing a strict
procedure as loose prose so its steps get skipped.

| Type | What it is | "Complete" means | Reach for |
|---|---|---|---|
| **Workflow** | Order matters; a sequence of steps (deploy, convert, release) | the full procedure, in order | gates, checklists, ordering — the control-flow techniques |
| **Judgment / policy** | Apply criteria, not a fixed sequence (review style, naming rules) | the full set of decision criteria | principles + few-shot examples; *avoid* rigid step-lists |
| **Knowledge / reference** | Hand over facts/API/lookup data (a spec sheet) | the necessary information, findable | clear headings, a table of contents; gates/steps don't apply |

A skill can be mostly one type with a touch of another — pick the dominant one.
**Completeness is about covering the information the model needs to behave correctly,
not about maximizing the number of steps.** Over-specifying freezes a smart model and
makes it brittle on inputs you didn't foresee.

---

## Step 3 — Research

Anything that has to be exact — API names, function signatures, config keys, CLI
flags — comes from primary sources, never memory. Use the documentation tools
available to you (e.g. a docs MCP like context7 for library specifics, web search for
current product behavior). If you can't confirm something, say so in the skill rather
than guessing. Come to the user with context already gathered, so you don't end up asking
for facts you could have looked up yourself.

---

## Step 4 — Description & file structure

A skill is a folder. The only required file is `SKILL.md`:

```
skill-name/
├── SKILL.md           (required: YAML frontmatter + markdown body)
└── (optional)
    ├── scripts/       executable code for deterministic, repeated work
    ├── references/    docs loaded only when needed
    └── assets/        files used in the output (templates, fonts, icons)
```

The folder name is the skill's `name`: lowercase letters, numbers, and hyphens only, and
clearest as a gerund or noun phrase that names what the skill does (`processing-pdfs`,
`pdf-processing`) — not a vague `helper` or `utils`.

### The description (write this first)

The `description` in the frontmatter is the single most important line: it's what the
model sees when deciding whether to use the skill at all. Write it to say **both what
the skill does and when to use it** — all the "when" lives here, not in the body.

The model tends to *under*-trigger skills, so for an auto-trigger skill make the
description a little pushy: name the concrete situations, phrasings, and file types that
should pull it in, including cases where the user won't name the skill explicitly.

- Thin: `Build a dashboard for internal metrics.`
- Better: `Build a dashboard for internal metrics. Use this whenever the user mentions
  dashboards, data visualization, internal metrics, or wants to display company data —
  even if they don't say "dashboard."`

For an **explicit-only** skill (from step 1), do the opposite: keep the description
short and factual so the model doesn't grab it on its own.

Either way, write the description in the **third person** ("Generates commit messages by
analyzing the staged diff…"), not the first or second ("I can help…", "You can use this
to…"). It's injected verbatim into the system prompt next to every other skill's, and a
mixed point of view there muddies triggering.

### Other frontmatter fields

Beyond `name` and `description`, frontmatter can carry more — invocation control, tool
access, model selection, and the like. Which fields exist depends on the runtime the skill
targets (Claude Code or another agent) and changes over time, so don't write them from
memory: look up the current set from the primary source via web search, and add whatever
this skill actually needs.

### Progressive disclosure

A skill loads in layers — **name + description** always in context, the **SKILL.md body**
when the skill fires, **scripts / references / assets** only as needed — so put each thing
where it gets seen at the right time. The non-obvious part: "always in context" is not the
same as *short*, since an auto-trigger description still has to name all its triggers.

A few structural guidelines:
- Keep the SKILL.md body roughly **under ~500 lines**. As it grows, prefer adding clear
  internal headings over splitting into many side files — a separate file the model is
  *told* to read is a file it often *won't*. Split only when a chunk is large and
  genuinely optional for a given run.
- Keep `references/` links **one level deep**: each one pointed to directly from
  SKILL.md, not from another reference file. The model tends to preview deeply-nested
  files (e.g. with `head`) and read them only partially, so anything reached by a chain
  of links often gets skimmed rather than read in full.
- Give any reference file longer than ~100 lines a **table of contents** at the top, so
  the model sees the full scope of what's there even when it previews the file instead of
  reading the whole thing.
- When a skill spans variants (aws/gcp/azure), a `references/<variant>.md` split is the
  right call, because the model only ever needs one.

---

## Step 5 — Write the body (the core)

This is where skills are won or lost. The techniques fall into two families, and which
family you reach for depends on the type from step 2.

- **Quality / judgment techniques** shape *how good* an output is. Here the model is
  smart — explain the *why*, show examples, and trust it. Rigid rules backfire.
- **Control-flow techniques** make the model *do the steps in order without skipping*.
  Here understanding is not enough; sometimes only hard structure works. This is the
  family most skills are missing.

A useful instinct: if you catch yourself writing `ALWAYS` / `NEVER` in caps to enforce
*quality*, stop and explain why instead — today's models have good theory of mind and do
better when they understand the point than when handed a bare rule. If you're enforcing
*control flow* (don't skip, don't proceed early), a hard structural line is legitimate —
use it sparingly.

### Control-flow techniques

| Technique | When | Why it works |
|---|---|---|
| **Gate (blocking)** | The model races ahead past a required input or confirmation | "Do not move to the next step until X" removes the gap to run ahead. A single such line often fixes an ordering slip that explanation alone never did. |
| **Batch-read** | Two+ files must all be read (e.g. `format.md` *and* `sample.md`) | The model reads one file, feels "informed enough," and moves on. "Read both in one parallel set of calls" closes the gap so both actually get read. |
| **Preflight checklist** | Several things must be checked before starting | A checklist at the top forces all items into mind at once; sequential prose lets later items slip. |
| **End self-check** | The output must meet listed requirements | "Before finishing, confirm the following" forces a review pass instead of stopping at first draft. |
| **Trigger guard** | A reference must be read before a specific action | "Before doing Y, read X — and don't begin Y until you have." Plain "read X first" is weak (easy to defer); the blocking clause is what makes it hold. Unlike a gate, it binds to the action Y, so it fires wherever Y comes up, not at a fixed point in the flow. |
| **STOP condition** | The model over-reaches, gold-plates, or retries forever | An explicit halt bounds scope and runaway loops: "Fix only the failing test; don't refactor nearby code." / "Stop after 3 attempts and report." This guards the opposite failure from skipping — doing too much. |
| **Negative / anti-pattern** | A tempting wrong path exists | "Do NOT use X" / "Don't substitute Y" closes a wrong route a positive instruction leaves open. |

### Emphasis & structure (both families)

| Technique | When | Why it works |
|---|---|---|
| **Repeat the core (top + bottom)** | One critical point is buried in a long file | Stated at both ends, it survives long context. |
| **Spend emphasis sparingly** | Only one or two points must truly stand out | Bold/caps everywhere dulls fast. Save it for the one place it matters. |
| **If-then routing table** | Behavior branches on input type | A condition→action table cuts missed branches and ad-hoc guessing. |
| **Fixed output template** | The output format must be consistent | "Use this exact template" gives a shape to fill. |
| **Few-shot example (Input/Output)** | You want to show a transform or judgment | One good example teaches more than a paragraph of rules. |

> Note: well-written skills usually *demonstrate* these techniques without ever naming
> them. The value here is making them explicit — when to use each, and why — so you can
> apply them on purpose instead of by accident.

### Writing style

Lean beats thorough — every dead instruction dilutes the ones that matter, so keep only
what earns its place. Prefer the imperative.

---

## Step 6 — Review with fresh eyes

Drafting and reviewing are different modes. After the draft, come back to it as cold as
you can — read it top to bottom the way the model will, not the way you remember meaning
it. This
is when dead weight becomes visible — run this
checklist:

- Does the **description** state both what it does and when to use it, and match the
  invocation style chosen in step 1 (pushy for auto-trigger, plain for explicit-only)?
- Is the body **shaped to its type** — not a rigid step-list forced onto a judgment or
  reference skill, nor a loose-prose workflow whose steps will get skipped?
- For workflow skills: are the must-not-skip points held by a **gate or checklist**,
  not just a hope?
- Was every **exact** string (API name, CLI flag, signature, config key) confirmed from
  documentation rather than written from memory?
- If the skill **splits into side files** (`references/`, `scripts/`): is each one
  actually pointed to from the body (one level deep, not via another reference file), and
  does it read cleanly on its own without contradicting `SKILL.md`?

---

## Step 7 — Independent review (subagent)

Your own pass in step 6 is limited: you wrote the skill, so you can't fully un-know what
you meant, and the gaps your own words quietly paper over stay invisible to you. A fresh
subagent has none of that context. If subagents are available, spend one on a cold read —
it catches what self-review structurally can't.

The review prompt lives in `references/independent-review-prompt.md` — point the subagent at
it rather than retyping it (a hand-copied prompt drifts). Spawn it with just:

```
Your complete instructions are in <abs-path>/references/independent-review-prompt.md.
Read that file fully and follow it. The SKILL.md under review is at <path>. Its purpose is:
<one line>.
```

Then **you decide**. Not every flag deserves a fix — a nitpick that adds words back is
worth rejecting, and reviewers tend to over-report. Apply the ones that genuinely improve
clarity or correctness, note why you skipped the rest, and keep the skill lean.
