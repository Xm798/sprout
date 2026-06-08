# Sprout 🌱

Open-source recurring-payments automation for [Beancount](https://beancount.github.io/).

Define recurring payments (subscriptions, loan repayments, rent), review what's due in an inbox, tune each occurrence, and write **real, editable** Beancount transactions — not virtual plugin entries.

## Status
Early development. Backend first.

## Development
```bash
cd backend
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest
uvicorn app.main:app --reload
```
