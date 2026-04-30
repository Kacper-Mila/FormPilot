# FormPilot

FormPilot learns answer patterns from completed survey CSV files, generates
synthetic responses, maps them to Google Forms, and can fill forms through
Playwright. It is designed for English and Polish surveys, with conservative
defaults so real submissions require an explicit opt-in.

## What It Does

- Loads CSV files with delimiter and Polish encoding fallback.
- Cleans columns into stable ids while preserving original question text.
- Drops timestamp columns such as `Sygnatura czasowa`, `data`, and `godzina`
  before schema/model generation when configured.
- Detects question types, optional fields, simple conditional follow-ups, and
  answer options.
- Builds marginal and conditional probability models for synthetic responses.
- Parses Google Forms, including common radio, checkbox, dropdown, text,
  paragraph, scale, required, and multi-page controls.
- Exports a mapping review JSON before filling.
- Supports dry-run/no-submit filling and explicit submission mode.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m playwright install chromium
```

The package exposes both module and console entrypoints:

```bash
python -m src.main --help
formpilot --help
```

## Typical Workflow

Build local artifacts from a CSV:

```bash
formpilot --csv resources/form-data-set.csv --count 0 --headless
```

Generate one response for review:

```bash
formpilot --generate-response --seed 123
```

Parse a form and export the mapping report without submitting:

```bash
formpilot \
  --csv resources/form-data-set.csv \
  --form "https://docs.google.com/forms/..." \
  --count 0 \
  --headless
```

Dry-run filling/validation without submitting:

```bash
formpilot \
  --csv resources/form-data-set.csv \
  --form "https://docs.google.com/forms/..." \
  --count 1 \
  --dry-run \
  --headless
```

Submit only after reviewing the mapping and intentionally opting in:

```bash
formpilot \
  --csv resources/form-data-set.csv \
  --form "https://docs.google.com/forms/..." \
  --count 1 \
  --submit \
  --headless
```

Only submit to forms you own or have clear permission to test. Tests and CI do
not submit real Google Forms.

## Mapping Review

FormPilot writes `data/form_mapping.json` by default. Review it before using
`--submit`.

The report includes:

- accepted matched questions and confidence scores
- unmatched dataset questions
- unmatched form questions
- blocked required form questions
- low-confidence candidate matches
- answer option mapping issues

Low-confidence mappings are not used for filling unless
`mapping.allow_low_confidence_mappings` is set to `true`. Required form fields
without a reliable mapping block submission.

## Configuration

`config/settings.yaml` contains the default paths and safety settings.

Important options:

- `automation.dry_run`: default no-submit behavior.
- `automation.submit`: must be `true`, or use `--submit`, for real submission.
- `mapping.minimum_question_match_confidence`: minimum accepted question match.
- `mapping.minimum_option_match_confidence`: minimum accepted option match.
- `mapping.allow_low_confidence_mappings`: manual override for risky mappings.
- `locale.language`: `auto`, `pl`, or `en`.
- `cleaning.drop_timestamp_columns`: exclude timestamp-like CSV columns.
- `cleaning.timestamp_patterns`: timestamp column-name fragments.

CLI flags override config for a single run.

## Generated Artifacts

By default, generated runtime artifacts are written under `data/` and logs under
`logs/`:

- `data/cleaned_surveys.csv`
- `data/schema.json`
- `data/probability_model.json`
- `data/form_schema.json`
- `data/form_mapping.json`
- `data/generated_responses.csv`
- `logs/formpilot.log`

These are ignored by git unless you intentionally add fixtures.

## Development

Run the local checks:

```bash
pytest
ruff check .
mypy src
```

CI runs the same lint, type check, and test suite through GitHub Actions.
