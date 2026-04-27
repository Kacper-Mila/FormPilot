---
title: implement — Run implement workflow interactively
description: Agent prompt to plan, implement, test, refactor, and re-test the project.
---

Command: implement

Prompt (for agent use):

You are executing the `implement` workflow. Perform these steps and report
results at each checkpoint. Use `apply_patch` to edit files.

1. Plan (record results)

- Summarize the goal for this implementation task in 3–6 bullets.
- List changed files you expect to touch and acceptance criteria.

2. Implement

- Make focused code changes using `apply_patch` only; avoid unrelated
  edits.
- Add or update tests that verify new behavior.
- After implementing, produce a brief changelog: files added/modified and
  short rationale for each change.

3. Test the whole project

- Run tests: `pytest -q`. Capture failing tests and stack traces.
- Run a manual smoke test of key flows: CSV load, schema detection,
  response generation. Describe the outputs and any anomalies.
- Upload required artifacts (test logs, sample generated row) in the
  agent response.
- If tests fail, stop and move to step 4.

4. Refactor and check for errors

- Address issues found during testing: fix code, add tests, or
  document known limitations.
- If the tooling is installed and configured in this repository, run type
  checking and linters: `mypy src`, `ruff check .`, `black --check .`,
  and fix reported issues.
- If any of these tools are unavailable or unconfigured, skip that check
  and explicitly report it as skipped due to missing tooling/configuration
  rather than failing the workflow.
- Run tests again locally and ensure all executed checks are green.

5. Test the whole project again

- Repeat `pytest -q` and manual smoke tests.
- Produce a final short report: the tasks completed, tests passing,
  commands used, and any remaining risks.

Output requirements

- At each major step, include concise bullets: actions taken, files
  modified (paths), test results (pass/fail), and next steps.
- Provide `apply_patch` diffs or commit-ready patches as part of the
  implementation artifacts.

Constraints and best practices

- Keep changes minimal and focused.
- Do not alter unrelated modules or reformats across many files.
- Preserve Polish text and Unicode-safe CSV handling throughout.
