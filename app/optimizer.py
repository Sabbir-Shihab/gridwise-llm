from __future__ import annotations

from app.guardrails import (
    effective_solar_profile,
    hour_set,
    hourly_minimum_energy,
    max_grid_caps,
)
from app.models import DirectiveInterpretation, OptimizeRequest
from app.replay import ReplayError, ReplayResult, replay_plan


class OptimizationError(RuntimeError):
    """Raised when no feasible schedule can be produced."""


_EPS = 1e-7
_SNAP = 1e-6


def _snap(value: float) -> float:
    number = float(value)
    if abs(number) < _SNAP:
        return 0.0
    return number


def _net_battery(charge: float, discharge: float) -> tuple[str, float]:
    charge = max(_snap(charge), 0.0)
    discharge = max(_snap(discharge), 0.0)
    if charge >= discharge:
        net = charge - discharge
        if net <= _SNAP:
            return "idle", 0.0
        return "charge", net
    net = discharge - charge
    if net <= _SNAP:
        return "idle", 0.0
    return "discharge", net


def _solve_lp(
    request: OptimizeRequest,
    interpretations: list[DirectiveInterpretation],
) -> list[dict]:
    try:
        from ortools.linear_solver import pywraplp
    except ImportError as exc:
        raise OptimizationError("OR-Tools is not installed") from exc

    solver = pywraplp.Solver.CreateSolver("GLOP")
    if solver is None:
        raise OptimizationError("GLOP solver is unavailable")

    solver.SetTimeLimit(5000)
    inf = solver.infinity()
    battery = request.battery
    demand = [hour.demand_kwh for hour in request.hours]
    tariff = [hour.tariff_bdt_per_kwh for hour in request.hours]
    solar = effective_solar_profile(request.hours, interpretations)
    min_energy = hourly_minimum_energy(battery, interpretations)
    no_charge = hour_set(interpretations, "no_charge_window")
    no_discharge = hour_set(interpretations, "no_discharge_window")
    caps = max_grid_caps(interpretations)

    grid = []
    solar_used = []
    charge = []
    discharge = []
    energy = []

    for hour in range(24):
        cap = caps.get(hour, inf)
        grid.append(solver.NumVar(0.0, cap, f"grid_{hour}"))
        solar_used.append(solver.NumVar(0.0, max(solar[hour], 0.0), f"solar_{hour}"))
        max_charge = 0.0 if hour in no_charge else battery.max_charge_kwh_per_hour
        max_discharge = 0.0 if hour in no_discharge else battery.max_discharge_kwh_per_hour
        charge.append(solver.NumVar(0.0, max_charge, f"charge_{hour}"))
        discharge.append(solver.NumVar(0.0, max_discharge, f"discharge_{hour}"))
        lo = min_energy[hour]
        hi = battery.capacity_kwh
        if lo > hi + _EPS:
            raise OptimizationError("reserve exceeds battery capacity")
        energy.append(solver.NumVar(lo, hi, f"energy_{hour}"))

    for hour in range(24):
        previous = battery.initial_energy_kwh if hour == 0 else energy[hour - 1]
        solver.Add(energy[hour] == previous + charge[hour] - discharge[hour])
        solver.Add(
            grid[hour] + solar_used[hour] + discharge[hour]
            == demand[hour] + charge[hour]
        )

    solver.Add(energy[23] == battery.initial_energy_kwh)
    solver.Minimize(solver.Sum(grid[hour] * tariff[hour] for hour in range(24)))

    status = solver.Solve()
    if status not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
        raise OptimizationError("energy schedule is infeasible")

    plan = []
    for hour in range(24):
        action, battery_kwh = _net_battery(
            charge[hour].solution_value(),
            discharge[hour].solution_value(),
        )
        solar_val = min(max(_snap(solar_used[hour].solution_value()), 0.0), solar[hour])
        if action == "charge":
            battery_kwh = min(battery_kwh, battery.max_charge_kwh_per_hour)
        elif action == "discharge":
            battery_kwh = min(battery_kwh, battery.max_discharge_kwh_per_hour)
        charge_amt = battery_kwh if action == "charge" else 0.0
        discharge_amt = battery_kwh if action == "discharge" else 0.0
        grid_val = demand[hour] + charge_amt - discharge_amt - solar_val
        if grid_val < 0:
            solar_val = min(solar[hour], solar_val + grid_val)
            solar_val = max(solar_val, 0.0)
            grid_val = demand[hour] + charge_amt - discharge_amt - solar_val
        if hour in caps:
            grid_val = min(grid_val, caps[hour])
            solar_val = min(solar[hour], demand[hour] + charge_amt - discharge_amt - grid_val)
            solar_val = max(solar_val, 0.0)
            grid_val = demand[hour] + charge_amt - discharge_amt - solar_val
        grid_val = max(grid_val, 0.0)
        plan.append(
            {
                "hour": hour,
                "grid_kwh": grid_val,
                "solar_used_kwh": solar_val,
                "battery_action": action,
                "battery_kwh": battery_kwh,
                "battery_energy_after_kwh": energy[hour].solution_value(),
            }
        )
    return plan


def _reconstruct(request: OptimizeRequest, raw_plan: list[dict]) -> list[dict]:
    energy = float(request.battery.initial_energy_kwh)
    rebuilt = []
    for entry in raw_plan:
        action = entry["battery_action"]
        battery_kwh = max(float(entry["battery_kwh"]), 0.0)
        if action == "idle" or battery_kwh <= _SNAP:
            action = "idle"
            battery_kwh = 0.0
        charge = battery_kwh if action == "charge" else 0.0
        discharge = battery_kwh if action == "discharge" else 0.0
        energy = energy + charge - discharge
        rebuilt.append(
            {
                "hour": entry["hour"],
                "grid_kwh": max(float(entry["grid_kwh"]), 0.0),
                "solar_used_kwh": max(float(entry["solar_used_kwh"]), 0.0),
                "battery_action": action,
                "battery_kwh": battery_kwh,
                "battery_energy_after_kwh": energy,
            }
        )
    return rebuilt


def optimize_schedule(
    request: OptimizeRequest,
    interpretations: list[DirectiveInterpretation],
) -> ReplayResult:
    raw_plan = _solve_lp(request, interpretations)
    rebuilt = _reconstruct(request, raw_plan)
    try:
        return replay_plan(request, interpretations, rebuilt)
    except ReplayError:
        # Tiny numeric drift: snap actions from reconstructed energy and rebalance.
        battery = request.battery
        demand = [hour.demand_kwh for hour in request.hours]
        solar = effective_solar_profile(request.hours, interpretations)
        energy = float(battery.initial_energy_kwh)
        fixed = []
        for entry in rebuilt:
            hour = entry["hour"]
            action = entry["battery_action"]
            battery_kwh = entry["battery_kwh"]
            charge = battery_kwh if action == "charge" else 0.0
            discharge = battery_kwh if action == "discharge" else 0.0
            energy_after = energy + charge - discharge
            solar_used = min(max(entry["solar_used_kwh"], 0.0), solar[hour])
            grid = demand[hour] + charge - discharge - solar_used
            if grid < 0:
                solar_used = min(solar[hour], demand[hour] + charge - discharge)
                solar_used = max(solar_used, 0.0)
                grid = demand[hour] + charge - discharge - solar_used
            fixed.append(
                {
                    "hour": hour,
                    "grid_kwh": max(grid, 0.0),
                    "solar_used_kwh": solar_used,
                    "battery_action": action,
                    "battery_kwh": battery_kwh,
                    "battery_energy_after_kwh": energy_after,
                }
            )
            energy = energy_after
        # Force end-of-day neutrality by nudging the last feasible hour if needed.
        drift = energy - battery.initial_energy_kwh
        if abs(drift) > _SNAP:
            for hour in range(23, -1, -1):
                entry = fixed[hour]
                if drift > 0 and entry["battery_action"] in {"idle", "discharge"}:
                    extra = min(drift, battery.max_discharge_kwh_per_hour - (
                        entry["battery_kwh"] if entry["battery_action"] == "discharge" else 0.0
                    ))
                    if extra <= 0:
                        continue
                    new_dis = (entry["battery_kwh"] if entry["battery_action"] == "discharge" else 0.0) + extra
                    solar_used = min(entry["solar_used_kwh"], solar[hour])
                    grid = demand[hour] - new_dis - solar_used
                    if grid < -1e-8:
                        continue
                    entry.update(
                        {
                            "battery_action": "discharge",
                            "battery_kwh": new_dis,
                            "grid_kwh": max(grid, 0.0),
                            "solar_used_kwh": solar_used,
                        }
                    )
                    drift -= extra
                    if abs(drift) <= _SNAP:
                        break
                elif drift < 0 and entry["battery_action"] in {"idle", "charge"}:
                    extra = min(-drift, battery.max_charge_kwh_per_hour - (
                        entry["battery_kwh"] if entry["battery_action"] == "charge" else 0.0
                    ))
                    if extra <= 0:
                        continue
                    new_ch = (entry["battery_kwh"] if entry["battery_action"] == "charge" else 0.0) + extra
                    solar_used = min(entry["solar_used_kwh"], solar[hour])
                    grid = demand[hour] + new_ch - solar_used
                    if grid < -1e-8:
                        continue
                    entry.update(
                        {
                            "battery_action": "charge",
                            "battery_kwh": new_ch,
                            "grid_kwh": max(grid, 0.0),
                            "solar_used_kwh": solar_used,
                        }
                    )
                    drift += extra
                    if abs(drift) <= _SNAP:
                        break
            energy = float(battery.initial_energy_kwh)
            for entry in fixed:
                charge = entry["battery_kwh"] if entry["battery_action"] == "charge" else 0.0
                discharge = entry["battery_kwh"] if entry["battery_action"] == "discharge" else 0.0
                energy = energy + charge - discharge
                entry["battery_energy_after_kwh"] = energy
        return replay_plan(request, interpretations, fixed)
