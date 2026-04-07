# FormPilot Copilot Instructions

FormPilot is a modular Python 3.14+ application for Polish survey CSV analysis, synthetic response generation, and Google Form automation with Playwright.

## Project Goals

- Load completed survey CSV files safely, including Polish text and common CSV encodings.
- Clean and normalize survey data before analysis.
- Infer a reusable survey schema from the dataset.
- Learn answer distributions and lightweight dependencies.
- Generate one coherent synthetic respondent at a time.
- Parse Google Forms, map form questions to dataset schema, and automate submission.
- Repeat the generate → fill → submit workflow for a user-defined number of runs.

## Core Design Principles

- Prefer a probability-driven statistical approach over heavy machine learning for the MVP.
- Keep the architecture modular so each module can evolve independently.
- Optimize for reliability, traceability, and debugging.
- Preserve Polish characters and Unicode-safe behavior end to end.
- Favor small, testable changes over large cross-cutting rewrites.
- Use explicit internal data contracts between modules.

## Required Internal Models

Prefer `dataclasses` or `pydantic` models for stable interfaces.

Core models:
- `SurveySchema`
- `GeneratedResponse`
- `FormQuestion`
- `MappingEntry`

Do not pass loosely structured dictionaries between major modules unless explicitly required.

## Implementation Order

Build and validate modules in this sequence:

1. `src/logger.py`
2. `src/data_loader.py`
3. `src/data_cleaner.py`
4. `src/schema_detector.py`
5. `src/probability_model.py`
6. `src/response_generator.py`
7. `src/form_parser.py`
8. `src/form_mapper.py`
9. `src/google_form_filler.py`
10. `src/submission_runner.py`
11. `src/main.py`

Optional after validation:
12. `src/persona_generator.py`

Do not generate the full system at once unless explicitly requested.

## Configuration Rules

Centralize runtime settings in:

`config/settings.yaml`

Supported config options:
- CSV path
- Google Form URL
- submission count
- headless mode
- retry count
- Playwright delays
- output paths
- logging level
- screenshot path
- duplicate prevention threshold

Do not hardcode runtime constants inside feature modules.

## Data Handling Rules

- Support UTF-8 and common Polish CSV encodings.
- Auto-detect delimiters when possible.
- Normalize column names and repeated labels consistently.
- Treat empty strings as missing values.
- Save cleaned data to `data/cleaned_surveys.csv`.
- Preserve generated responses and model artifacts for debugging.
- Never lose Polish diacritics.

## Schema and Modeling Rules

- Classify every column into a usable survey field type.
- Support:
  - single-choice
  - multi-select
  - Likert / scale
  - short text
  - long text
  - optional fields
- Learn marginal probabilities first.
- Add simple conditional dependencies second.
- Keep probability tables inspectable and reusable.

## Response Generation Rules

- Generate one full respondent per run.
- Generate anchor variables first.
- Generate dependent answers second.
- Validate final answer consistency.
- Avoid exact duplicates.
- Add controlled randomness without breaking dependencies.
- Save generated rows for traceability.

## Form Automation Rules

- Use Playwright for browser automation.
- Detect visible question blocks before filling.
- Handle:
  - radio buttons
  - checkboxes
  - dropdowns
  - short answers
  - paragraph answers
  - scales
  - multi-page navigation
- Wait explicitly for visible interactive elements.
- Save screenshots and logs on failure.
- Flag unmatched or low-confidence mappings instead of guessing silently.

## Coding Preferences

- Use strong type hints.
- Add docstrings for public APIs.
- Keep functions small and focused.
- Prefer explicit exceptions with actionable messages.
- Preserve existing public interfaces unless refactoring is necessary.
- Avoid premature abstraction.

## Output and Debugging Expectations

Persist useful artifacts:
- cleaned CSV
- schema JSON
- probability tables
- generated responses
- submission logs
- failure screenshots

Failures must be easy to inspect and replay.

If a requirement is ambiguous, choose the safest MVP-friendly interpretation from the project documentation before expanding scope.