---
name: brief
description: Turn any prompt — including 15+ request dictated dumps — into an ordered queue of top-0.1% briefs, then dispatch it. Use on every multi-ask, messy or dictated prompt, or when the user types /brief.
---

# Prompt upgrader + queue builder (from "How the top 0.1% use Claude — UAply edition")

The founders send big multi-ask prompts on purpose (time crunch). Don't push back on the format: split it.
Cost rule: the queue + briefs shown to the user stay under ~200 words. Clear one-ask prompts: print `BRIEF ✓`, go.

## Step 1 — Extract
List every distinct ask, including ones hidden in "also", "another thing", "and then". Number them.
Drop pure context sentences. Merge duplicates. Keep the user's words for names, numbers, card #s.

## Step 2 — Order (chronological by dependency)
1. Facts & research first (they change later decisions). Run in parallel.
2. Decisions the founder must make → batch into ONE question set, asked once.
3. Builds/edits that depend on 1–2. Independent ones in parallel; same-file ones in sequence.
4. Things that go out (send, post, merge, Trello writes the user asked for) — after previews, gated.
5. Answers/explanations last, in one summary.
Mark each item: owner (TPD-self / builder / writer / researcher / runner / reviewer), model, risk (fast/risky).

## Step 3 — Write each bot brief (0.1% shape; drop lines that add nothing)
```
ROLE: <hat from roles.md, one line>     GOAL: one-sentence outcome
CONTEXT: paths/branch/card # only — the bot can't see this chat
SCOPE OUT: what not to touch; unrelated issues → follow-up list
DONE WHEN: checkable finish line        RETURN: format + word cap
STOPS: no send/merge/live; stop after 2 failed attempts
```

## Fixes to apply while rewriting
- Adjectives ("be smart", "top 1%") → name the standard instead (WCAG AA, 375px, tests pass).
- "Keep going until it works" → a cap. "Screenshot everything" → text checks, one screenshot at the end.
- "Make it like X, send a test, then send to all" → three gated steps.
- "Estimate tokens/%" → point to the status line / `ccusage`; the model can't see the meter.
- Missing finish line → write one. Dictation: confirm numbers as digits; "you apply/aply" = UAply.

## Step 4 — Show and go
Print `QUEUE n items` with one line per item (order · owner · done-when). Start items 1+ immediately.
Wait for "go" only if an item sends, merges, deletes, pays, touches live, or the rewrite changed the meaning.
At the end: one summary in the order of the queue, then follow-ups the user didn't ask for (max 3).
