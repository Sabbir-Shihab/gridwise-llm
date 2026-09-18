from __future__ import annotations

from typing import Any

from app.config import ALLOWED_DIRECTIVE_TYPES, NUMERIC_TOLERANCE
from app.models import BatteryConfig, DirectiveInterpretation


class GuardrailError(ValueError):
    """Raised when LLM output cannot be coerced into a valid directive."""


def _is_finite_number(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return number == number and number not in (float("inf"), float("-inf"))


def _normalize_hours(raw: Any) -> list[int]:
    if not isinstance(raw, list) or not raw:
        raise GuardrailError("hours must be a non-empty list")
    hours: list[int] = []
    for item in raw:
        if not _is_finite_number(item):
            raise GuardrailError("hours must be numeric")
        hour = int(round(float(item)))
        if abs(float(item) - hour) > NUMERIC_TOLERANCE:
            raise GuardrailError("hours must be whole numbers")
        if hour < 0 or hour > 23:
            raise GuardrailError("hours must be integers from 0 through 23")
        hours.append(hour)
    unique = sorted(set(hours))
    if not unique:
        raise GuardrailError("hours must contain at least one valid hour")
    return unique


def _required_hours_only(adjustment: dict[str, Any]) -> dict[str, Any]:
    return {"hours": _normalize_hours(adjustment.get("hours"))}


def normalize_directive(
    raw: dict[str, Any],
    note_index: int,
    battery: BatteryConfig,
) -> DirectiveInterpretation:
    if not isinstance(raw, dict):
        raise GuardrailError("each interpretation must be an object")

    directive_type = str(raw.get("directive_type", "")).strip()
    if directive_type not in ALLOWED_DIRECTIVE_TYPES:
        raise GuardrailError(f"unsupported directive_type: {directive_type}")

    explanation = str(raw.get("explanation") or "").strip()
    if not explanation:
        explanation = f"Interpreted operator note {note_index} as {directive_type}."

    if directive_type == "no_op":
        return DirectiveInterpretation(
            note_index=note_index,
            applies=False,
            directive_type="no_op",
            structured_adjustment=None,
            explanation=explanation,
        )

    adjustment = raw.get("structured_adjustment")
    if not isinstance(adjustment, dict):
        raise GuardrailError(f"{directive_type} requires structured_adjustment")

    if directive_type == "solar_reduction":
        factor_raw = adjustment.get("factor")
        if not _is_finite_number(factor_raw):
            raise GuardrailError("solar_reduction factor must be a finite number")
        factor = float(factor_raw)
        if factor < 0 or factor > 1:
            raise GuardrailError("solar_reduction factor must be between 0 and 1")
        structured = {"hours": _normalize_hours(adjustment.get("hours")), "factor": factor}
    elif directive_type == "minimum_battery_reserve":
        reserve_raw = adjustment.get("minimum_energy_kwh")
        if not _is_finite_number(reserve_raw):
            raise GuardrailError("minimum_energy_kwh must be a finite number")
        reserve = float(reserve_raw)
        if reserve < 0 or reserve > battery.capacity_kwh + NUMERIC_TOLERANCE:
            raise GuardrailError("minimum_energy_kwh must be within battery capacity")
        reserve = min(max(reserve, 0.0), battery.capacity_kwh)
        structured = {
            "hours": _normalize_hours(adjustment.get("hours")),
            "minimum_energy_kwh": reserve,
        }
    elif directive_type == "no_charge_window":
        structured = _required_hours_only(adjustment)
    elif directive_type == "no_discharge_window":
        structured = _required_hours_only(adjustment)
    elif directive_type == "max_grid_window":
        cap_raw = adjustment.get("max_grid_kwh")
        if not _is_finite_number(cap_raw):
            raise GuardrailError("max_grid_kwh must be a finite number")
        cap = float(cap_raw)
        if cap < 0:
            raise GuardrailError("max_grid_kwh must be non-negative")
        structured = {"hours": _normalize_hours(adjustment.get("hours")), "max_grid_kwh": cap}
    else:
        raise GuardrailError(f"unsupported directive_type: {directive_type}")

    return DirectiveInterpretation(
        note_index=note_index,
        applies=True,
        directive_type=directive_type,
        structured_adjustment=structured,
        explanation=explanation,
    )


def normalize_interpretations(
    raw_items: Any,
    note_count: int,
    battery: BatteryConfig,
) -> list[DirectiveInterpretation]:
    if isinstance(raw_items, dict):
        if "directives" in raw_items:
            raw_items = raw_items["directives"]
        elif "directive_interpretation" in raw_items:
            raw_items = raw_items["directive_interpretation"]
        elif "interpretations" in raw_items:
            raw_items = raw_items["interpretations"]

    if not isinstance(raw_items, list) or len(raw_items) != note_count:
        raise GuardrailError("expected one interpretation per operator note")

    by_index: dict[int, dict[str, Any]] = {}
    for position, item in enumerate(raw_items):
        if not isinstance(item, dict):
            raise GuardrailError("interpretation entries must be objects")
        if "note_index" in item and _is_finite_number(item["note_index"]):
            index = int(item["note_index"])
        else:
            index = position
        if index < 0 or index >= note_count or index in by_index:
            raise GuardrailError("note_index values must be unique and in range")
        by_index[index] = item

    if sorted(by_index) != list(range(note_count)):
        raise GuardrailError("missing or duplicate note_index mappings")

    return [
        normalize_directive(by_index[index], index, battery)
        for index in range(note_count)
    ]


def effective_solar_profile(hours: list[Any], interpretations: list[DirectiveInterpretation]) -> list[float]:
    solar = [float(entry.solar_kwh) for entry in hours]
    for item in interpretations:
        if item.directive_type != "solar_reduction" or not item.applies:
            continue
        factor = float(item.structured_adjustment["factor"])
        for hour in item.structured_adjustment["hours"]:
            solar[hour] *= factor
    return solar


def hourly_minimum_energy(battery: BatteryConfig, interpretations: list[DirectiveInterpretation]) -> list[float]:
    mins = [float(battery.minimum_energy_kwh)] * 24
    for item in interpretations:
        if item.directive_type != "minimum_battery_reserve" or not item.applies:
            continue
        reserve = float(item.structured_adjustment["minimum_energy_kwh"])
        for hour in item.structured_adjustment["hours"]:
            mins[hour] = max(mins[hour], reserve)
    return mins


def hour_set(interpretations: list[DirectiveInterpretation], directive_type: str) -> set[int]:
    hours: set[int] = set()
    for item in interpretations:
        if item.applies and item.directive_type == directive_type:
            hours.update(item.structured_adjustment["hours"])
    return hours


def max_grid_caps(interpretations: list[DirectiveInterpretation]) -> dict[int, float]:
    caps: dict[int, float] = {}
    for item in interpretations:
        if not item.applies or item.directive_type != "max_grid_window":
            continue
        cap = float(item.structured_adjustment["max_grid_kwh"])
        for hour in item.structured_adjustment["hours"]:
            caps[hour] = cap if hour not in caps else min(caps[hour], cap)
    return caps
