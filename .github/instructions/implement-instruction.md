---
title: Implement Project — Step-by-step Instructions
description: Detailed implementation workflow for contributors and agents.
---

# Implement: Step-by-step Instructions

Purpose: provide a concise, repeatable workflow to implement features
and deliver a working, tested project. Follow these stages in order.

1. Plan

- Review the project goals and the current repo state.
- Create a short implementation plan with checkpoints and acceptance
  criteria for each change.
- Open an issue or create a feature branch for the work and list the
  target files.

2. Implement

- Make minimal, focused changes to the codebase.
- Prefer small, testable commits and keep changes scoped.
- Use `apply_patch` for edits and include docstrings and type hints.
- Update `requirements.txt` when adding dependencies.

3. Test the whole project

- Run unit tests and integration checks.
- Manually run core flows: CSV load, schema detection, one-response
  generation, and (if configured) a dry-run of the form filler.
- Save generated artifacts to `data/` for traceability.

4. Refactor and check for errors

- Fix style and structural issues discovered during testing.
- Run static checks: type checking (`mypy`), linter (`ruff`),
  and formatter (`black`).
- Add or extend tests to cover newly discovered edge cases.

5. Test the whole project again

- Repeat the full test suite and manual integration flows.
- Verify outputs (cleaned CSV, schema JSON, probability model,
  generated responses) are produced and valid.

Acceptance criteria for an implementation cycle

- All tests pass locally.
- Core flows run end-to-end without uncaught exceptions.
- Changes are documented and committed in small, logical units.

Recommended commands (copyable)

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
mypy src
ruff check .
black --check .
```

Notes for agents

- Use the companion prompt at `.github/prompts/implement-prompt.md` to
  execute the implement workflow interactively.
- Use the companion prompt to run each stage and report results at each checkpoint.
