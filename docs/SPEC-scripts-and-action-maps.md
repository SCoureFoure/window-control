# Spec (draft): goals files, action maps, and scripts

Status: **APPROVED 2026-07-23 — Leader adopted Feature A and amended the charter for
B2 + C (full scripts).** The amendment text lives in `CLAUDE.md` → "What this project
is NOT". Path B1 (map hints to the model) remains rejected. Written 2026-07-23 at the Leader's
request to spec two ideas: (1) a reusable "script entry" surface, and (2) a stored
"button grid" / action map tied to a lens. This document exists to surface the design
choices — especially where they collide with the charter — so the Leader can decide
scope before any code is written.

Read `CLAUDE.md` first. Three clauses govern everything below:

- **§3 Vision-first:** the only signal Claude receives about the lens is rendered pixels.
  No accessibility tree, no DOM, **no non-pixel hints.**
- **§4 Grid is a perception aid,** not a functional element.
- **"What this is NOT":** *Not an RPA platform. No flow designer, no scheduler,
  **no record-and-replay.***

The two requested features sit on different sides of those lines. This spec keeps them
separate so they can be adopted (or rejected) independently.

---

## Feature A — Goals file (IN-BOUNDS)

A named collection of natural-language goal strings you pick from at launch, so you
don't retype prompts. **Every run still goes through the full vision loop** — this is
just saved prompts, not replay. Nothing here touches §3 or the RPA non-goal.

### Storage
`~/.window-control/goals.json`
```json
{
  "uma-open-options": "click the Options icon",
  "uma-daily-race":   "start today's daily race and confirm",
  "notepad-hello":    "type the word hello"
}
```

### CLI
```
python -m src.orchestrator --goal-name uma-open-options --lens uma
python -m src.orchestrator --list-goals
```
`--goal-name X` looks up `X` in `goals.json` and runs it exactly as if typed. Mutually
exclusive with the positional `goal`. No new run semantics — one lookup, then the
existing loop.

### Cost / risk
Trivial. One loader module (`src/goals/store.py`), two CLI flags. No invariant impact.
This is the safe floor if the Leader wants *something* reusable now.

---

## Feature B — Action map / "button grid" (OUT OF CHARTER as replay; two paths)

A per-lens table mapping a **name** to a **lens-relative** coordinate or rect, e.g.
`settings -> (1043, 256)`. The appeal: reference `settings` instead of raw coords or a
vision round-trip. The problem: *how* the name is used decides whether it's legal.

### Storage (same for both paths)
`~/.window-control/actionmaps/<lens>.json`
```json
{
  "lens": "uma",
  "buttons": {
    "settings": {"point": [1043, 256]},
    "back":     {"rect": [0, 0, 80, 80]}
  }
}
```
Coordinates are **lens-relative** (model space). Resolution to screen-absolute happens
only at the `coords.py` boundary (per the two-coordinate-spaces rule). A `rect` taps its
center. Populated either by the human (click-to-name during an extended overlay editor)
or promoted from a successful vision run's chosen coordinate.

### Path B1 — feed the map to the model as a hint  ❌ REJECTED
"Tell Claude the settings button is near (1043, 256)." This injects a **non-pixel signal**
into perception → **direct violation of §3.** Do not build. Listed only to close the door.

### Path B2 — deterministic tap, no model  ⚠️ NEEDS INVARIANT AMENDMENT
`tap settings` resolves the name → lens-rel point → `coords.to_screen` → `backend.click`,
**without calling Claude at all.** This does not violate §3 (Claude receives nothing —
Claude isn't in the loop for that action). But a stored coordinate replayed on command
**is record-and-replay**, which the "What this is NOT" section explicitly rules out.

So B2 is technically clean w.r.t. vision-first, but breaks the RPA/replay non-goal. It is
adoptable **only** with a written charter amendment (see "Decision points").

**Framing that could justify an amendment:** the action map is an *optional, per-lens,
user-curated shortcut cache* — an "action aid" that extends §4's "perception aid" idea.
Vision remains the only mode for unknown UIs and the default everywhere; the map is a
convenience for buttons the human has already confirmed. It still never binds an HWND
(§1) and still emits only OS-level input (§2). The honest cost: the project gains a
deterministic execution mode it currently, deliberately, does not have.

---

## Feature C — Scripts (a flow; NEEDS INVARIANT AMENDMENT)

A named, ordered sequence of steps. Each step is **either** a vision-loop goal **or** a
deterministic action (only available if Feature B2 is adopted).

### Storage
`~/.window-control/scripts/<name>.yaml`
```yaml
name: uma-daily
lens: uma
steps:
  - goal: "click the Options icon"     # runs the full vision loop until DONE/IMPOSSIBLE
  - tap: settings                       # deterministic (requires action map + B2)
  - type: "hello"                       # deterministic
  - wait: 1.0
  - swipe: {from: back, to: home, duration: 0.3}
```

A `goal:` step is in-bounds on its own (it's just a saved prompt run through the loop).
A script that is **only** `goal:` steps is a "goal playlist" — still arguably a *flow
designer*, but with no replay and no stored coordinates. A script that mixes in `tap/
type/swipe` steps is full record-and-replay.

### Runner
`src/scripts/runner.py` iterates steps: `goal` → call `orchestrator.run`; deterministic
step → resolve against the action map and dispatch through the existing `InputBackend`
(no new input path — reuses `action.py`/`desktop.py`). Per-step and per-script `--max-steps`.
Honors the access border (`acting` during deterministic steps too).

### Cost / risk
Largest surface. New `scripts/` package, YAML dep, a step schema, and it most squarely
lands in "no flow designer." Only proceed with an explicit amendment.

---

## Decision points for the Leader

1. **Adopt Feature A (goals file) now?** In-bounds, cheap, independently useful. Recommended
   yes regardless of the rest.
2. **Amend `CLAUDE.md` "What this is NOT" to permit a deterministic replay layer?**
   - If **no** → B2 and C are dead; stop at A.
   - If **yes** → we add a written justification to the charter (the "action aid" framing
     above), then B2 and C become buildable.
3. **If amending, how far?**
   - B2 only (named deterministic taps, invoked one at a time) — smaller identity shift.
   - B2 + C (full scripts) — full mini-RPA.

## Recommended phasing (contingent on decisions)

1. **Phase 1 (no amendment):** ship Feature A. Reuse without touching the charter.
2. **Phase 2 (if amended):** action map storage + `--edit-buttons` click-to-name in the
   overlay + `tap NAME` one-shot command (B2). Prove deterministic dispatch through the
   existing backend.
3. **Phase 3 (if amended):** script runner (C) over the Phase-2 primitives.

Each phase is independently verifiable (its own tests: goals loader, action-map resolve
+ bounds-check, script step dispatch) and disjoint in files — so each is a clean horde
slice when/if approved.

---

**No code until the Leader answers Decision points 1–3.** This file is the artifact of
"spec both now, decide later."
