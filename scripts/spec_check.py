"""Spec compliance checks against the official public sample pack."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from app.guardrails import normalize_interpretations
from app.main import app
from app.models import OptimizeRequest, OptimizeResponse
from app.optimizer import optimize_schedule
from app.replay import replay_plan

TOL = 0.01
REQUIRED_INPUT = {"scenario_id", "operator_notes", "hours", "battery"}
REQUIRED_HOUR = {"hour", "demand_kwh", "solar_kwh", "tariff_bdt_per_kwh"}
REQUIRED_BATTERY = {
    "capacity_kwh",
    "initial_energy_kwh",
    "minimum_energy_kwh",
    "max_charge_kwh_per_hour",
    "max_discharge_kwh_per_hour",
}
REQUIRED_OUTPUT = {
    "scenario_id",
    "directive_interpretation",
    "hourly_plan",
    "total_grid_kwh",
    "total_cost_bdt",
    "peak_grid_kwh",
    "plan_summary",
}
REQUIRED_DIRECTIVE = {
    "note_index",
    "applies",
    "directive_type",
    "structured_adjustment",
    "explanation",
}
REQUIRED_PLAN = {
    "hour",
    "grid_kwh",
    "solar_used_kwh",
    "battery_action",
    "battery_kwh",
    "battery_energy_after_kwh",
}
ALLOWED_TYPES = {
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op",
}


def load_cases() -> list[dict]:
    payload = json.loads((ROOT / "tests" / "public_samples.json").read_text(encoding="utf-8"))
    return payload["cases"]


def check_official_expected_schema(case: dict) -> list[str]:
    errors = []
    inp = case["input"]
    out = case["expected_output"]
    if set(inp) < REQUIRED_INPUT:
        errors.append("input missing required fields")
    if set(out) < REQUIRED_OUTPUT:
        errors.append("expected_output missing required fields")
    notes = inp["operator_notes"]
    di = out["directive_interpretation"]
    if not (1 <= len(notes) <= 3):
        errors.append("operator_notes length not 1-3")
    if len(di) != len(notes):
        errors.append("interpretation count != notes")
    for i, item in enumerate(di):
        if set(item) < REQUIRED_DIRECTIVE:
            errors.append(f"directive {i} missing fields")
        if item["note_index"] != i:
            errors.append(f"note_index order broken at {i}")
        if item["directive_type"] not in ALLOWED_TYPES:
            errors.append(f"unsupported type {item['directive_type']}")
        if item["directive_type"] == "no_op":
            if item["applies"] is not False or item["structured_adjustment"] is not None:
                errors.append(f"no_op semantics broken at {i}")
        else:
            if item["applies"] is not True:
                errors.append(f"applies must be true for {item['directive_type']}")
            adj = item["structured_adjustment"] or {}
            hours = adj.get("hours", [])
            if hours != sorted(set(hours)) or any(h < 0 or h > 23 for h in hours):
                errors.append(f"hours not unique 0-23 sorted at note {i}")
    plan = out["hourly_plan"]
    if [p["hour"] for p in plan] != list(range(24)):
        errors.append("expected hourly_plan hours not 0-23")
    return errors


def main() -> int:
    failures = 0
    cases = load_cases()
    print(f"Loaded {len(cases)} official public cases\n")

    print("=== 1. Official sample schema vs Problem Statement ===")
    for case in cases:
        errs = check_official_expected_schema(case)
        if errs:
            failures += 1
            print(f"  FAIL {case['id']}: {errs}")
        else:
            print(f"  OK   {case['id']} notes={len(case['input']['operator_notes'])} types="
                  + ",".join(d['directive_type'] for d in case['expected_output']['directive_interpretation']))

    print("\n=== 2. Our replay accepts official expected hourly_plan (judge rules) ===")
    for case in cases:
        request = OptimizeRequest.model_validate(case["input"])
        expected = case["expected_output"]
        interpretations = normalize_interpretations(
            expected["directive_interpretation"],
            note_count=len(request.operator_notes),
            battery=request.battery,
        )
        try:
            result = replay_plan(request, interpretations, expected["hourly_plan"])
            cost_ok = abs(result.total_cost_bdt - expected["total_cost_bdt"]) <= TOL
            grid_ok = abs(result.total_grid_kwh - expected["total_grid_kwh"]) <= TOL
            peak_ok = abs(result.peak_grid_kwh - expected["peak_grid_kwh"]) <= TOL
            if not (cost_ok and grid_ok and peak_ok):
                failures += 1
                print(
                    f"  FAIL {case['id']} totals "
                    f"cost {result.total_cost_bdt} vs {expected['total_cost_bdt']}"
                )
            else:
                print(f"  OK   {case['id']} official plan replays; totals match")
        except Exception as exc:
            failures += 1
            print(f"  FAIL {case['id']} replay of official plan: {type(exc).__name__}: {exc}")

    print("\n=== 3. Our optimizer vs official optimal cost + our plan validity ===")
    for case in cases:
        request = OptimizeRequest.model_validate(case["input"])
        expected = case["expected_output"]
        interpretations = normalize_interpretations(
            expected["directive_interpretation"],
            note_count=len(request.operator_notes),
            battery=request.battery,
        )
        result = optimize_schedule(request, interpretations)
        payload = OptimizeResponse(
            scenario_id=request.scenario_id,
            directive_interpretation=interpretations,
            hourly_plan=result.hourly_plan,
            total_grid_kwh=result.total_grid_kwh,
            total_cost_bdt=result.total_cost_bdt,
            peak_grid_kwh=result.peak_grid_kwh,
            plan_summary="test",
        ).model_dump()
        missing = REQUIRED_OUTPUT - set(payload)
        if missing:
            failures += 1
            print(f"  FAIL {case['id']} response missing {missing}")
            continue
        cost_delta = result.total_cost_bdt - expected["total_cost_bdt"]
        if result.total_cost_bdt > expected["total_cost_bdt"] + TOL:
            failures += 1
            print(f"  FAIL {case['id']} cost {result.total_cost_bdt} > {expected['total_cost_bdt']}")
        else:
            print(
                f"  OK   {case['id']} cost={result.total_cost_bdt:.4f} "
                f"ref={expected['total_cost_bdt']:.4f} delta={cost_delta:.4f} "
                f"peak={result.peak_grid_kwh:.4f}"
            )

    print("\n=== 4. HTTP contract ===")
    client = TestClient(app)
    health = client.get("/health")
    if health.status_code != 200 or health.json() != {"status": "ok"}:
        failures += 1
        print(f"  FAIL /health {health.status_code} {health.json()}")
    else:
        print("  OK   GET /health -> {status: ok}")

    bad = client.post("/optimize-energy", content="not-json", headers={"content-type": "application/json"})
    if bad.status_code != 400:
        failures += 1
        print(f"  FAIL malformed JSON status {bad.status_code}")
    else:
        print("  OK   POST malformed JSON -> 400")

    missing = client.post("/optimize-energy", json={"scenario_id": "x"})
    if missing.status_code != 400:
        failures += 1
        print(f"  FAIL incomplete body status {missing.status_code}")
    else:
        print("  OK   POST incomplete body -> 400")

    from app import main as main_mod

    case = cases[0]
    request = OptimizeRequest.model_validate(case["input"])
    interpretations = normalize_interpretations(
        case["expected_output"]["directive_interpretation"],
        note_count=len(request.operator_notes),
        battery=request.battery,
    )

    def fake_interpret(_payload):
        return interpretations

    main_mod.interpret_operator_notes = fake_interpret
    response = client.post("/optimize-energy", json=case["input"])
    if response.status_code != 200:
        failures += 1
        print(f"  FAIL SAMPLE-01 HTTP {response.status_code} {response.text[:300]}")
    else:
        body = response.json()
        schema_ok = set(body) >= REQUIRED_OUTPUT
        notes_ok = len(body["directive_interpretation"]) == len(case["input"]["operator_notes"])
        hours_ok = [row["hour"] for row in body["hourly_plan"]] == list(range(24))
        echo_ok = body["scenario_id"] == case["input"]["scenario_id"]
        cost_ok = abs(body["total_cost_bdt"] - case["expected_output"]["total_cost_bdt"]) <= TOL
        if not (schema_ok and notes_ok and hours_ok and echo_ok and cost_ok):
            failures += 1
            print("  FAIL SAMPLE-01 HTTP response contract")
        else:
            print(
                f"  OK   POST /optimize-energy SAMPLE-01 HTTP 200, "
                f"cost={body['total_cost_bdt']}, types="
                + ",".join(d["directive_type"] for d in body["directive_interpretation"])
            )

    print("\n=== 5. LLM live path ===")
    from app.llm import provider_name
    print(f"  provider={provider_name()}")
    if provider_name() == "unconfigured":
        print("  SKIP no GROQ_API_KEY / GEMINI_API_KEY (required for hidden-note judging)")
    else:
        from scripts.test_samples import test_llm_path
        llm_failures = test_llm_path()
        failures += llm_failures

    print("\n================================")
    if failures:
        print(f"RESULT: {failures} failure(s) — code does not fully match the statement")
        return 1
    print("RESULT: code matches the Problem Statement on all checked public cases and HTTP rules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
