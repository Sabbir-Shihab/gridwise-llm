# 3-minute video script (teleprompter)

Record with Windows Win+G or OBS. Camera optional. Show the screen. Speak English. Target **2:40–2:55**. Do not go past 3:00.

Live URL to show (do **not** show API keys):

`https://label-offices-came-milk.trycloudflare.com`

Before record: open README, `app/llm.py`, `app/guardrails.py`, `app/optimizer.py`, and a terminal already in `g:\BUP hackathon`.

---

## 0:00–0:20 — Problem
**Screen:** README title + first paragraph.

We built GridWise LLM for the BUP CSE Fest 2026 preliminary.

Campus demand, rooftop solar, and grid tariff are known for twenty-four hours. Operators also send one to three natural-language notes. Some notes change the schedule. Others are distractors.

The API must understand those notes, apply only supported directives, then return a valid low-cost twenty-four-hour energy plan.

## 0:20–0:50 — Architecture
**Screen:** README architecture block, then the `app/` folder.

The pipeline is five steps.

First, `POST /optimize-energy` validates the JSON contract.

Second, a language model — Groq `openai/gpt-oss-20b`, with Gemini Flash as fallback — turns every note into one structured directive.

Third, deterministic guardrails check type, hours, applies semantics, and numeric ranges.

Fourth, OR-Tools GLOP solves the linear program.

Fifth, an independent replay checks energy balance, effective solar, battery limits, directive windows, and end-of-day neutrality.

The LLM is on the interpretation path, not only used for the summary text.

## 0:50–1:20 — LLM and guardrails
**Screen:** `app/llm.py`, then `app/guardrails.py`.

One JSON call handles all notes. Battery capacity is sent so a fifty-percent reserve becomes kilowatt-hours.

Time windows are start-inclusive and end-exclusive. One PM to three PM is hours thirteen and fourteen.

An eighty-percent solar reduction means factor zero-point-two remaining.

Irrelevant notes become `no_op` with `applies` false and a null adjustment.

Hidden wording can paraphrase the same rule, so we do not hard-code public sample phrases.

If the model returns malformed JSON, we retry once, then fail closed. Guardrails never invent a new directive type.

## 1:20–1:50 — Optimizer
**Screen:** `app/optimizer.py` objective / constraints, glance at `app/replay.py`.

The objective is minimize the sum of grid kilowatt-hours times the hourly tariff.

Constraints are energy balance every hour, solar cannot exceed effective solar after reductions, charge and discharge rate limits, capacity and reserve, no-charge and no-discharge windows, grid caps, and final battery energy equals the initial energy.

After the LP, we replay the plan hour by hour so reported totals match the hourly actions.

## 1:50–2:40 — Live demo
**Screen:** terminal. Do **not** scroll secrets.

```powershell
curl.exe -s https://label-offices-came-milk.trycloudflare.com/health
curl.exe -s -X POST https://label-offices-came-milk.trycloudflare.com/optimize-energy -H "Content-Type: application/json" -d "@tests/sample_request.json"
```

**Say while it runs:**

Health returns status ok as JSON.

This SAMPLE-01 request has a solar-cleaning note from noon to two PM, treating usable solar as twenty-five percent of forecast, plus a distractor about a sports-office deadline.

The service maps that to `solar_reduction` with factor zero-point-two-five on hours twelve and thirteen, and `no_op` for the distractor.

The returned cost is thirty-eight thousand three hundred sixty-five taka, matching the official sample.

Locally, all ten public samples pass on both the optimizer path and the full LLM path.

Keys stay in environment variables. Nothing is committed.

## 2:40–2:55 — Close
**Screen:** README API section.

The judging path is: understand the note, validate the directive, apply it, return a valid schedule, then minimize cost.

Same pipeline on the live URL, the GitHub README, and Docker.

Thank you.

---

## Recording checklist

1. Hide `.env` and any password windows.
2. Speak the script; do not improvise long explanations.
3. If the live curl is slow, keep talking — do not wait in silence.
4. Upload unlisted YouTube **or** Google Drive with “anyone with the link can view”.
5. Paste that URL into the form’s 3-minute video field.
