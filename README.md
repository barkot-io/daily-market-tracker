# Daily Market Tracker Pipeline

An automated data extraction and normalization engine built with Python and GitHub Actions.

## Architecture
- **Source:** Open Exchange Rates API
- **Ingestion & Transform:** Python 3.11 (`requests`, `pytest`)
- **Storage:** Deduplicated CSV time-series
- **Automation:** GitHub Actions cron trigger running daily at 06:00 UTC

## Local Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
python main.py