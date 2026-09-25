# cmoAI — V1

AI Business Consultant: diagnoses a company's real growth bottleneck and,
only when marketing is genuinely the correct lever, generates an
evidence-based marketing strategy and PowerPoint presentation.

V1 is intentionally a **simple, modular monolith** — no multi-agent
frameworks, no knowledge graph, no vector DB, no memory system, no task
queues. One decision-maker (the Orchestrator), several dumb collector/
processing services, and SQLite for storage.

---

## Project Structure

```
cmoai/
├── main.py                  # local entrypoint (Brick 1: skeleton check only)
├── requirements.txt
├── .env.example              # copy to .env and fill in your keys
├── .gitignore
├── config/
│   ├── settings.py           # typed settings loaded from .env
│   └── logging_config.py     # console + rotating file logging setup
├── domain/                   # Pydantic models — the shared vocabulary
├── services/                 # collectors + small-LLM services (no reasoning)
├── orchestrator/             # the single reasoning/decision-making component
├── storage/                  # SQLite schema + repository layer
├── api/                      # HTTP layer (added in a later brick)
├── data/                     # sqlite db file lives here (gitignored)
└── logs/                     # rotating log files (gitignored)
```

Each package folder's `__init__.py` documents that package's exact
responsibility and boundaries — read those before adding code to a folder.

---

## Setup (WSL Ubuntu)

```bash
# 1. Clone / cd into the project
cd ~/projects/cmoai   # or wherever you place it

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create your local environment file
cp .env.example .env
# then open .env and fill in GEMINI_API_KEY (or NVIDIA_API_KEY), etc.

# 5. Verify the skeleton is wired correctly
python main.py
```

Expected output ends with:

```
cmoAI skeleton is configured correctly ✅
```

A `logs/cmoai.log` file and a `data/` directory (for the SQLite DB, added
in Brick 3) will be created automatically.

To leave the virtual environment later: `deactivate`

---

## Running Tests

```bash
pytest tests/ -v
```

---

## Running the API

```bash
uvicorn api.main:app --reload
```

Then visit `http://127.0.0.1:8000/docs` for interactive API docs (Swagger UI), or:

```bash
# Run a full analysis (this can take a minute or two: web scraping + several LLM calls)
curl -X POST http://127.0.0.1:8000/consulting-cases \
  -H "Content-Type: application/json" \
  -d '{"company_name": "Acme Corp", "website_url": "https://acme.example.com"}'

# Check a case's status
curl http://127.0.0.1:8000/consulting-cases/{case_id}

# Fetch its report once ready
curl http://127.0.0.1:8000/consulting-cases/{case_id}/report

# Download the PowerPoint
curl -OJ http://127.0.0.1:8000/consulting-cases/{case_id}/download-pptx

# If the diagnosis said marketing wasn't the primary issue, request a strategy anyway
curl -X POST http://127.0.0.1:8000/consulting-cases/{case_id}/generate-strategy-anyway
```

No background task queue exists in V1 by design (see Design Principles below), so
`POST /consulting-cases` runs synchronously and the HTTP response only returns
once the full pipeline finishes.

---

## Development Roadmap (bricks)

1. ~~Project Structure & Environment~~ ✅
2. ~~Domain Models~~ ✅
3. ~~SQLite Storage Layer~~ ✅
4. ~~Website Collector Service~~ ✅
5. ~~PDF & Social Media Collector Services~~ ✅ ← you are here
6. ~~Market Research Service (small LLM)~~ ✅ ← you are here
7. ~~Information Extraction Service (small LLM)~~ ✅ ← you are here
8. ~~Orchestrator — Diagnosis~~ ✅
9. ~~Orchestrator — Strategy & Report Generation~~ ✅ ← you are here
10. ~~PowerPoint Generator~~ ✅ ← you are here
11. ~~API Layer / Main Flow Wiring~~ ✅ ← V1 complete

---

## Design Principles

1. Keep V1 as simple as possible.
2. Only the orchestrator makes business decisions.
3. Services collect/transform information; they never reason.
4. Store structured, meaningful data — not raw noise.
5. Use long, self-documenting function names (no `run()`, `process()`, `analyze()`).
6. Build a modular monolith that can evolve later.
7. Every recommendation must be supported by evidence.
8. Never force a marketing strategy if marketing is not the real problem.
9. Always allow the user to override the diagnosis and request a strategy anyway.
10. Optimize for maintainability and readability over premature complexity.
