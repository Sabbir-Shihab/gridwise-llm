# 3-minute architecture / solution video script

Target length: 2:30–2:50. Screen-record this README + code. Speak clearly; no fancy editing required.

## 0:00–0:20 — Problem

We are solving the BUP CSE Fest 2026 GridWise preliminary.

Campus demand, rooftop solar, and grid tariff are known for 24 hours. Operators also send 1–3 natural-language notes. Some notes change the schedule; others are distractors.

The service must understand those notes, apply only the supported directives, then return a valid low-cost 24-hour energy plan.

## 0:20–0:50 — Architecture overview

Show `README.md` architecture block, then `app/` files.

Pipeline:

1. `POST /optimize-energy` validates the JSON contract.
2. A language model — Groq Llama 3.3 70B, with Gemini Flash as fallback — converts every note into one structured directive.
3. Deterministic guardrails check type, hours, applies semantics, and numeric ranges.
4. OR-Tools GLOP solves the linear program.
5. An independent replay checks energy balance, effective solar, battery limits, directive windows, and end-of-day neutrality.

The LLM is on the interpretation path, not just used for the summary text.

## 0:50–1:25 — LLM and guardrails

Open `app/llm.py` and `app/guardrails.py`.

Points to say:

- One JSON call handles all notes.
- Battery capacity is sent so “50% reserve” becomes kWh.
- Time windows are start-inclusive and end-exclusive: 1 PM to 3 PM is hours 13 and 14.
- An 80% solar reduction means factor 0.2 remaining.
- Irrelevant notes become `no_op` with `applies=false` and null adjustment.
- Hidden wording can paraphrase the same rule, so we do not hard-code public phrases.
- If the model returns malformed JSON, we retry once and then fail closed instead of inventing a new directive type.

## 1:25–1:55 — Optimizer and constraints

Open `app/optimizer.py` and `app/replay.py`.

Points to say:

- Objective: minimize sum of grid_kwh times tariff.
- Constraints: energy balance every hour, solar cannot exceed effective solar after reductions, charge/discharge rate limits, capacity and reserve, no-charge and no-discharge windows, grid caps, and final battery energy equals the initial energy.
- After the LP, we net charge versus discharge and replay the plan so reported totals match the hourly actions.

## 1:55–2:30 — How to run and test

Show the terminal.

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
curl http://127.0.0.1:8000/health
python scripts/test_samples.py
python scripts/test_samples.py --llm
```

Say:

- `/health` returns `{"status":"ok"}`.
- Public samples are in `tests/public_samples.json`.
- Optimizer-only tests match all 10 reference costs exactly.
- `--llm` checks paraphrase-style interpretation against the public ground truth.
- Docker fallback: `docker build -t gridwise-llm:preli .` then `docker run -p 8000:8000 -e GROQ_API_KEY=...`.
- Keys stay in environment variables. Nothing is committed.

## 2:30–2:50 — Close

The judging path is: understand the note, validate the directive, apply it, return a valid schedule, then minimize cost. The live endpoint, repository README, and Docker image all expose that same pipeline.
