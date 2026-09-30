"""
backend/main.py
===============
SmartCare AI — FastAPI Backend
IBM Bob 2.0 Hackathon: Agent Mode · Parallel Subagents · Document Understanding

Endpoints
---------
POST /api/diagnose
    Full 4-subagent parallel pipeline (SA1 ∥ SA2 → SA3 → SA4).
    Accepts any combination of: brand, model, error_code, telemetry, user_symptom.
    Returns structured DiagnosticResult + agent_execution_trace.

GET  /api/agents/status
    Returns the names, versions, and roles of all registered subagents.

GET  /health
    Service liveness check.

Environment variables (.env)
-----------------------------
WATSONX_API_KEY, WATSONX_PROJECT_ID, WATSONX_URL
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.agents import run_diagnostic_pipeline

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)

# ── App ────────────────────────────────────────────────────────────────────────
_FRONTEND = Path(__file__).parent.parent / "frontend"

app = FastAPI(
    title="SmartCare AI — Diagnostic Backend",
    description=(
        "IBM Bob 2.0 Hackathon backend. "
        "4-subagent parallel pipeline: TelemetryIngestion ∥ DocumentUnderstanding "
        "→ SafetyTriage → ResolutionDispatch."
    ),
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend at /  (must be mounted AFTER API routes are defined,
# so we do it at the bottom of this file via a catch-all GET route)

# ── Schemas ────────────────────────────────────────────────────────────────────

class DiagnoseRequest(BaseModel):
    brand:        str
    model:        str
    # Optional structured telemetry
    error_code:   Optional[str]  = Field(None, description="Error code from display (e.g. OE, E18)")
    water_level:  Optional[str]  = Field(None, description="Tub water sensor reading")
    drum_rpm:     Optional[int]  = Field(None, description="Current drum RPM")
    power_draw_w: Optional[int]  = Field(None, description="Motor power draw in watts")
    user_symptom: Optional[str]  = Field(None, description="Plain-language symptom")
    # Legacy field — map to user_symptom for backward-compat
    user_input:   Optional[str]  = Field(None, description="Alias for user_symptom")


class StepItem(BaseModel):
    step_number: int
    instruction: str


class ServiceContact(BaseModel):
    brand: str
    phone: str


class AgentTrace(BaseModel):
    subagent:      str
    version:       str
    status:        str
    started_at:    str
    completed_at:  str
    duration_ms:   int
    input_summary: str
    output_summary: str
    log_lines:     list[str]


class DiagnoseResponse(BaseModel):
    can_user_solve:         bool
    machine_health_score:   int
    issue_title:            str
    root_cause:             str
    risk_level:             str
    oem_tolerance_note:     Optional[str]  = None
    wiring_hazard:          Optional[str]  = None
    service_center_contact: ServiceContact
    steps_to_solve:         list[StepItem]
    youtube_video_id:       Optional[str]  = None
    technician_reason:      Optional[str]  = None
    call_to_action:         str
    agent_execution_trace:  list[AgentTrace]


# ── Subagent registry (for /api/agents/status) ─────────────────────────────────
AGENT_REGISTRY = [
    {
        "id": "SA1", "name": "TelemetryIngestionSubagent", "version": "1.0",
        "role": "Parses hardware registers: RPM, water level, power draw, error codes.",
        "executes": "parallel (with SA2)",
    },
    {
        "id": "SA2", "name": "DocumentUnderstandingSubagent", "version": "1.0",
        "role": (
            "Semantic document understanding over multi-brand OEM service manuals, "
            "wiring schematics, and tolerance tables (LG, Samsung, Bosch, Whirlpool, IFB)."
        ),
        "executes": "parallel (with SA1)",
    },
    {
        "id": "SA3", "name": "SafetyTriageSubagent", "version": "1.0",
        "role": "Synthesises SA1+SA2 findings. Issues authoritative USER_DIY vs TECHNICIAN_REQUIRED ruling.",
        "executes": "sequential (after SA1∥SA2)",
    },
    {
        "id": "SA4", "name": "ResolutionDispatchSubagent", "version": "1.0",
        "role": (
            "Generates step-by-step visual guides + YouTube ID for safe DIY fixes, "
            "or brand-specific service centre hotline for hazard cases."
        ),
        "executes": "sequential (after SA3)",
    },
]


# ── POST /api/diagnose ─────────────────────────────────────────────────────────

@app.post("/api/diagnose", response_model=DiagnoseResponse)
async def diagnose(req: DiagnoseRequest) -> DiagnoseResponse:
    """
    Execute the full 4-subagent parallel diagnostic pipeline.

    Phase 1 (parallel):  SA1 TelemetryIngestion  ∥  SA2 DocumentUnderstanding
    Phase 2 (sequential): SA3 SafetyTriage
    Phase 3 (sequential): SA4 ResolutionDispatch
    """
    # Normalise: user_input (legacy) → user_symptom
    symptom = req.user_symptom or req.user_input

    # If user_input looks like an error code (short, uppercase), treat as error_code
    error_code = req.error_code
    if not error_code and symptom:
        stripped = symptom.strip()
        if len(stripped) <= 4 and stripped.replace(" ", "").isalnum():
            error_code = stripped.upper()
            symptom    = None

    logger.info(
        "Pipeline start: brand=%s model=%s ec=%s symptom=%r",
        req.brand, req.model, error_code, symptom,
    )

    result = await run_diagnostic_pipeline(
        brand        = req.brand,
        model        = req.model,
        error_code   = error_code,
        water_level  = req.water_level,
        drum_rpm     = req.drum_rpm,
        power_draw_w = req.power_draw_w,
        user_symptom = symptom,
    )

    logger.info(
        "Pipeline complete: classification=%s health=%d%%",
        "USER_DIY" if result.can_user_solve else "TECHNICIAN_REQUIRED",
        result.machine_health_score,
    )

    return DiagnoseResponse(
        can_user_solve         = result.can_user_solve,
        machine_health_score   = result.machine_health_score,
        issue_title            = result.issue_title,
        root_cause             = result.root_cause,
        risk_level             = result.risk_level,
        oem_tolerance_note     = result.oem_tolerance_note,
        wiring_hazard          = result.wiring_hazard,
        service_center_contact = ServiceContact(**result.service_center_contact),
        steps_to_solve         = [StepItem(**s) for s in result.steps_to_solve],
        youtube_video_id       = result.youtube_video_id,
        technician_reason      = result.technician_reason,
        call_to_action         = result.call_to_action,
        agent_execution_trace  = [AgentTrace(**t) for t in result.agent_execution_trace],
    )


# ── GET /api/agents/status ──────────────────────────────────────────────────────

@app.get("/api/agents/status")
async def agents_status():
    """Returns registered subagents and their roles."""
    return {
        "pipeline": "TelemetryIngestion ∥ DocumentUnderstanding → SafetyTriage → ResolutionDispatch",
        "parallelism": "SA1 and SA2 execute concurrently via asyncio.gather()",
        "agents": AGENT_REGISTRY,
        "watsonx_configured": bool(
            os.getenv("WATSONX_API_KEY") and os.getenv("WATSONX_PROJECT_ID")
        ),
    }


# ── GET /health ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status":             "ok",
        "version":            "3.0.0",
        "watsonx_configured": bool(
            os.getenv("WATSONX_API_KEY") and os.getenv("WATSONX_PROJECT_ID")
        ),
        "model":              "ibm/granite-3-8b-instruct",
        "agents":             [a["name"] for a in AGENT_REGISTRY],
    }


# ── Serve frontend ──────────────────────────────────────────────────────────────
# /frontend/index.html  — phone-friendly path (matches QR code URLs)
# /                     — browser shortcut
# /static               — raw asset fallback

if _FRONTEND.is_dir():
    # Mount at /frontend so QR URLs like /frontend/index.html work on phones
    app.mount("/frontend", StaticFiles(directory=str(_FRONTEND), html=True), name="frontend")
    # Also mount raw assets at /static for any relative imports
    app.mount("/static", StaticFiles(directory=str(_FRONTEND)), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_index():
        return FileResponse(str(_FRONTEND / "index.html"))


# ── Entrypoint ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
