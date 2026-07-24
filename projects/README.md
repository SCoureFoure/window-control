# Project trees

A **project** is a folder of scripts and button maps for one app/game, run with:

```
python -m src.scripts.runner <project>/<task>/<script>     # path form
python -m src.scripts.runner <script>                      # bare name, if unique
python -m src.scripts.runner --list
```

Everything in this directory is gitignored **except** `example/` — copy it to start
your own project:

```
projects/
  my-game/
    project.yaml          # REQUIRED: lens binding (+ optional defaults)
    buttons.json          # optional: buttons shared by the whole project
    scripts/              # optional: shared scripts, callable via `run:` from any task
    some-task/
      buttons.json        # optional: task-specific buttons (override parent names)
      some-script.yaml
```

Rules (full design: `docs/SPEC-project-tree.md`):

- **Lens** is set once, in the root `project.yaml`. Tree scripts must not set `lens:`.
- **Buttons** resolve nearest-wins: a script in `some-task/` checks
  `some-task/buttons.json` first, then each ancestor up to the project root. A child
  entry with the same name overrides the parent's.
- **`run:` targets** resolve through ancestors' `scripts/` folders only, nearest first.
  A shared script resolves *its* buttons from its own folder (the project root), no
  matter who calls it.
- **Coordinates are lens-relative** (0,0 = lens top-left). Harvest them from a vision
  run's `runs/<ts>/trace.jsonl` + step screenshots, or measure on a capture.
- Step types: `tap`, `type`, `wait`, `swipe`, `key`, `scroll`, `run`, `goal`
  (`goal:` runs the full vision loop and costs API credits; the rest are free and
  deterministic).
