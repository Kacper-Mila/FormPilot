# FormPilot Copilot Instructions

FormPilot is a modular Python 3.14+ application for Polish survey CSV analysis, synthetic response generation, and Google Form automation with Playwright.

## Project Goals

- Load completed survey CSV files safely, including Polish text and common CSV encodings.
- Clean and normalize survey data before analysis.
- Infer a reusable survey schema from the dataset.
- Learn answer distributions and simple dependencies.
- Generate one coherent synthetic respondent at a time.
- Parse Google Forms, map form questions to dataset schema, and automate submission.
- Repeat the generate -> fill -> submit workflow for a user-defined number of runs.

## Core Design Principles

- Prefer a probability-driven approach over heavy machine learning for the MVP.
- Keep the architecture modular so each module can evolve independently.
- Optimize for reliability, traceability, and debugging.
- Preserve Polish characters and Unicode-safe behavior end to end.
- Favor small, testable changes over large cross-cutting rewrites.

## Implementation Order

When building or extending the project, prefer this sequence:

1. `src/logger.py`
2. `src/data_loader.py`
3. `src/data_cleaner.py`
4. `src/schema_detector.py`
5. `src/probability_model.py`
6. `src/persona_generator.py`
7. `src/response_generator.py`
8. `src/form_parser.py`
9. `src/form_mapper.py`
10. `src/google_form_filler.py`
11. `src/submission_runner.py`
12. `src/main.py`

Do not try to generate the entire system at once unless explicitly requested. Build and validate one module at a time.

## Data Handling Rules

- Support UTF-8 and other common Polish CSV encodings.
- Auto-detect delimiters when possible.
- Normalize column names and repeated labels consistently.
- Treat empty strings as missing values.
- Save cleaned data to `data/cleaned_surveys.csv`.
- Keep generated responses and model artifacts available for debugging and traceability.

## Schema and Modeling Rules

- Classify every column into a usable survey field type.
- Support single-choice, multi-select, Likert/scale, short text, long text, and optional fields.
- Learn marginal probabilities first, then simple conditional dependencies.
- Keep probability tables inspectable and reusable by downstream modules.
- Use persona logic only as a controlled layer on top of the statistical model.

## Form Automation Rules

- Use Playwright for browser automation.
- Handle radio buttons, checkboxes, dropdowns, short answers, paragraph answers, scales, and multi-page navigation.
- Detect visible question blocks and section/page structure before filling.
- Save screenshots and logs when automation fails.
- Flag unmatched or low-confidence mappings instead of guessing silently.

## Coding Preferences

- Use clear type hints and docstrings for public functions and classes.
- Keep functions small and focused.
- Prefer explicit error handling with helpful messages.
- Avoid unnecessary complexity, abstractions, or premature optimization.
- Preserve existing style and public APIs unless a change is required.

## Output and Debugging Expectations

- Save intermediate artifacts when they help explain behavior: cleaned CSVs, schema JSON, learned probability tables, generated response rows, logs, and failure screenshots.
- Make failures easy to inspect and recover from.
- If a requirement is ambiguous, infer the safest MVP-friendly interpretation from the project docs before expanding scope.
