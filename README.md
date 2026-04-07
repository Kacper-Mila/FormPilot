# Survey Response Generator + Google Forms Auto-Filler

A modular Python project that learns answer patterns from existing
**survey CSV datasets**, generates **synthetic but realistic
survey responses**, and automatically **fills Google Forms in the
browser using Playwright**.

The project is optimized for: - Polish-language surveys - probabilistic
synthetic response generation - Google Forms automation - repeatable
multi-submission workflows - robust debugging and logging

------------------------------------------------------------------------

#  Features

##  Data Learning Pipeline

-   Load completed survey CSV datasets
-   Full **Polish encoding support**
-   Auto-detect delimiters
-   Normalize column names and labels
-   Handle missing values
-   Detect survey schema automatically

##  Statistical Response Generator

Instead of heavy ML, the system uses: - marginal answer probabilities -
conditional dependencies - optional personas/clusters - controlled
randomness - duplicate prevention

This makes it ideal for **small-to-medium datasets (e.g. \~80
surveys)**.

##  Google Forms Automation

Using **Playwright**, the bot can: 
- open a Google Form 
- parse visible questions 
- map dataset columns to form labels 
- fill: 
    - radio buttons 
    - checkboxes 
    - dropdowns 
    - short text 
    - paragraph text 
    - linear scales 
- navigate multi-page sections 
- submit automatically 
- repeat for **N submissions**

##  Logging + Debugging

-   submission logs
-   generated response storage
-   schema JSON export
-   probability model export
-   screenshots on browser failures

------------------------------------------------------------------------

#  Project Structure

``` text
project/
├── data/
├── src/
├── config/
├── logs/
├── requirements.txt
└── README.md
```

#  Installation

``` bash
git clone https://github.com/your-username/polish-survey-generator.git
cd polish-survey-generator
python -m venv .venv
pip install -r requirements.txt
playwright install
```

#  Usage

``` bash
python src/main.py --csv data/input_surveys.csv --form "https://docs.google.com/forms/..." --count 25 --config config/settings.yaml
```

#  Workflow

1.  Load CSV
2.  Clean data
3.  Detect schema
4.  Learn probabilities
5.  Generate response
6.  Parse Google Form
7.  Fill and submit
8.  Repeat N times

# License

MIT
