from __future__ import annotations

from dataclasses import dataclass

from app.config import NUMERIC_TOLERANCE
from app.guardrails import (
    effective_solar_profile,
    hour_set,
    hourly_minimum_energy,
    max_grid_caps,
)
from app.models import DirectiveInterpretation, HourlyPlanEntry, OptimizeRequest


class ReplayError(ValueError):
    """Raised when a returned plan violates GridWise rules."""


@dataclass
class ReplayResult:
    hourly_plan: list[HourlyPlanEntry]
    total_grid_kwh: float
    total_cost_bdt: float
    peak_grid_kwh: float


def _finite_non_negative(value: float, name: str) -> float:
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise ReplayError(f"{name} is not finite")
    if number < -NUMERIC_TOLERANCE:
        raise ReplayError(f"{name} is negative")
    return max(number, 0.0)


def replay_plan(
    request: OptimizeRequest,
    interpretations: list[DirectiveInterpretation],
    hourly_plan: list[dict],
) -> ReplayResult:
    if len(hourly_plan) != 24:
        raise ReplayError("hourly_plan must contain 24 entries")

    by_hour = {}
    for entry in hourly_plan:
        hour = int(entry["hour"])
        if hour in by_hour:
            raise ReplayError("duplicate hour in hourly_plan")
        by_hour[hour] = entry
    if sorted(by_hour) != list(range(24)):
        raise ReplayError("hourly_plan must cover hours 0 through 23")

    effective_solar = effective_solar_profile(request.hours, interpretations)
    min_energy = hourly_minimum_energy(request.battery, interpretations)
    no_charge = hour_set(interpretations, "no_charge_window")
    no_discharge = hour_set(interpretations, "no_discharge_window")
    caps = max_grid_caps(interpretations)
    demand = [hour.demand_kwh for hour in request.hours]
    tariff = [hour.tariff_bdt_per_kwh for hour in request.hours]
    battery = request.battery

    energy = float(battery.initial_energy_kwh)
    cleaned: list[HourlyPlanEntry] = []
    total_grid = 0.0
    total_cost = 0.0
    peak = 0.0

    for hour in range(24):
        entry = by_hour[hour]
        grid = _finite_non_negative(entry["grid_kwh"], "grid_kwh")
        solar_used = _finite_non_negative(entry["solar_used_kwh"], "solar_used_kwh")
        battery_kwh = _finite_non_negative(entry["battery_kwh"], "battery_kwh")
        action = entry["battery_action"]
        if action not in {"charge", "discharge", "idle"}:
            raise ReplayError("invalid battery_action")
        if action == "idle" and battery_kwh > NUMERIC_TOLERANCE:
            raise ReplayError("idle action must have battery_kwh = 0")
        if action != "idle" and battery_kwh <= NUMERIC_TOLERANCE:
            action = "idle"
            battery_kwh = 0.0

        charge = battery_kwh if action == "charge" else 0.0
        discharge = battery_kwh if action == "discharge" else 0.0

        if hour in no_charge and charge > NUMERIC_TOLERANCE:
            raise ReplayError(f"charge forbidden in hour {hour}")
        if hour in no_discharge and discharge > NUMERIC_TOLERANCE:
            raise ReplayError(f"discharge forbidden in hour {hour}")
        if charge > battery.max_charge_kwh_per_hour + NUMERIC_TOLERANCE:
            raise ReplayError("charge exceeds hourly limit")
        if discharge > battery.max_discharge_kwh_per_hour + NUMERIC_TOLERANCE:
            raise ReplayError("discharge exceeds hourly limit")
        if solar_used > effective_solar[hour] + NUMERIC_TOLERANCE:
            raise ReplayError("solar_used exceeds effective solar")
        if hour in caps and grid > caps[hour] + NUMERIC_TOLERANCE:
            raise ReplayError("grid exceeds max_grid_window cap")

        balance = grid + solar_used + discharge - demand[hour] - charge
        if abs(balance) > NUMERIC_TOLERANCE:
            raise ReplayError(f"energy balance failed in hour {hour}")

        energy = energy + charge - discharge
        if energy < min_energy[hour] - NUMERIC_TOLERANCE:
            raise ReplayError(f"battery below reserve in hour {hour}")
        if energy > battery.capacity_kwh + NUMERIC_TOLERANCE:
            raise ReplayError(f"battery above capacity in hour {hour}")

        reported = float(entry.get("battery_energy_after_kwh", energy))
        if abs(reported - energy) > NUMERIC_TOLERANCE:
            raise ReplayError("battery_energy_after_kwh does not match transitions")

        cleaned.append(
            HourlyPlanEntry(
                hour=hour,
                grid_kwh=grid,
                solar_used_kwh=solar_used,
                battery_action=action,
                battery_kwh=0.0 if action == "idle" else battery_kwh,
                battery_energy_after_kwh=energy,
            )
        )
        total_grid += grid
        total_cost += grid * tariff[hour]
        peak = max(peak, grid)

    if abs(energy - battery.initial_energy_kwh) > NUMERIC_TOLERANCE:
        raise ReplayError("end-of-day battery energy must equal initial_energy_kwh")

    return ReplayResult(
        hourly_plan=cleaned,
        total_grid_kwh=total_grid,
        total_cost_bdt=total_cost,
        peak_grid_kwh=peak,
    )
