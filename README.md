# GridWise LLM — Smart Campus Energy Optimizer

BUP CSE Fest 2026 Hackathon · Online Preliminary Round

Public FastAPI service that interprets campus operator notes with a language model, validates the structured directives, then solves a 24-hour grid/solar/battery schedule that minimizes electricity cost.

## Architecture

```
operator notes
    -> Groq (`openai/gpt-oss-20b`) or Gemini Flash
    -> deterministic guardrails
    -> OR-Tools GLOP linear program
    -> independent hour-by-hour replay
    -> JSON plan
```

The LLM is on the operator-note interpretation path. Guardrails never invent a new directive type. The optimizer applies only validated directives. `plan_summary` is generated after the schedule is solved.

## Required environment variables

| Name | Required | Purpose |
|---|---|---|
| `GROQ_API_KEY` | One of Groq or Gemini | Operator-note interpretation (preferred, low latency) |
| `GEMINI_API_KEY` | One of Groq or Gemini | Fallback / alternative interpreter |
| `GROQ_MODEL` | No | Default `openai/gpt-oss-20b` |
| `GEMINI_MODEL` | No | Default `gemini-2.0-flash` |
| `LLM_TIMEOUT_SECONDS` | No | Default `12` |
| `LLM_MAX_RETRIES` | No | Default `2` |
| `PORT` | No | Default `8000` |

Do not commit secret values. Copy `.env.example` to `.env`.

## Local quickstart (clean machine)

```bash
git clone <this-repo>
cd <this-repo>
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env   # then set GROQ_API_KEY or GEMINI_API_KEY
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Expected:

```json
{"status":"ok"}
```

## API

### `GET /health`

Readiness probe. HTTP 200 and `{"status":"ok"}`.

### `POST /optimize-energy`

Accepts one GridWise scenario JSON object. Returns `directive_interpretation` plus a 24-hour `hourly_plan`.

Malformed JSON or structurally invalid bodies return HTTP 400. Controlled internal failures return HTTP 500 without secrets or stack traces.

Example:

```bash
curl -s -X POST http://127.0.0.1:8000/optimize-energy ^
  -H "Content-Type: application/json" ^
  -d @tests/sample_request.json
```

On macOS/Linux use `\` instead of `^`.

A compact sample request is in `tests/sample_request.json`. The full public pack is `tests/public_samples.json`.

## Public sample test

Optimizer-only (uses published ground-truth interpretations; no LLM key):

```bash
python scripts/test_samples.py
```

Expected: all 10 public cases match reference cost and grid totals within `0.01`.

Full LLM + optimizer path (requires `GROQ_API_KEY` or `GEMINI_API_KEY`):

```bash
python scripts/test_samples.py --llm
```

Expected: each note maps to the public `directive_type`, hours, and numeric values; the resulting plan is valid and no more expensive than the reference.

## LLM role, guardrails, optimizer

**LLM.** Groq `openai/gpt-oss-20b` by default (Gemini Flash if only `GEMINI_API_KEY` is set). One JSON call interprets all 1–3 notes. Battery capacity is passed so percentage reserves become kWh. Time windows are start-inclusive / end-exclusive. `solar_reduction.factor` is the remaining usable fraction (an 80% reduction → `0.2`).

**Guardrails.** Allowed types only. Exactly one entry per note in `note_index` order. `no_op` uses `applies=false` and `structured_adjustment=null`. Other types use `applies=true` with the required shape. Hours are unique integers `0..23` ascending. Factor is in `[0,1]`. Reserve is finite, non-negative, and ≤ capacity. Invalid model JSON is retried once; unsupported types are never invented.

**Optimizer.** Google OR-Tools GLOP minimizes `sum(grid_kwh[h] * tariff[h])` subject to energy balance, effective solar, battery bounds and rates, no-charge / no-discharge windows, grid caps, and end-of-day battery neutrality (`E_final = E_initial`). The service then replays the plan hour by hour and recomputes `total_grid_kwh`, `total_cost_bdt`, and `peak_grid_kwh` from `hourly_plan`.

## Docker fallback

Image exposes port 8000 and binds `0.0.0.0`. Pass the LLM key at runtime. No secrets are baked into the image.

```bash
docker build -t gridwise-llm:preli .
docker run --rm -p 8000:8000 -e GROQ_API_KEY=YOUR_KEY gridwise-llm:preli
```

Then:

```bash
curl http://127.0.0.1:8000/health
python scripts/test_samples.py --llm
```

If using a registry image:

```bash
docker pull <registry>/<image>:<tag>
docker run --rm -p 8000:8000 -e GROQ_API_KEY=YOUR_KEY <registry>/<image>:<tag>
```

## Dependencies

See `requirements.txt`. Core libraries:

- FastAPI / Uvicorn — HTTP API
- httpx — Groq and Gemini requests
- pydantic — request/response validation
- OR-Tools GLOP — 24-hour linear program
- python-dotenv — local env loading

AI coding assistants were used during development. Core architecture (LLM → guardrails → LP → replay) is this team's work.

## Known limitations

- A valid `GROQ_API_KEY` or `GEMINI_API_KEY` must be available at runtime. Hosted-model quota, rate limits, and uptime are the team's responsibility.
- Hidden notes may paraphrase the same directive; phrase hard-coding is not used as the interpreter.
- If the language model returns malformed JSON twice, the request fails closed with HTTP 500 instead of inventing a directive.
- Grid export is not modeled. Unused solar is curtailed.
- Per-request timeout budget is dominated by the LLM call; the LP solve is typically well under 100 ms.

## Secret handling

- `.env` is gitignored.
- Docker images do not contain API keys.
- API responses and logs never echo credentials, raw secret-bearing prompts, or stack traces.
- Use only the synthetic harness data. No live campus, utility, billing, or personal data is required.
