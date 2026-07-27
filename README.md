# Loom Backend

AI-powered customer feedback analysis pipeline. Converts a raw CSV of customer
feedback into structured classification, deterministic analytics, and a
grounded executive summary — all in a single stateless API call.

See [`Loom_Source_of_Truth.md`](Loom_Source_of_Truth.md) for the full design
rationale.

## Architecture

The LLM classifies and phrases; Python computes every number. Every LLM
response is validated against a closed-enum Pydantic schema before use, with
a bounded repair contract (validate -> coerce -> one re-prompt -> fallback)
so a single bad ticket never fails the batch.

```
src/loom/
├── api/          FastAPI routes (POST /analyze)
├── pipeline/      validate -> preprocess -> classify -> summarize
├── analytics/     deterministic aggregation (no LLM imports)
├── prompts/       prompt templates, generated from schemas/taxonomy.py
├── rag/           embeddings + retrieval-augmented Q&A
├── reports/       chart + PDF report generation
├── schemas/       canonical taxonomy + Pydantic models
├── services/      OpenAI client wrapper
├── utils/         shared text helpers + error types
├── main.py        FastAPI app, CORS, request timing
└── cli.py         runs 10 hardcoded tickets end-to-end (no server needed)
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env   # fill in LLM_MODEL and API_KEY
```

## Run the pipeline spine (no server)

```bash
python -m loom.cli
```

## Run the API

```bash
uvicorn loom.main:app --reload
```

```bash
curl -F "file=@sample.csv" http://localhost:8000/analyze
```

`sample.csv` needs a `feedback` column; `id`, `source`, and `date` are optional.

## Configuration

All runtime parameters are environment variables — see `.env.example`.
`LLM_MODEL` and `API_KEY` are required; everything else has a sensible default.

## Error codes

| Code | Meaning |
|------|---------|
| 4001 | Missing `feedback` column |
| 4002 | Empty CSV / unparseable file |
| 4003 | No valid feedback rows found |
| 4004 | Invalid LLM response (post-repair) |
| 5001 | AI provider unavailable |
