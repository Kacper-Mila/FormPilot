# FormPilot

FormPilot is a modular Python application that learns answer patterns
from completed survey CSV datasets, generates synthetic but
statistically coherent survey responses, and automatically fills Google
Forms using Playwright.

The project is designed for: - Polish-language surveys - probabilistic
synthetic response generation - robust Google Forms browser automation -
repeatable multi-submission workflows - clean logging and debugging -
modular MVP-first development

------------------------------------------------------------------------

## Overview

The system follows a practical architecture optimized for small and
medium datasets (for example, 80 completed surveys):

1.  Load completed survey CSV data
2.  Clean and normalize responses
3.  Detect schema and question types
4.  Learn answer distributions and dependencies
5.  Generate one synthetic respondent
6.  Parse Google Form structure
7.  Fill and submit the form automatically
8.  Repeat for N submissions

Instead of overengineering a full machine learning pipeline, FormPilot
uses a probability-driven generator that is easier to control, easier to
debug, and better suited to survey-style tabular data.

------------------------------------------------------------------------

## Features

### Data Pipeline

-   CSV loading with Polish encoding support
-   delimiter auto-detection
-   column normalization
-   repeated label standardization
-   missing value handling
-   cleaned CSV export

### Schema Understanding

-   single-choice detection
-   multi-select detection
-   Likert / scale detection
-   short and long text detection
-   optional field detection
-   reusable schema JSON export

### Statistical Response Generator

-   marginal probability tables
-   conditional dependencies
-   answer consistency rules
-   persona support
-   controlled randomness
-   duplicate prevention

### Google Forms Automation

-   Playwright browser automation
-   visible field parsing
-   radio buttons
-   checkboxes
-   dropdowns
-   short answer
-   paragraph fields
-   linear scales
-   multi-page navigation
-   automatic submission
-   screenshot on failure

### Logging and Traceability

-   generated responses CSV
-   submission logs
-   schema export
-   probability model export
-   failure screenshots
-   per-run debugging metadata

------------------------------------------------------------------------

## Project Structure

``` text
FormPilot/
│
├── data/
│   ├── input_surveys.csv
│   ├── cleaned_surveys.csv
│   └── generated_responses.csv
│
├── src/
│   ├── data_loader.py
│   ├── data_cleaner.py
│   ├── schema_detector.py
│   ├── probability_model.py
│   ├── persona_generator.py
│   ├── response_generator.py
│   ├── form_parser.py
│   ├── form_mapper.py
│   ├── google_form_filler.py
│   ├── submission_runner.py
│   ├── logger.py
│   └── main.py
│
├── config/
│   └── settings.yaml
│
├── logs/
│   └── submissions.log
│
├── requirements.txt
└── README.md
```

------------------------------------------------------------------------

## Installation

### Clone the repository

``` bash
git clone https://github.com/your-username/formpilot.git
cd formpilot
```

### Create virtual environment

``` bash
python -m venv .venv
source .venv/bin/activate
```

### Windows

``` bash
.venv\Scripts\activate
```

### Install dependencies

``` bash
pip install -r requirements.txt
playwright install
```

------------------------------------------------------------------------

## Requirements

-   Python 3.11+
-   pandas
-   numpy
-   Playwright
-   PyYAML
-   pydantic (optional)
-   scikit-learn (optional)

------------------------------------------------------------------------

## Usage

### CLI example

``` bash
python src/main.py \
    --csv data/input_surveys.csv \
    --form "https://docs.google.com/forms/..." \
    --count 25 \
    --headless \
    --config config/settings.yaml
```

### Arguments

-   `--csv` : path to source CSV
-   `--form` : Google Form URL
-   `--count` : number of submissions
-   `--config` : YAML config path
-   `--headless` : run Playwright without a visible browser window
-   `--headed` : force a visible browser window for debugging
-   `--timeout-ms` : Playwright page/action timeout in milliseconds
-   `--action-delay-ms` : small delay after field actions; lower is faster
-   `--list-personas` : print available personas
-   `--generate-response` : print one generated sample response
-   `--persona-mode` : choose `weighted` or `uniform` persona selection
-   `--seed` : set a random seed for reproducible generation

Terminal arguments override matching values from `config/settings.yaml` for
that run. For example, `--headless` overrides `automation.headless`, and
`--csv` overrides `paths.csv_path`.

### Settings

`app.name` is the application name used for configuration readability.

`app.log_level` controls log verbosity. Common values are `DEBUG`, `INFO`,
`WARNING`, and `ERROR`.

`automation.headless` controls whether Playwright runs without a visible browser
window. It is overridden by `--headless` or `--headed`.

`automation.timeout_ms` is the browser/page timeout in milliseconds. It is
overridden by `--timeout-ms`.

`automation.action_delay_ms` is the small pause after field actions. Lower
values are faster; higher values can help with slow forms. It is overridden by
`--action-delay-ms`.

`automation.retry_failed_submissions` enables retrying the same generated
response when a form submission attempt fails.

`automation.max_submission_retries` sets how many extra attempts are allowed
after the first failed attempt. For example, `1` means one retry, so two total
attempts.

`automation.stop_on_error` stops the batch after a response still fails once all
configured retries are exhausted.

`cleaning.drop_timestamp_columns` removes timestamp-like CSV columns before
schema/model generation.

`cleaning.timestamp_patterns` lists case-insensitive column-name fragments that
should be treated as timestamps.

`paths.csv_path` is the default input CSV path. It is overridden by `--csv`.

`paths.data_dir` is the project data folder reference.

`paths.cleaned_data` is where the cleaned CSV is written.

`paths.generated_responses` is where generated responses from the current batch
are written. This file is cleared at the start of each submission run.

`paths.logs_dir` is where log files are written.

`paths.schema_export` is where the detected survey schema is written, and where
the CLI looks for an existing schema if no CSV is supplied.

`paths.model_export` is where the probability model is written, and where it is
loaded from when submissions run without rebuilding from CSV.

`paths.form_schema_export` is where the parsed Google Form schema is written.

`paths.mapping_export` is where the schema-to-form mapping table is written.

`persona.list_personas` prints available personas when set to `true`.
`--list-personas` can also enable this for one run.

`persona.generate_response` prints one generated sample response when set to
`true`. `--generate-response` can also enable this for one run.

`persona.mode` chooses persona selection mode: `weighted` or `uniform`. It is
overridden by `--persona-mode`.

`persona.seed` sets the default random seed. `null` means non-deterministic
sampling. It is overridden by `--seed`.

------------------------------------------------------------------------

## Core Modules

### `data_loader.py`

Loads CSV files safely with encoding validation and delimiter detection.

### `data_cleaner.py`

Normalizes labels, handles nulls, and exports cleaned datasets.

### `schema_detector.py`

Infers question types and builds reusable schema definitions.

### `probability_model.py`

Learns answer distributions and simple dependencies.

### `persona_generator.py`

Defines optional respondent personas for weighted generation.

### `response_generator.py`

Builds one coherent synthetic respondent at a time.

### `form_parser.py`

Reads Google Form structure and visible question blocks.

### `form_mapper.py`

Maps CSV schema to Google Form labels using fuzzy Polish matching.

### `google_form_filler.py`

Controls Playwright automation and performs submission.

### `submission_runner.py`

Repeats generate → fill → submit workflow N times.

### `main.py`

CLI entrypoint for the complete pipeline.

------------------------------------------------------------------------

## Design Principles

FormPilot prioritizes: - reliability over complexity - modular
architecture - Polish text robustness - reproducible outputs - easy
debugging - incremental one-file-at-a-time development

For small survey datasets, this probability-based architecture is
typically more maintainable than training a heavy ML model.

------------------------------------------------------------------------

## License

MIT License
