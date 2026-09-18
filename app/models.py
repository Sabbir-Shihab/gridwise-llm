from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class HourEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    hour: int
    demand_kwh: float
    solar_kwh: float
    tariff_bdt_per_kwh: float

    @field_validator("hour")
    @classmethod
    def hour_range(cls, value: int) -> int:
        if value < 0 or value > 23:
            raise ValueError("hour must be between 0 and 23")
        return value

    @field_validator("demand_kwh", "solar_kwh", "tariff_bdt_per_kwh")
    @classmethod
    def finite_non_negative(cls, value: float) -> float:
        if value is None or value != value or value == float("inf") or value == float("-inf"):
            raise ValueError("numeric fields must be finite")
        if value < 0:
            raise ValueError("numeric fields must be non-negative")
        return float(value)


class BatteryConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    capacity_kwh: float
    initial_energy_kwh: float
    minimum_energy_kwh: float
    max_charge_kwh_per_hour: float
    max_discharge_kwh_per_hour: float

    @field_validator(
        "capacity_kwh",
        "initial_energy_kwh",
        "minimum_energy_kwh",
        "max_charge_kwh_per_hour",
        "max_discharge_kwh_per_hour",
    )
    @classmethod
    def finite_non_negative(cls, value: float) -> float:
        if value is None or value != value or value == float("inf") or value == float("-inf"):
            raise ValueError("battery fields must be finite")
        if value < 0:
            raise ValueError("battery fields must be non-negative")
        return float(value)

    @model_validator(mode="after")
    def bounds(self) -> "BatteryConfig":
        if self.minimum_energy_kwh > self.capacity_kwh:
            raise ValueError("minimum_energy_kwh cannot exceed capacity_kwh")
        if self.initial_energy_kwh > self.capacity_kwh:
            raise ValueError("initial_energy_kwh cannot exceed capacity_kwh")
        if self.initial_energy_kwh < self.minimum_energy_kwh:
            raise ValueError("initial_energy_kwh cannot be below minimum_energy_kwh")
        return self


class OptimizeRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    scenario_id: str
    operator_notes: list[str]
    hours: list[HourEntry]
    battery: BatteryConfig

    @field_validator("scenario_id")
    @classmethod
    def scenario_id_non_empty(cls, value: str) -> str:
        if not str(value).strip():
            raise ValueError("scenario_id must be a non-empty string")
        return str(value)

    @field_validator("operator_notes")
    @classmethod
    def notes_valid(cls, value: list[str]) -> list[str]:
        if not isinstance(value, list) or not (1 <= len(value) <= 3):
            raise ValueError("operator_notes must contain 1 to 3 strings")
        cleaned: list[str] = []
        for note in value:
            if not isinstance(note, str) or not note.strip():
                raise ValueError("each operator note must be a non-empty string")
            cleaned.append(note)
        return cleaned

    @field_validator("hours")
    @classmethod
    def twenty_four_hours(cls, value: list[HourEntry]) -> list[HourEntry]:
        if len(value) != 24:
            raise ValueError("hours must contain exactly 24 entries")
        seen = [entry.hour for entry in value]
        if sorted(seen) != list(range(24)):
            raise ValueError("hours must contain unique integers 0 through 23")
        return sorted(value, key=lambda entry: entry.hour)


class StructuredAdjustment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hours: list[int]
    factor: Optional[float] = None
    minimum_energy_kwh: Optional[float] = None
    max_grid_kwh: Optional[float] = None


class DirectiveInterpretation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note_index: int
    applies: bool
    directive_type: Literal[
        "solar_reduction",
        "minimum_battery_reserve",
        "no_charge_window",
        "no_discharge_window",
        "max_grid_window",
        "no_op",
    ]
    structured_adjustment: Optional[dict[str, Any]] = None
    explanation: str


class HourlyPlanEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hour: int
    grid_kwh: float
    solar_used_kwh: float
    battery_action: Literal["charge", "discharge", "idle"]
    battery_kwh: float
    battery_energy_after_kwh: float


class OptimizeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    directive_interpretation: list[DirectiveInterpretation]
    hourly_plan: list[HourlyPlanEntry]
    total_grid_kwh: float
    total_cost_bdt: float
    peak_grid_kwh: float
    plan_summary: str
