# Sprout 🌱

Open-source recurring-payments automation for [Beancount](https://beancount.github.io/).

Define recurring payments (subscriptions, loan repayments, rent), review what's due in an inbox, tune each occurrence, and write **real, editable** Beancount transactions — not virtual plugin entries.

## Features
- Schedules: create recurring payments (interval, anchor date, end conditions).
- Inbox: review due occurrences, edit amount/date/narration inline, see a live `.bean` preview, confirm or skip.
- Real writes: validated against your ledger, appended atomically, stamped with a `sprout-id` for idempotency.
- History: browse confirmed/skipped occurrences, detect written transactions that vanished from the ledger (manual edits), and re-add them.
- Settings: configure your ledger path and write mode.

## Run with Docker (recommended)
```bash
# Put your ledger in ./ledger (main file at ./ledger/main.bean), then:
docker compose up --build
# open http://localhost:8000
```
The single image serves both the API and the web UI on port 8000. The SQLite DB persists in the `sprout-data` volume.

### Postgres (optional)
The default backend is SQLite — no action needed. To use Postgres instead, set
`SPROUT_DATABASE_URL` (takes precedence over `SPROUT_DB_PATH`):
```bash
SPROUT_DATABASE_URL=postgresql+psycopg://USER:PASS@HOST:5432/DBNAME
```
With Docker Compose, layer the override file to bring up a bundled Postgres:
```bash
docker compose -f docker-compose.yml -f docker-compose.postgres.yml up --build
```
To run the test suite against Postgres, set `SPROUT_TEST_DATABASE_URL` before `pytest`:
```bash
SPROUT_TEST_DATABASE_URL=postgresql+psycopg://USER:PASS@HOST:5432/DBNAME pytest
```

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
See `.env.example`. Key vars: `SPROUT_LEDGER_MAIN_FILE`, `SPROUT_LEDGER_ROOT`, `SPROUT_WRITE_MODE` (`single_file` | `month_file`), `SPROUT_DB_PATH`, `SPROUT_DATABASE_URL` (Postgres; overrides `SPROUT_DB_PATH`).

## License
MIT
