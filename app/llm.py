from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import httpx

from app.config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GROQ_API_KEY,
    GROQ_MODEL,
    LLM_MAX_RETRIES,
    LLM_TIMEOUT_SECONDS,
)
from app.guardrails import GuardrailError, normalize_interpretations
from app.models import DirectiveInterpretation, OptimizeRequest

logger = logging.getLogger("gridwise.llm")

SYSTEM_PROMPT = """You are the operator-note interpreter for a 24-hour campus energy scheduler.

Convert each operator note into exactly one structured directive. Return JSON only.

Allowed directive_type values:
- solar_reduction
- minimum_battery_reserve
- no_charge_window
- no_discharge_window
- max_grid_window
- no_op

Output schema:
{"directives":[
  {"note_index":0,"applies":true,"directive_type":"solar_reduction","structured_adjustment":{"hours":[13,14],"factor":0.2},"explanation":"..."}
]}

Rules:
1. One object per operator note, note_index 0..N-1, same order as the notes.
2. Time windows are whole-hour intervals. Start is included, end is excluded.
   1 PM to 3 PM -> [13,14]
   noon until 2 PM -> [12,13]
   2 AM until 5 AM -> [2,3,4]
   between 11 AM and 2 PM -> [11,12,13]
   from 6 PM until 9 PM -> [18,19,20]
   from 6 PM until 10 PM -> [18,19,20,21]
   12 PM is hour 12, 12 AM is hour 0. 24-hour clocks such as 13:00-15:00 map the same way: [13,14].
3. hours must be unique integers 0-23 in ascending order.
4. solar_reduction.factor is the usable fraction that REMAINS, in [0,1].
   "drop to 20%" / "about 20% of forecast" / "one-fifth of normal" -> 0.2
   "roughly 25% of the forecast" -> 0.25
   "about half" -> 0.5
   "80% reduction" / "reduce by 80%" -> 0.2 because 20% remains.
5. minimum_battery_reserve.minimum_energy_kwh is kWh. If the note gives a percentage of battery capacity, convert using capacity_kwh. Example: 50% of a 200 kWh battery -> 100.
6. no_charge_window: charging unavailable, charger isolated, charging circuit down, do not charge.
7. no_discharge_window: do not discharge, discharge disabled, protection testing that forbids discharge.
8. max_grid_window: grid import / intake / feeder / transformer / substation cap. max_grid_kwh is the hourly cap.
9. no_op if the note does not change this 24-hour energy, solar, battery, or grid schedule. Examples: cafeteria menus, registration deadlines, library hours next week, club notices tomorrow, room bookings moved. For no_op: applies=false and structured_adjustment=null.
10. Every non-no_op directive has applies=true and the required structured_adjustment keys.
11. Do not invent demand, tariff, battery hardware limits, or new directive types.
12. Each note maps to exactly one supported type. Hidden wording may paraphrase the same rule.

structured_adjustment shapes:
- solar_reduction: {"hours":[...],"factor":number}
- minimum_battery_reserve: {"hours":[...],"minimum_energy_kwh":number}
- no_charge_window: {"hours":[...]}
- no_discharge_window: {"hours":[...]}
- max_grid_window: {"hours":[...],"max_grid_kwh":number}
- no_op: null
"""


class LLMInterpretationError(RuntimeError):
    """Raised when the language model cannot produce a valid interpretation."""


def _extract_json(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _user_payload(request: OptimizeRequest) -> str:
    notes = [{"note_index": i, "text": note} for i, note in enumerate(request.operator_notes)]
    battery = request.battery
    return json.dumps(
        {
            "scenario_id": request.scenario_id,
            "operator_notes": notes,
            "battery": {
                "capacity_kwh": battery.capacity_kwh,
                "initial_energy_kwh": battery.initial_energy_kwh,
                "minimum_energy_kwh": battery.minimum_energy_kwh,
                "max_charge_kwh_per_hour": battery.max_charge_kwh_per_hour,
                "max_discharge_kwh_per_hour": battery.max_discharge_kwh_per_hour,
            },
            "instruction": "Interpret every operator note. Use battery.capacity_kwh when a reserve is given as a percentage of capacity.",
        },
        ensure_ascii=True,
    )


def _groq_available() -> bool:
    return bool(GROQ_API_KEY)


def _gemini_available() -> bool:
    return bool(GEMINI_API_KEY)


def provider_name() -> str:
    if _groq_available():
        return f"groq:{GROQ_MODEL}"
    if _gemini_available():
        return f"gemini:{GEMINI_MODEL}"
    return "unconfigured"


def _call_groq(user_content: str) -> str:
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    }
    last_error: Exception | None = None
    with httpx.Client(timeout=LLM_TIMEOUT_SECONDS) as client:
        for attempt in range(4):
            response = client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            if response.status_code == 429:
                retry_after = response.headers.get("retry-after", "1")
                try:
                    wait = min(max(float(retry_after), 0.8), 3.5)
                except ValueError:
                    wait = 1.2
                logger.warning("Groq HTTP 429, retry in %.1fs", wait)
                time.sleep(wait)
                continue
            if response.status_code >= 400:
                logger.warning("Groq HTTP %s", response.status_code)
                response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"].get("content") or ""
            if not content.strip():
                raise LLMInterpretationError("empty model content")
            return content
    raise LLMInterpretationError("Groq rate limited")


def _call_gemini(user_content: str) -> str:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent"
    )
    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": user_content}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
        },
    }
    with httpx.Client(timeout=LLM_TIMEOUT_SECONDS) as client:
        response = client.post(url, params={"key": GEMINI_API_KEY}, json=payload)
        response.raise_for_status()
        data = response.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _call_model(user_content: str) -> str:
    errors: list[str] = []
    if _groq_available():
        try:
            return _call_groq(user_content)
        except Exception as exc:
            logger.warning("Groq interpretation failed: %s", type(exc).__name__)
            errors.append("groq")
    if _gemini_available():
        try:
            return _call_gemini(user_content)
        except Exception as exc:
            logger.warning("Gemini interpretation failed: %s", type(exc).__name__)
            errors.append("gemini")
    if not _groq_available() and not _gemini_available():
        raise LLMInterpretationError("No LLM API key configured")
    raise LLMInterpretationError("Language model request failed")


def interpret_operator_notes(request: OptimizeRequest) -> list[DirectiveInterpretation]:
    base_payload = _user_payload(request)
    last_error = "unknown"
    payload = base_payload
    for attempt in range(LLM_MAX_RETRIES + 1):
        try:
            raw_text = _call_model(payload)
            parsed = _extract_json(raw_text)
            return normalize_interpretations(
                parsed,
                note_count=len(request.operator_notes),
                battery=request.battery,
            )
        except (json.JSONDecodeError, KeyError, IndexError, GuardrailError, LLMInterpretationError) as exc:
            last_error = str(exc)
            logger.warning("LLM interpretation attempt %s failed: %s", attempt + 1, type(exc).__name__)
            payload = (
                base_payload
                + "\n\nPrevious output was invalid: "
                + last_error
                + "\nReturn corrected JSON only, following the schema exactly."
            )
        except httpx.HTTPError:
            last_error = "http_error"
            logger.warning("LLM HTTP error on attempt %s", attempt + 1)
            payload = base_payload
    raise LLMInterpretationError("Failed to produce a valid structured interpretation")


def summarize_plan(
    interpretations: list[DirectiveInterpretation],
    total_cost_bdt: float,
) -> str:
    parts = []
    for item in interpretations:
        if item.directive_type == "no_op":
            parts.append(f"Note {item.note_index} ignored as no_op.")
        else:
            parts.append(
                f"Note {item.note_index} applied as {item.directive_type} "
                f"on hours {item.structured_adjustment.get('hours')}."
            )
    parts.append(
        "Battery shifts energy into higher-tariff hours, respects all hard constraints, "
        f"restores the initial state of charge, and yields {total_cost_bdt:.2f} BDT grid cost."
    )
    return " ".join(parts)
