from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.guardrails import normalize_interpretations
from app.models import OptimizeRequest
from app.optimizer import optimize_schedule
from app.replay import replay_plan

SAMPLE_PATHS = [
    ROOT / "tests" / "public_samples.json",
    ROOT / "participant_docs" / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json",
]


def load_cases() -> list[dict]:
    for path in SAMPLE_PATHS:
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload["cases"]
    raise FileNotFoundError("Public sample JSON not found")


def compare_interpretation(actual: list[dict], expected: list[dict]) -> list[str]:
    errors = []
    if len(actual) != len(expected):
        return [f"interpretation count {len(actual)} != {len(expected)}"]
    for got, want in zip(actual, expected):
        prefix = f"note {want['note_index']}"
        for key in ("note_index", "applies", "directive_type"):
            if got.get(key) != want.get(key):
                errors.append(f"{prefix} {key}: {got.get(key)!r} != {want.get(key)!r}")
        if want["directive_type"] == "no_op":
            if got.get("structured_adjustment") is not None:
                errors.append(f"{prefix} expected null structured_adjustment")
            continue
        got_adj = got.get("structured_adjustment") or {}
        want_adj = want.get("structured_adjustment") or {}
        if got_adj.get("hours") != want_adj.get("hours"):
            errors.append(f"{prefix} hours {got_adj.get('hours')} != {want_adj.get('hours')}")
        for numeric_key in ("factor", "minimum_energy_kwh", "max_grid_kwh"):
            if numeric_key not in want_adj:
                continue
            if abs(float(got_adj.get(numeric_key, 10**9)) - float(want_adj[numeric_key])) > 0.01:
                errors.append(
                    f"{prefix} {numeric_key} {got_adj.get(numeric_key)} != {want_adj[numeric_key]}"
                )
    return errors


def test_optimizer_only() -> int:
    failures = 0
    for case in load_cases():
        request = OptimizeRequest.model_validate(case["input"])
        expected = case["expected_output"]
        interpretations = normalize_interpretations(
            expected["directive_interpretation"],
            note_count=len(request.operator_notes),
            battery=request.battery,
        )
        result = optimize_schedule(request, interpretations)
        replay_plan(request, interpretations, [row.model_dump() for row in result.hourly_plan])
        expected_cost = float(expected["total_cost_bdt"])
        expected_grid = float(expected["total_grid_kwh"])
        cost_delta = result.total_cost_bdt - expected_cost
        print(
            f"{case['id']}: cost={result.total_cost_bdt:.4f} "
            f"(ref {expected_cost:.4f}, delta {cost_delta:.4f}) "
            f"grid={result.total_grid_kwh:.4f} (ref {expected_grid:.4f})"
        )
        if result.total_cost_bdt > expected_cost + 0.01:
            print(f"  FAIL cost worse than reference by {cost_delta:.4f}")
            failures += 1
    return failures


def test_llm_path() -> int:
    from app.llm import interpret_operator_notes, provider_name

    print(f"LLM provider: {provider_name()}")
    failures = 0
    for case in load_cases():
        request = OptimizeRequest.model_validate(case["input"])
        expected = case["expected_output"]
        try:
            interpretations = interpret_operator_notes(request)
        except Exception as exc:
            print(f"{case['id']}: LLM FAIL {type(exc).__name__}")
            failures += 1
            continue
        actual = [item.model_dump() for item in interpretations]
        errors = compare_interpretation(actual, expected["directive_interpretation"])
        result = optimize_schedule(request, interpretations)
        if errors:
            print(f"{case['id']}: INTERPRET FAIL")
            for err in errors:
                print(f"  {err}")
            failures += 1
        elif result.total_cost_bdt > float(expected["total_cost_bdt"]) + 0.01:
            print(
                f"{case['id']}: COST FAIL {result.total_cost_bdt:.4f} > "
                f"{expected['total_cost_bdt']}"
            )
            failures += 1
        else:
            print(f"{case['id']}: PASS interpretation+optimize ({result.total_cost_bdt:.2f} BDT)")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate GridWise public sample cases")
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Call the configured LLM instead of using public ground-truth interpretations",
    )
    args = parser.parse_args()
    failures = test_llm_path() if args.llm else test_optimizer_only()
    if failures:
        print(f"\n{failures} failing case(s)")
        return 1
    print("\nAll public sample checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
