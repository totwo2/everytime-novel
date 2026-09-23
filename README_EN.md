# everytime-novel — A Full-Pipeline Web-Novel Writing System

English | [简体中文](README.md)

> **A writing system that keeps AI from falling apart on long novels.** Three things ruin a long
> web novel: the characters drift by chapter 50, the plot contradicts itself, and every page
> reeks of AI. This system splits writing into a plan-first, two-phase pipeline —
> the outline and chapter beats must pass an audit before a single page of prose is written,
> and every batch of chapters then goes through a 20-dimension audit.
> The de-AI-tone pass can be held to while drafting or run separately afterwards — it is not
> welded to the writing flow and can be detached and used on its own at any time.

## What it watches for you

| What goes wrong in a long novel | What this system does |
|---|---|
| Foreshadowing planted and then forgotten | Every thread is tagged with its plant/payoff point during outlining, and the audit checks them one by one |
| Character names, skill names, money tiers drift as you write | `设定.md` (the setting file) is the single source of truth for names; the writer stops rather than inventing one; money chains and item chains are reconciled chapter by chapter |
| "仿佛" / "骤然" / "与此同时" on every page | 50+ banned words with zero tolerance, caps on 7 high-frequency sentence patterns, plus three targeted audits: sentence-pattern density, template-paragraph fingerprint, and filler chapters |
| The outline only covers the first few dozen chapters, then it collapses | Outline completeness check: if the number of chapter beats does not match the planned chapter count, writing is blocked outright |
| Chapters do not join up | The writer reads the full previous chapter plus this chapter's beats before starting, advancing serially with no gaps |
| The whole manuscript sounds like AI | De-AI-tone is couplable or standalone: hold the language bans while writing, then run scripts to clean punctuation and scan at the passage level; only the style changes, never the plot or characters |
| No way to tell whether the AI tone is gone | A bundled checker reports rule number and line number per hit — no "does it read like AI" guesswork |

None of this is a paper design: the author wrote a full web novel with it — 495 chapters of
《听说这棍能擀面？》 — and the pitfalls hit along the way became 52 lessons shipped with the pack
(`lessons.md`).

## 30-second start

```bash
skillhub install everytime-novel
```

(`skillhub` is the skill-marketplace CLI. If you already installed it, skip this and just say the
line below to your AI.)

Then say one sentence to your AI:

```
我要写一本都市小说
```

## How to confirm it installed

The AI will not start writing immediately. It will first confirm the setting with you item by item —
worldview, protagonist, the "cheat", the rules — writing each confirmed item straight into `设定.md`.
Seeing that happen means it is installed.

If it starts writing without asking about the setting, it did not install: run `skillhub list` and
check whether `everytime-novel` is there.

## Four entry points — pick up wherever you are

| Your situation | Say to the AI | What it does |
|---|---|---|
| You only have an idea | "我要写一本 XX 小说" | Talks the setting through with you → outline → volume outline → all chapter beats → audits them, and only starts writing after you approve |
| You already have chapter beats | "从 ch111 开始写" | Writes prose in batches; each batch is audited and fixed before the next begins |
| You have a pile of drafts | "对 vol02 去 AI 味" | Runs the checker to locate hits first; if everything is green it changes not a single word; only hits are edited, output to `deaid/`, plot and characters untouched |
| The whole book is written | "审查全书" | Audits all 20 dimensions volume by volume, then cross-volume checks (contradictions, foreshadowing, timeline) |
| You want the AI to learn your voice | "定风格 DNA" | Distils a language fingerprint from ≥20 of your own chapters, then writes to your sentence rhythm (optional — it will not do this unless asked) |

## Core mechanism: two-phase batch mode

```
Planning phase (all of it must finish before drafting starts):
  volume outline → beat batch 1 → beat batch 2 → … → all beats ready → beat audit

Drafting phase (prose written batch by batch):
  prose batch 1 → audit → fix → prose batch 2 → audit → …
```

One phase is one story arc in the volume outline, roughly 15–20 chapters. On a 1M-context model
one phase is about 87,500 tokens, which fits.

### What the writer reads per chapter

| Reads | Why |
|---|---|
| This chapter's beats (state / events / foreshadowing / prohibitions blocks) | The basis for executing plot beats, state changes and foreshadowing actions |
| The full previous chapter | Continuity: position, time, mood and held items all carry over |
| A setting summary (dispatched with the writer instruction) | Real character names and key setting facts |

The audit then checks the prose item by item against the original `设定.md` (character table,
skills, rules, foreshadowing list) and the beats.

### Two audit layers

| Layer | When | What it checks |
|---|---|---|
| Beat audit | Planning phase | Whether skills/characters exist in the setting library, foreshadowing closure, place specificity, character entrance and foreshadowing-payoff timing |
| Prose audit | After each batch | 20 dimensions: money chain, item chain, scene continuity, pronouns, foreshadowing, sentence-pattern density, template-paragraph fingerprint, filler chapters, three-level character-name consistency, de-AI-tone script scan, … |

### De-AI-tone: couplable, or standalone

It is not "a finishing step you must run at the end" — it is a **capability you can take apart**.
Both uses are valid:

| How you use it | What you get |
|---|---|
| **Coupled into writing** | The writer holds the language bans from the first word, so no AI tone is produced in the first place and an entire rework round is saved |
| **Standalone run** | Drop in a finished draft: it takes prose in and gives de-AI-toned prose out, changing not one word of plot or character |

When coupled into writing, work is layered by "how expensive is this to fix", with no pointless rewriting:

| Layer | When | What |
|---|---|---|
| Language | While writing | Banned words, sentence-pattern caps, opening formulas, enumeration commas, metaphors — the writer holds these live |
| Symbols | After writing | Em dashes, ellipsis formatting, punctuation consistency — script-located, replaced one by one |
| Passage | After writing | Adjacent-sentence isomorphism, paragraph-opening zero-anaphora — invisible while writing, counted by script |
| On-demand patching | Only if the above reports hits | A subagent edits, and only the hit spots; everything unmatched is kept word for word |

**You can use it without writing a novel at all.** `scripts/check_ai_tone.py` is a standalone checker
that runs on any Chinese text; it prints rule number + line number, reads only and never modifies your
files. If everything is green there is nothing to do — it turns a "requirement" into a "fact".

## Project directory conventions

```
project root/
├── drafts/volXX/chXXX_draft.md     # prose drafts
├── settings/
│   ├── 设定.md                     # authoritative source: characters, skills, rules, foreshadowing list
│   ├── 本书语言DNA.md              # writing-truth file (optional; exists only if DNA was distilled)
│   ├── 大纲.md
│   └── 卷纲_volXX.md
├── dna-corpus/                     # style-distillation corpus (optional, ≥20 human-written chapters)
├── chapters/volXX/chXXX.md         # chapter beats
├── deaid/volXX/                    # de-AI-tone output
├── reports/                        # audit and cross-volume reports
└── PROGRESS.md
```

## It ships with two scripts

| Script | What it does | Self-test |
|---|---|---|
| `scripts/check_ai_tone.py` | Scans 14 AI-tone rules, prints rule number + line number + snippet | `--test` 16/16 pass |
| `scripts/distill_dna.py` | Computes language fingerprint: dialogue share, sentence length, paragraph rhythm, punctuation, modal particles, chapter-opening/closing types | `--test` 11/11 pass |

Both are pure local scripts — read-only, no network — and can be run on their own at any time.

## When not to use it

- **Short stories / single chapters**: its value is in novels of dozens of chapters or more — the beat
  gate and cross-volume review show nothing at small chapter counts.
- **You already have a draft you like and only want the style changed**: a standalone de-AI-tone run is
  enough; there is no need for the whole pipeline.
- **You want it to invent the plot for you**: it manages "do not fall apart", not "come up with a good
  story". The setting and outline are still yours to decide.

## Where the experience comes from

- 495 chapters of 《听说这棍能擀面？》 in practice: batch-by-phase mode and cross-volume review were both
  proven on this book
- A whole-book quality-review pass: pronoun repair, format unification, cross-volume auxiliary forms
- 52 pitfall records (`lessons.md`) shipped with the pack; most audit rules come from real failures

Current version: v1.4.0
