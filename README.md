# Sprout 🌱

Open-source recurring-payments automation for [Beancount](https://beancount.github.io/).

Define recurring payments (subscriptions, loan repayments, rent), review what's due in an inbox, tune each occurrence, and write **real, editable** Beancount transactions — not virtual plugin entries.

## Features
- Schedules: create recurring payments (interval, anchor date, end conditions).
- Inbox: review due occurrences, edit amount/date/narration inline, see a live `.bean` preview, confirm or skip.
- Real writes: validated against your ledger, appended atomically, stamped with a `sprout-id` for idempotency.
- Settings: configure your ledger path and write mode.

## Run with Docker (recommended)
```bash
# Put your ledger in ./ledger (main file at ./ledger/main.bean), then:
docker compose up --build
# open http://localhost:8000
```
The single image serves both the API and the web UI on port 8000. The SQLite DB persists in the `sprout-data` volume.

## Development
Backend:
```bash
cd backend
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest
uvicorn app.main:app --reload   # API on http://localhost:8000
```
Frontend:
```bash
cd frontend
npm install
npm run dev      # Vite dev server on http://localhost:5173, proxies /api to :8000
npm run test     # vitest
npm run build    # production build into dist/
```

## Configuration
See `.env.example`. Key vars: `SPROUT_LEDGER_MAIN_FILE`, `SPROUT_LEDGER_ROOT`, `SPROUT_WRITE_MODE` (`single_file` | `month_file`), `SPROUT_DB_PATH`.

## License
MIT
