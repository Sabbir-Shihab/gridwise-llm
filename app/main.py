from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.llm import LLMInterpretationError, interpret_operator_notes, summarize_plan
from app.models import OptimizeRequest, OptimizeResponse
from app.optimizer import OptimizationError, optimize_schedule

logger = logging.getLogger("gridwise")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(
    title="GridWise LLM Energy Optimizer",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
)


@app.exception_handler(RequestValidationError)
async def request_validation_handler(_: Request, __: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "error": "invalid_request",
            "detail": "Malformed JSON or structurally invalid request.",
        },
    )


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    if isinstance(exc, StarletteHTTPException):
        return await http_exception_handler(request, exc)
    logger.exception("Unhandled error: %s", type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "detail": "Controlled internal error."},
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/optimize-energy", response_model=OptimizeResponse)
def optimize_energy(payload: OptimizeRequest) -> OptimizeResponse:
    try:
        interpretations = interpret_operator_notes(payload)
        result = optimize_schedule(payload, interpretations)
    except LLMInterpretationError as exc:
        logger.error("LLM interpretation failed: %s", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Controlled internal error.") from None
    except OptimizationError as exc:
        logger.error("Optimization failed: %s", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Controlled internal error.") from None

    return OptimizeResponse(
        scenario_id=payload.scenario_id,
        directive_interpretation=interpretations,
        hourly_plan=result.hourly_plan,
        total_grid_kwh=result.total_grid_kwh,
        total_cost_bdt=result.total_cost_bdt,
        peak_grid_kwh=result.peak_grid_kwh,
        plan_summary=summarize_plan(interpretations, result.total_cost_bdt),
    )
